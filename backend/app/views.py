"""
API views

Auth endpoints:
  POST /auth/register          — create account (open)
  POST /auth/login             — get JWT tokens (open)
  POST /auth/token/refresh     — refresh access token (open)
  GET  /auth/me                — current user info (authenticated)

AI endpoints (all require JWT):
  POST /app/ai/upload          — ingest file  [editor, admin]
  POST /app/ai/query           — RAG query    [viewer, editor, admin]
  GET  /app/ai/files           — list files   [viewer, editor, admin]
"""

import logging
from pathlib import PurePosixPath

from decouple import config
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
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

logger       = logging.getLogger(__name__)
User         = get_user_model()
S3_BUCKET    = config("S3_BUCKET")
ALL_SUPPORTED = sorted(DOC_EXTENSIONS | SUPPORTED_MEDIA_EXTENSIONS)


# ─────────────────────────────────────────────────────────────────────────────
# AUTH — open endpoints (no JWT required)
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    """
    POST /auth/register
    Body: { "email": "...", "password": "...", "password2": "...", "role": "viewer|editor|admin" }

    Role defaults to "viewer" if omitted.
    Only an existing admin should be able to create editor/admin accounts in
    production — enforce that at the infrastructure level or add a check here.
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

    Returns access + refresh JWT tokens.
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
        return Response(
            {"error": "Invalid credentials"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if not user.check_password(password):
        return Response(
            {"error": "Invalid credentials"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if not user.is_active:
        return Response(
            {"error": "Account is disabled"},
            status=status.HTTP_403_FORBIDDEN,
        )

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
    """
    GET /auth/me
    Returns the current authenticated user's profile and role.
    """
    return Response(UserSerializer(request.user).data, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────────
# AI — POST /app/ai/upload   [editor, admin only]
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAdminOrEditor])
def store_vectordb(request):
    """
    Ingest a file from S3 into Qdrant.
    Requires: editor or admin role.

    Body: { "s3_key": "path/to/file.pdf" }
    """
    s3_key = request.data.get("s3_key", "").strip()
    if not s3_key:
        return Response({"error": "s3_key is required"}, status=status.HTTP_400_BAD_REQUEST)

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
        uploaded_by    = request.user,
    )

    return Response(
        {
            "message":       "File ingested successfully",
            "s3_key":        s3_key,
            "file_type":     ext.lstrip("."),
            "chunks_stored": stored,
            "uploaded_by":   request.user.email,
        },
        status=status.HTTP_201_CREATED,
    )


# ─────────────────────────────────────────────────────────────────────────────
# AI — POST /app/ai/query   [all authenticated users]
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAnyRole])
def query_vectordb(request):
    """
    Ask a question over all ingested documents.
    Requires: any authenticated user (viewer, editor, admin).

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
    """
    List all ingested files.
    Requires: any authenticated user.
    """
    files = IngestedFile.objects.all().values(
        "s3_key", "file_type", "chunks_stored", "ingested_at", "uploaded_by__email"
    )
    return Response({"files": list(files), "total": len(files)}, status=status.HTTP_200_OK)
