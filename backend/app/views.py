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
import time
from datetime import timedelta
from pathlib import PurePosixPath

from decouple import config
from Services.aws_storage import upload_file_to_s3
from .utils import resolve_workspace
from .metrics_service import log_prediction_and_check_drift, get_workspace_monitoring_stats
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes, throttle_classes
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from Services.Extractor import extract_and_chunk
from Services.Ai_service.embedding import embed_and_store
from .tasks import run_ingestion_task
from .throttling import CostControlRoleThrottle
from Services.Ai_service.load_data import SUPPORTED_EXTENSIONS as DOC_EXTENSIONS
from Services.Ai_service.video_transcibing import SUPPORTED_MEDIA_EXTENSIONS
from Services.agent import query as rag_query

from django.db.models import Avg, Count
from django.utils import timezone

from .models import IngestedFile, Workspace, PredictionLog, DriftLog
from .alerting import send_drift_alert, send_error_alert
from .permissions import IsAdminOrEditor, IsAnyRole
from .serializers import RegisterSerializer, UserSerializer, WorkspaceSerializer

logger        = logging.getLogger(__name__)
User          = get_user_model()
OBJECT_STORAGE_BUCKET = config("OBJECT_STORAGE_BUCKET", default=config("S3_BUCKET", default="arishem-documents"))
AWS_REGION    = config("AWS_REGION", default="us-east-1")
ALL_SUPPORTED = sorted(DOC_EXTENSIONS | SUPPORTED_MEDIA_EXTENSIONS)

# S3 client and logic moved to Services.aws_storage


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

def _run_ingestion(s3_key: str, user, workspace_id: int) -> Response:
    """
    Shared logic: check backpressure, create DB record in PENDING state,
    enqueue to Celery (RabbitMQ), and return 202 Accepted.
    """
    try:
        workspace = user.workspaces.get(id=workspace_id)
    except (Workspace.DoesNotExist, ValueError, TypeError):
        return Response({"error": "Workspace not found or access denied"}, status=status.HTTP_403_FORBIDDEN)

    ext = PurePosixPath(s3_key).suffix.lower()

    if ext not in DOC_EXTENSIONS and ext not in SUPPORTED_MEDIA_EXTENSIONS:
        return Response(
            {"error": f"Unsupported file type '{ext}'", "supported": ALL_SUPPORTED},
            status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )

    if IngestedFile.objects.filter(object_bucket=OBJECT_STORAGE_BUCKET, object_key=s3_key).exists():
        return Response(
            {"error": f"'{s3_key}' has already been ingested or is in progress. Delete it first to re-ingest."},
            status=status.HTTP_409_CONFLICT,
        )

    # ── Backpressure Handling ─────────────────────────────────────────────────
    from django.conf import settings
    max_depth = getattr(settings, 'MAX_INGESTION_QUEUE_DEPTH', 50)
    active_jobs_count = IngestedFile.objects.filter(status__in=['PENDING', 'PROCESSING']).count()
    if active_jobs_count >= max_depth:
        logger.warning("Ingestion queue depth exceeded: %d >= %d. Rejecting job request.", active_jobs_count, max_depth)
        return Response(
            {
                "error": "Service Temporarily Unavailable",
                "message": f"The background ingestion pipeline is currently experiencing heavy load. Queue depth is at capacity ({active_jobs_count}/{max_depth}). Please try again later."
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    # Create the IngestedFile record in database in PENDING status (Dual-write consistency step 1)
    file_obj = IngestedFile.objects.create(
        object_bucket  = OBJECT_STORAGE_BUCKET,
        object_key     = s3_key,
        file_type      = ext.lstrip("."),
        chunks_stored  = 0,
        uploaded_by    = user,
        workspace      = workspace,
        status         = 'PENDING',
    )

    # Trigger Celery Background worker
    task = run_ingestion_task.delay(
        s3_key=s3_key,
        user_id=user.id,
        workspace_id=workspace.id,
        file_id=file_obj.id
    )

    return Response(
        {
            "message": "Ingestion task queued successfully",
            "task_id": task.id,
            "file": {
                "id": file_obj.id,
                "s3_key": file_obj.object_key,
                "file_type": file_obj.file_type,
                "status": file_obj.status,
                "chunks_stored": file_obj.chunks_stored,
            }
        },
        status=status.HTTP_202_ACCEPTED
    )


# ─────────────────────────────────────────────────────────────────────────────
# AI — POST /app/ai/upload   [editor, admin only]
# Ingest a file that already exists in S3 by providing its key
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAdminOrEditor])
@throttle_classes([CostControlRoleThrottle])
def store_vectordb(request):
    """
    POST /app/ai/upload
    Body: { "s3_key": "path/to/file.pdf", "workspace_id": 1 }
    File must already exist in S3.
    """
    s3_key = request.data.get("s3_key", "").strip()
    if not s3_key:
        return Response({"error": "s3_key is required"}, status=status.HTTP_400_BAD_REQUEST)

    workspace_id, error_response = resolve_workspace(request, request.data)
    if error_response:
        return error_response

    return _run_ingestion(s3_key, request.user, workspace_id)


# ─────────────────────────────────────────────────────────────────────────────
# AI — POST /app/ai/upload-direct   [editor, admin only]
# Upload a file from the browser directly — saves to S3 then ingests
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAdminOrEditor])
@parser_classes([MultiPartParser])
@throttle_classes([CostControlRoleThrottle])
def upload_direct(request):
    """
    POST /app/ai/upload-direct
    Form-data: file=<binary>, workspace_id=1
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
    if not upload_file_to_s3(file_obj, s3_key):
        return Response({"error": f"S3 upload failed for {original_name}"}, status=status.HTTP_502_BAD_GATEWAY)

    # Now ingest from S3
    workspace_id, error_response = resolve_workspace(request, request.data)
    if error_response:
        return error_response

    return _run_ingestion(s3_key, request.user, workspace_id)


# AI — POST /app/ai/query   [all authenticated users]
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAnyRole])
@throttle_classes([CostControlRoleThrottle])
def query_vectordb(request):
    """
    POST /app/ai/query
    Body: { "question": "...", "top_k": 5, "workspace_id": 1 }
    """
    question = request.data.get("question", "").strip()
    if not question:
        return Response({"error": "question is required"}, status=status.HTTP_400_BAD_REQUEST)

    workspace_id, error_response = resolve_workspace(request, request.data)
    if error_response:
        return error_response

    kwargs = {}
    top_k = request.data.get("top_k")
    if top_k is not None:
        try:
            kwargs["top_k"] = int(top_k)
        except (ValueError, TypeError):
            return Response({"error": "top_k must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

    start_time = time.time()
    error_msg = None
    result = None
    try:
        result = rag_query(
            question,
            workspace_id=workspace_id,
            user_email=request.user.email,
            user_role=request.user.role,
            **kwargs
        )
    except Exception as e:
        logger.exception("RAG query failed: '%s'", question[:80])
        error_msg = str(e)
    
    response_time_ms = int((time.time() - start_time) * 1000)

    # Log prediction and check drift via metrics_service
    user = request.user if request.user.is_authenticated else None
    log_prediction_and_check_drift(
        workspace_id=workspace_id,
        user=user,
        question=question,
        result=result,
        response_time_ms=response_time_ms,
        error_msg=error_msg
    )

    if error_msg:
        return Response({"error": f"Query failed: {error_msg}"}, status=status.HTTP_502_BAD_GATEWAY)

    return Response(result, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────────
# AI — GET /app/ai/files   [all authenticated users]
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsAnyRole])
def list_files(request):
    """
    GET /app/ai/files — list all ingested files.
    Query params: workspace_id=1
    """
    workspace_id, error_response = resolve_workspace(request, request.query_params)
    if error_response:
        # Special case: original list_files returns empty array instead of error when no workspace exists
        if error_response.status_code == 400 and error_response.data.get("error") == "No workspace available.":
            return Response({"files": [], "total": 0}, status=status.HTTP_200_OK)
        return error_response

    raw_files = list(
        IngestedFile.objects.filter(workspace_id=workspace_id).values(
            "id", "object_key", "file_type", "chunks_stored", "status", "error_message", "ingested_at", "uploaded_by__email"
        )
    )
    files = []
    for f in raw_files:
        item = dict(f)
        item["s3_key"] = f["object_key"]
        files.append(item)
    return Response({"files": files, "total": len(files)}, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────────
# AI — DELETE /app/ai/files   [editor, admin only]
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["DELETE"])
@permission_classes([IsAdminOrEditor])
def delete_file(request):
    """
    DELETE /app/ai/files/delete (actually mapped to DELETE /app/ai/files/delete or /app/ai/files)
    Body: { "s3_key": "uploads/report.pdf" }
    Removes the DB record so the file can be re-ingested.
    Does NOT delete from S3 or Qdrant (vectors remain but are orphaned).
    """
    s3_key = request.data.get("s3_key", "").strip()
    if not s3_key:
        return Response({"error": "s3_key is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        file_obj = IngestedFile.objects.get(object_bucket=OBJECT_STORAGE_BUCKET, object_key=s3_key)
    except IngestedFile.DoesNotExist:
        return Response({"error": f"'{s3_key}' not found in ingested files"}, status=status.HTTP_404_NOT_FOUND)

    if file_obj.workspace and not request.user.workspaces.filter(id=file_obj.workspace.id).exists():
        return Response({"error": "Workspace access denied"}, status=status.HTTP_403_FORBIDDEN)

    file_obj.delete()
    return Response({"message": f"'{s3_key}' removed successfully"}, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAnyRole])
def check_task_status(request, task_id):
    """
    GET /app/ai/tasks/<task_id>
    Check status of a background ingestion task from the Celery result backend.
    """
    from celery.result import AsyncResult
    res = AsyncResult(task_id)
    response_data = {
        "task_id": task_id,
        "status": res.status, # PENDING, STARTED, SUCCESS, FAILURE, etc.
    }
    if res.failed():
        response_data["error"] = str(res.result)
    elif res.ready():
        response_data["result"] = res.result
    return Response(response_data, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────────
# AUTH — GET /app/auth/workspaces   [all authenticated users]
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsAnyRole])
def list_workspaces(request):
    """
    GET /app/auth/workspaces
    Lists all workspaces the authenticated user belongs to.
    """
    workspaces = request.user.workspaces.all()
    serializer = WorkspaceSerializer(workspaces, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────────
# AI — GET /app/ai/monitoring   [editor, admin only]
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsAdminOrEditor])
def get_monitoring_stats(request):
    """
    GET /app/ai/monitoring
    Query params: workspace_id=1
    Returns aggregated metrics for the dashboard.
    """
    workspace_id, error_response = resolve_workspace(request, request.query_params)
    if error_response:
        return error_response

    stats = get_workspace_monitoring_stats(workspace_id)
    return Response(stats, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────────
# MEETING INTELLIGENCE — YouTube Ingestion & Analysis Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAdminOrEditor])
def ingest_youtube(request):
    """
    POST /app/ai/meetings/ingest-youtube
    Body: { "url": "https://www.youtube.com/watch?v=...", "workspace_id": 1 }
    Downloads YouTube audio, transcribes with local Whisper, embeds to Qdrant,
    and runs meeting intelligence analysis.
    """
    url = request.data.get("url", "").strip()
    if not url or not ("youtube.com" in url or "youtu.be" in url):
        return Response(
            {"error": "Valid YouTube URL is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    workspace_id, error_resp = resolve_workspace(request, request.data)
    if error_resp:
        return error_resp

    try:
        workspace = request.user.workspaces.get(id=workspace_id)
    except Exception:
        return Response({"error": "Workspace not found or access denied"}, status=status.HTTP_403_FORBIDDEN)

    try:
        from Services.meeting.audio_processor import download_youtube, convert_to_wav, cleanup_temp_files
        from Services.meeting.transcriber import transcribe_file
        from langchain_core.documents import Document

        # 1. Download YouTube audio
        audio_file = download_youtube(url)
        wav_file = convert_to_wav(audio_file)

        # 2. Transcribe locally using Whisper
        logger.info("Transcribing YouTube video from %s", url)
        transcript = transcribe_file(wav_file)

        # 3. Create document chunks
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=150)
        doc = Document(page_content=transcript, metadata={"source": url, "media_type": "youtube"})
        chunks = splitter.split_documents([doc])

        # 4. Embed into Qdrant
        stored = embed_and_store(chunks, workspace.id, uploaded_by=request.user.email)

        # 5. Create IngestedFile DB record
        video_id = url.split("v=")[-1].split("&")[0] if "v=" in url else "yt_video"
        file_obj = IngestedFile.objects.create(
            object_bucket=OBJECT_STORAGE_BUCKET,
            object_key=f"youtube/{video_id}.mp3",
            original_filename=f"YouTube_{video_id}",
            file_type="mp3",
            document_category="meeting",
            chunks_stored=stored,
            uploaded_by=request.user,
            workspace=workspace,
            status="SUCCESS",
        )

        # Cleanup temp audio files
        cleanup_temp_files(audio_file, wav_file)

        # 6. Trigger meeting analysis Celery task
        from .tasks import run_meeting_analysis_task
        run_meeting_analysis_task.delay(file_obj.id, [c.page_content for c in chunks])

        return Response(
            {
                "message": "YouTube meeting successfully ingested and analysis queued.",
                "file_id": file_obj.id,
                "chunks_stored": stored,
            },
            status=status.HTTP_201_CREATED,
        )

    except Exception as e:
        logger.exception("Failed to ingest YouTube video: %s", e)
        return Response({"error": f"YouTube ingestion failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@permission_classes([IsAnyRole])
def get_meeting_analysis(request, file_id):
    """
    GET /app/ai/meetings/<file_id>/analysis
    Returns the MeetingAnalysis details for an ingested meeting file.
    """
    from .models import MeetingAnalysis
    try:
        analysis = MeetingAnalysis.objects.get(file_id=file_id)
        return Response(
            {
                "file_id": file_id,
                "title": analysis.title,
                "summary": analysis.summary,
                "action_items": analysis.action_items,
                "key_decisions": analysis.key_decisions,
                "open_questions": analysis.open_questions,
                "full_transcript": analysis.full_transcript,
                "created_at": analysis.created_at,
            },
            status=status.HTTP_200_OK,
        )
    except MeetingAnalysis.DoesNotExist:
        # If record is not ready yet, return 404 or pending status
        return Response(
            {"error": "Meeting analysis is still processing or not found for this file."},
            status=status.HTTP_404_NOT_FOUND,
        )




