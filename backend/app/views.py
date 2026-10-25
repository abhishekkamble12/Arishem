"""
API views

Auth endpoints:
  POST /auth/register          — create account (open)
  POST /auth/login             — get JWT tokens (open)
  POST /auth/token/refresh     — refresh access token (open)
  GET  /auth/me                — current user info (authenticated)
  PATCH /auth/users/<id>/role  — change a user's role [admin]

AI endpoints (all require JWT):
  POST /app/ai/upload          — ingest file from storage key [editor, admin]
  POST /app/ai/upload-direct   — upload file directly + ingest [editor, admin]
  POST /app/ai/query           — RAG query    [viewer, editor, admin]
  GET  /app/ai/files           — list files   [viewer, editor, admin]
  DELETE /app/ai/files/delete  — delete file, its vectors and stored object [editor, admin]

Ops:
  GET  /app/health             — liveness + DB check (open)
"""

import logging
import time
from pathlib import PurePosixPath
from urllib.parse import parse_qs, urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes, throttle_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from Services.agent import query as rag_query
from Services.Ai_service.embedding import delete_file_vectors
from Services.Ai_service.load_data import SUPPORTED_EXTENSIONS as DOC_EXTENSIONS
from Services.Ai_service.video_transcibing import SUPPORTED_MEDIA_EXTENSIONS
from Services.storage import build_object_key, delete_object, is_key_in_workspace, save_upload

from .metrics_service import get_workspace_monitoring_stats, log_prediction_and_check_drift
from .models import ROLE_ADMIN, IngestedFile, MeetingAnalysis, PredictionLog, Workspace
from .permissions import IsAdmin, IsAdminOrEditor, IsAnyRole
from .serializers import RegisterSerializer, RoleUpdateSerializer, UserSerializer, WorkspaceSerializer
from .tasks import run_ingestion_task, run_youtube_ingestion_task
from .throttling import AuthRateThrottle, CostControlRoleThrottle
from .utils import resolve_workspace

logger        = logging.getLogger(__name__)
User          = get_user_model()
OBJECT_STORAGE_BUCKET = settings.OBJECT_STORAGE_BUCKET


def _allowed_extensions() -> set[str]:
    """Documents always; audio/video only when the optional Meetings feature is enabled."""
    return DOC_EXTENSIONS | SUPPORTED_MEDIA_EXTENSIONS if settings.ENABLE_MEETINGS else set(DOC_EXTENSIONS)

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


# ─────────────────────────────────────────────────────────────────────────────
# OPS — GET /app/health   (open; used by Docker / load-balancer healthchecks)
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    """Liveness + DB connectivity check. Returns 503 if the DB is unreachable."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        logger.exception("Health check: database unreachable")
        return Response({"status": "error", "database": "unreachable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response({"status": "ok", "database": "ok"}, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────────
# AUTH — open endpoints (no JWT required)
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthRateThrottle])
def register(request):
    """
    POST /auth/register
    Body: { "email": "...", "password": "...", "password2": "..." }
    New accounts are always viewers; an admin promotes them via
    PATCH /auth/users/<id>/role.
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
@throttle_classes([AuthRateThrottle])
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


@api_view(["PATCH"])
@permission_classes([IsAdmin])
def set_user_role(request, user_id):
    """
    PATCH /auth/users/<id>/role   [admin only]
    Body: { "role": "viewer|editor|admin" }
    """
    serializer = RoleUpdateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        target = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

    new_role = serializer.validated_data["role"]
    # Stop an admin from locking themselves out
    if target.id == request.user.id and new_role != ROLE_ADMIN:
        return Response({"error": "Admins cannot remove their own admin role"}, status=status.HTTP_400_BAD_REQUEST)

    group, _ = Group.objects.get_or_create(name=new_role)
    target.groups.set([group])
    logger.info("User %s changed role of %s to %s", request.user.email, target.email, new_role)
    return Response(UserSerializer(target).data, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────────
# Shared ingestion helper
# ─────────────────────────────────────────────────────────────────────────────

def _run_ingestion(s3_key: str, user, workspace_id: int, original_filename: str | None = None) -> Response:
    """
    Shared logic: check backpressure, create DB record in PENDING state,
    enqueue to Celery, and return 202 Accepted.
    """
    try:
        workspace = user.workspaces.get(id=workspace_id)
    except (Workspace.DoesNotExist, ValueError, TypeError):
        return Response({"error": "Workspace not found or access denied"}, status=status.HTTP_403_FORBIDDEN)

    # Keys must sit under this workspace's prefix: blocks path traversal
    # ("../../x.pdf") and ingesting another tenant's objects.
    if not is_key_in_workspace(s3_key, workspace.id):
        return Response(
            {"error": f"s3_key must be inside this workspace (prefix 'ws_{workspace.id}/')"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    ext = PurePosixPath(s3_key).suffix.lower()

    if ext not in _allowed_extensions():
        return Response(
            {"error": f"Unsupported file type '{ext}'", "supported": sorted(_allowed_extensions())},
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
        original_filename = original_filename or PurePosixPath(s3_key).name,
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
                "original_filename": file_obj.original_filename,
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
    Body: { "s3_key": "ws_1/path/to/file.pdf", "workspace_id": 1 }
    File must already exist in storage, under the workspace's prefix.
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
    Saves the file under ws_<id>/<uuid>_<filename>, then runs the same
    ingestion pipeline as /ai/upload.
    """
    file_obj = request.FILES.get("file")
    if not file_obj:
        return Response({"error": "No file provided. Send as multipart form-data with key 'file'."}, status=status.HTTP_400_BAD_REQUEST)

    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if file_obj.size > max_bytes:
        return Response(
            {"error": f"File too large (max {settings.MAX_UPLOAD_MB} MB)"},
            status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )

    original_name = file_obj.name
    ext = PurePosixPath(original_name).suffix.lower()

    if ext not in _allowed_extensions():
        return Response(
            {"error": f"Unsupported file type '{ext}'", "supported": sorted(_allowed_extensions())},
            status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )

    # Authorise the workspace BEFORE writing anything to storage
    workspace_id, error_response = resolve_workspace(request, request.data)
    if error_response:
        return error_response

    # Unique per-workspace key: two tenants uploading "report.pdf" never collide
    s3_key = build_object_key(workspace_id, original_name)

    if not save_upload(file_obj, s3_key):
        return Response({"error": f"Storage upload failed for {original_name}"}, status=status.HTTP_502_BAD_GATEWAY)

    response = _run_ingestion(s3_key, request.user, workspace_id, original_filename=original_name)
    if response.status_code != status.HTTP_202_ACCEPTED:
        delete_object(s3_key)  # don't leave orphaned uploads behind
    return response


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
    question = str(request.data.get("question", "")).strip()
    if not question:
        return Response({"error": "question is required"}, status=status.HTTP_400_BAD_REQUEST)
    if len(question) > settings.MAX_QUESTION_CHARS:
        return Response(
            {"error": f"question is too long (max {settings.MAX_QUESTION_CHARS} characters)"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    workspace_id, error_response = resolve_workspace(request, request.data)
    if error_response:
        return error_response

    kwargs = {}
    top_k = request.data.get("top_k")
    if top_k is not None:
        try:
            top_k = int(top_k)
        except (ValueError, TypeError):
            return Response({"error": "top_k must be an integer"}, status=status.HTTP_400_BAD_REQUEST)
        if not 1 <= top_k <= settings.MAX_TOP_K:
            return Response(
                {"error": f"top_k must be between 1 and {settings.MAX_TOP_K}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        kwargs["top_k"] = top_k

    # Daily per-user cap on LLM-backed queries. Admins are exempt.
    if not request.user.has_role(ROLE_ADMIN):
        day_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        used_today = PredictionLog.objects.filter(user=request.user, timestamp__gte=day_start).count()
        if used_today >= settings.DAILY_QUERY_QUOTA:
            return Response(
                {"error": f"Daily query limit reached ({settings.DAILY_QUERY_QUOTA}). Try again tomorrow."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

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
    DELETE /app/ai/files/delete
    Body: { "file_id": 12 }   (or legacy { "s3_key": "ws_1/..." })

    Removes the file's vectors from Qdrant, the stored object, and the DB
    record, in that order. If the vector delete fails nothing else is
    touched, so the request can simply be retried.
    """
    file_id = request.data.get("file_id")
    s3_key  = str(request.data.get("s3_key", "")).strip()
    if not file_id and not s3_key:
        return Response({"error": "file_id or s3_key is required"}, status=status.HTTP_400_BAD_REQUEST)

    # Only search the caller's own workspaces: another tenant's file looks
    # exactly like a file that doesn't exist.
    files = IngestedFile.objects.filter(workspace__in=request.user.workspaces.all())
    try:
        file_obj = files.get(id=int(file_id)) if file_id else files.get(object_key=s3_key)
    except (IngestedFile.DoesNotExist, ValueError, TypeError):
        return Response({"error": "File not found"}, status=status.HTTP_404_NOT_FOUND)

    if file_obj.status in ("PENDING", "PROCESSING"):
        # A worker could still write vectors after we delete them
        return Response(
            {"error": "File is still being ingested. Try again once it finishes."},
            status=status.HTTP_409_CONFLICT,
        )

    try:
        delete_file_vectors(file_obj.id, file_obj.workspace_id)
    except Exception:
        logger.exception("Failed to delete vectors for file #%d", file_obj.id)
        return Response({"error": "Could not delete vectors; file was not removed"}, status=status.HTTP_502_BAD_GATEWAY)

    delete_object(file_obj.object_key)
    name = file_obj.original_filename or file_obj.object_key
    file_obj.delete()
    return Response({"message": f"'{name}' removed successfully"}, status=status.HTTP_200_OK)


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

def _youtube_video_id(parsed) -> str:
    if parsed.hostname == "youtu.be":
        return parsed.path.lstrip("/")
    return parse_qs(parsed.query).get("v", [""])[0]


@api_view(["POST"])
@permission_classes([IsAdminOrEditor])
@throttle_classes([CostControlRoleThrottle])
def ingest_youtube(request):
    """
    POST /app/ai/meetings/ingest-youtube
    Body: { "url": "https://www.youtube.com/watch?v=...", "workspace_id": 1 }
    Queues download + Whisper transcription + embedding on a Celery worker
    and returns 202 immediately; poll GET /app/ai/files for the status.
    """
    url = request.data.get("url", "").strip()
    parsed = urlparse(url)
    video_id = _youtube_video_id(parsed) if parsed.hostname in YOUTUBE_HOSTS else ""
    if parsed.scheme not in ("http", "https") or not video_id:
        return Response(
            {"error": "Valid YouTube URL is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    workspace_id, error_resp = resolve_workspace(request, request.data)
    if error_resp:
        return error_resp

    workspace = request.user.workspaces.get(id=workspace_id)
    file_obj = IngestedFile.objects.create(
        object_bucket=OBJECT_STORAGE_BUCKET,
        object_key=build_object_key(workspace.id, f"youtube_{video_id}.mp3"),
        original_filename=f"YouTube_{video_id}",
        file_type="mp3",
        document_category="meeting",
        uploaded_by=request.user,
        workspace=workspace,
        status="PENDING",
    )

    task = run_youtube_ingestion_task.delay(url, request.user.id, workspace.id, file_obj.id)

    return Response(
        {
            "message": "YouTube ingestion queued.",
            "task_id": task.id,
            "file_id": file_obj.id,
            "status": file_obj.status,
        },
        status=status.HTTP_202_ACCEPTED,
    )


@api_view(["GET"])
@permission_classes([IsAnyRole])
def get_meeting_analysis(request, file_id):
    """
    GET /app/ai/meetings/<file_id>/analysis
    Returns the MeetingAnalysis details for an ingested meeting file.
    Only members of the file's workspace can read it.
    """
    try:
        analysis = MeetingAnalysis.objects.get(
            file_id=file_id,
            file__workspace__in=request.user.workspaces.all(),
        )
    except MeetingAnalysis.DoesNotExist:
        return Response(
            {"error": "Meeting analysis is still processing or not found for this file."},
            status=status.HTTP_404_NOT_FOUND,
        )

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
