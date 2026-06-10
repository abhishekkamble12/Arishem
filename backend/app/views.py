"""
API views

Auth endpoints:
  POST /auth/register          — create account (open)
  POST /auth/login             — get JWT tokens (open)
  POST /auth/token/refresh     — refresh access token (open)
  GET  /auth/me                — current user info (authenticated)

AI endpoints (all require JWT):
  POST /app/ai/upload          — ingest file from S3 key  [editor, admin]
  POST /app/ai/upload-direct   — upload file directly + ingest [editor, admin]
  POST /app/ai/query           — RAG query    [viewer, editor, admin]
  GET  /app/ai/files           — list files   [viewer, editor, admin]
  DELETE /app/ai/files         — delete ingested file record [editor, admin]
"""

import logging
import tempfile
import os
from pathlib import PurePosixPath

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from decouple import config
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from Services.Extractor import extract_and_chunk
from Services.Ai_service.embedding import embed_and_store
from Services.Ai_service.load_data import SUPPORTED_EXTENSIONS as DOC_EXTENSIONS
from Services.Ai_service.video_transcibing import SUPPORTED_MEDIA_EXTENSIONS
from Services.agent import query as rag_query

from .models import IngestedFile
from .permissions import IsAdminOrEditor, IsAnyRole
from .serializers import RegisterSerializer, UserSerializer

logger        = logging.getLogger(__name__)
User          = get_user_model()
S3_BUCKET     = config("S3_BUCKET")
AWS_REGION    = config("AWS_REGION", default="us-east-1")
ALL_SUPPORTED = sorted(DOC_EXTENSIONS | SUPPORTED_MEDIA_EXTENSIONS)

# Lazy S3 client singleton
_s3 = None
def _get_s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3", region_name=AWS_REGION)
    return _s3


# ─────────────────────────────────────────────────────────────────────────────
# AUTH — open endpoints (no JWT required)
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    """
    POST /auth/register
    Body: { "email": "...", "password": "...", "password2": "...", "role": "viewer|editor|admin" }
    """
    serializer = RegisterSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    user = serializer.save()
    refresh = RefreshToken.for_user(user)

    return Response(
        {
            "message": "Account created successfully",
            "user": UserSerializer(user).data,
            "tokens": {
                "access":  str(refresh.access_token),
                "refresh": str(refresh),
            },
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    """
    POST /auth/login
    Body: { "email": "...", "password": "..." }
    """
    email    = request.data.get("email", "").strip().lower()
    password = request.data.get("password", "")

    if not email or not password:
        return Response(
            {"error": "email and password are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

    if not user.check_password(password):
        return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

    if not user.is_active:
        return Response({"error": "Account is disabled"}, status=status.HTTP_403_FORBIDDEN)

    refresh = RefreshToken.for_user(user)
    return Response(
        {
            "user": UserSerializer(user).data,
            "tokens": {
                "access":  str(refresh.access_token),
                "refresh": str(refresh),
            },
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAnyRole])
def me(request):
    """GET /auth/me — current user profile."""
    return Response(UserSerializer(request.user).data, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────────
# Shared ingestion helper
# ─────────────────────────────────────────────────────────────────────────────

def _run_ingestion(s3_key: str, user) -> Response:
    """
    Shared logic: extract chunks from S3 key, embed, store in Qdrant,
    record in IngestedFile. Returns a DRF Response.
    """
    ext = PurePosixPath(s3_key).suffix.lower()

    if ext not in DOC_EXTENSIONS and ext not in SUPPORTED_MEDIA_EXTENSIONS:
        return Response(
            {"error": f"Unsupported file type '{ext}'", "supported": ALL_SUPPORTED},
            status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )

    if IngestedFile.objects.filter(s3_bucket=S3_BUCKET, s3_key=s3_key).exists():
        return Response(
            {"error": f"'{s3_key}' has already been ingested. Delete it first to re-ingest."},
            status=status.HTTP_409_CONFLICT,
        )

    try:
        chunks = extract_and_chunk(bucket_name=S3_BUCKET, s3_key=s3_key)
    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception("Extraction failed for '%s'", s3_key)
        return Response({"error": f"Extraction failed: {str(e)}"}, status=status.HTTP_502_BAD_GATEWAY)

    if not chunks:
        return Response(
            {"error": "No text could be extracted from the file"},
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    try:
        stored = embed_and_store(chunks)
    except Exception as e:
        logger.exception("Embedding/storage failed for '%s'", s3_key)
        return Response({"error": f"Embedding/storage failed: {str(e)}"}, status=status.HTTP_502_BAD_GATEWAY)

    transcribe_job = None
    if chunks and "job_name" in chunks[0].metadata:
        transcribe_job = chunks[0].metadata["job_name"]

    IngestedFile.objects.create(
        s3_bucket      = S3_BUCKET,
        s3_key         = s3_key,
        file_type      = ext.lstrip("."),
        chunks_stored  = stored,
        transcribe_job = transcribe_job,
        uploaded_by    = user,
    )

    return Response(
        {
            "message":       "File ingested successfully",
            "s3_key":        s3_key,
            "file_type":     ext.lstrip("."),
            "chunks_stored": stored,
            "uploaded_by":   user.email,
        },
        status=status.HTTP_201_CREATED,
    )


# ─────────────────────────────────────────────────────────────────────────────
# AI — POST /app/ai/upload   [editor, admin only]
# Ingest a file that already exists in S3 by providing its key
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAdminOrEditor])
def store_vectordb(request):
    """
    POST /app/ai/upload
    Body: { "s3_key": "path/to/file.pdf" }
    File must already exist in S3.
    """
    s3_key = request.data.get("s3_key", "").strip()
    if not s3_key:
        return Response({"error": "s3_key is required"}, status=status.HTTP_400_BAD_REQUEST)

    return _run_ingestion(s3_key, request.user)


# ─────────────────────────────────────────────────────────────────────────────
# AI — POST /app/ai/upload-direct   [editor, admin only]
# Upload a file from the browser directly — saves to S3 then ingests
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAdminOrEditor])
@parser_classes([MultiPartParser])
def upload_direct(request):
    """
    POST /app/ai/upload-direct
    Form-data: file=<binary>
    Accepts multipart file upload, saves to S3 under uploads/<filename>,
    then runs the same ingestion pipeline as /ai/upload.
    """
    file_obj = request.FILES.get("file")
    if not file_obj:
        return Response({"error": "No file provided. Send as multipart form-data with key 'file'."}, status=status.HTTP_400_BAD_REQUEST)

    original_name = file_obj.name
    ext = PurePosixPath(original_name).suffix.lower()

    if ext not in DOC_EXTENSIONS and ext not in SUPPORTED_MEDIA_EXTENSIONS:
        return Response(
            {"error": f"Unsupported file type '{ext}'", "supported": ALL_SUPPORTED},
            status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )

    # S3 key: uploads/<original filename>
    s3_key = f"uploads/{original_name}"

    # Upload to S3
    try:
        s3 = _get_s3()
        s3.upload_fileobj(file_obj, S3_BUCKET, s3_key)
        logger.info("Uploaded '%s' to s3://%s/%s", original_name, S3_BUCKET, s3_key)
    except (ClientError, BotoCoreError) as e:
        logger.exception("S3 upload failed for '%s'", original_name)
        return Response({"error": f"S3 upload failed: {str(e)}"}, status=status.HTTP_502_BAD_GATEWAY)

    # Now ingest from S3
    return _run_ingestion(s3_key, request.user)


# ─────────────────────────────────────────────────────────────────────────────
# AI — POST /app/ai/query   [all authenticated users]
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAnyRole])
def query_vectordb(request):
    """
    POST /app/ai/query
    Body: { "question": "...", "top_k": 5 }
    """
    question = request.data.get("question", "").strip()
    if not question:
        return Response({"error": "question is required"}, status=status.HTTP_400_BAD_REQUEST)

    kwargs = {}
    top_k = request.data.get("top_k")
    if top_k is not None:
        try:
            kwargs["top_k"] = int(top_k)
        except (ValueError, TypeError):
            return Response({"error": "top_k must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        result = rag_query(question, **kwargs)
    except Exception as e:
        logger.exception("RAG query failed: '%s'", question[:80])
        return Response({"error": f"Query failed: {str(e)}"}, status=status.HTTP_502_BAD_GATEWAY)

    return Response(result, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────────
# AI — GET /app/ai/files   [all authenticated users]
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsAnyRole])
def list_files(request):
    """GET /app/ai/files — list all ingested files."""
    files = list(
        IngestedFile.objects.all().values(
            "id", "s3_key", "file_type", "chunks_stored", "ingested_at", "uploaded_by__email"
        )
    )
    return Response({"files": files, "total": len(files)}, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────────
# AI — DELETE /app/ai/files   [editor, admin only]
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["DELETE"])
@permission_classes([IsAdminOrEditor])
def delete_file(request):
    """
    DELETE /app/ai/files
    Body: { "s3_key": "uploads/report.pdf" }
    Removes the DB record so the file can be re-ingested.
    Does NOT delete from S3 or Qdrant (vectors remain but are orphaned).
    """
    s3_key = request.data.get("s3_key", "").strip()
    if not s3_key:
        return Response({"error": "s3_key is required"}, status=status.HTTP_400_BAD_REQUEST)

    deleted, _ = IngestedFile.objects.filter(s3_bucket=S3_BUCKET, s3_key=s3_key).delete()
    if deleted == 0:
        return Response({"error": f"'{s3_key}' not found in ingested files"}, status=status.HTTP_404_NOT_FOUND)

    return Response({"message": f"'{s3_key}' removed successfully"}, status=status.HTTP_200_OK)
