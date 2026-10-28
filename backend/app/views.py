"""
API views

Auth endpoints:
  POST /auth/register          — create account (open)
  POST /auth/login             — get JWT tokens (open)
  POST /auth/token/refresh     — refresh access token (open)
  GET  /auth/me                — current user info (authenticated)
  GET/POST /auth/workspaces    — list / create workspaces (creator becomes its admin)
  GET/POST /auth/workspaces/<id>/members          — list / add members [admin to add]
  PATCH/DELETE /auth/workspaces/<id>/members/<uid> — change role / remove [admin; members may leave]

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

from . import answer_cache
from .metrics_service import get_workspace_monitoring_stats, log_prediction_and_check_drift
from .models import (
    EDIT_ROLES,
    ROLE_ADMIN,
    IngestedFile,
    MeetingAnalysis,
    Membership,
    PredictionLog,
    Workspace,
)
from .permissions import IsAnyRole
from .serializers import (
    MemberAddSerializer,
    MemberSerializer,
    RegisterSerializer,
    RoleUpdateSerializer,
    UserSerializer,
    WorkspaceCreateSerializer,
    WorkspaceSerializer,
)
from .tasks import run_ingestion_task, run_youtube_ingestion_task
from .throttling import AuthRateThrottle, CostControlRoleThrottle, workspace_retry_after
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
    The new user becomes admin of their own personal workspace and has no access
    to anyone else's until that workspace's admin adds them.
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


def _admin_count(workspace_id: int) -> int:
    return Membership.objects.filter(workspace_id=workspace_id, role=ROLE_ADMIN).count()


@api_view(["GET", "POST"])
@permission_classes([IsAnyRole])
def workspaces(request):
    """
    GET  /auth/workspaces  — workspaces the caller belongs to, each with their role.
    POST /auth/workspaces  — create a workspace (e.g. a project group); caller becomes its admin.
                             Body: { "name": "Payments team" }
    """
    if request.method == "GET":
        qs = request.user.workspaces.order_by("id")
        return Response(WorkspaceSerializer(qs, many=True, context={"user": request.user}).data)

    serializer = WorkspaceCreateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    if request.user.memberships.filter(role=ROLE_ADMIN).count() >= settings.MAX_WORKSPACES_PER_USER:
        return Response(
            {"error": f"You can administer at most {settings.MAX_WORKSPACES_PER_USER} workspaces."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    workspace = Workspace.objects.create(name=serializer.validated_data["name"].strip())
    workspace.add_member(request.user, ROLE_ADMIN)
    return Response(
        WorkspaceSerializer(workspace, context={"user": request.user}).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET", "POST"])
@permission_classes([IsAnyRole])
def workspace_members(request, workspace_id):
    """
    GET  /auth/workspaces/<id>/members  — any member can see who is in the workspace.
    POST /auth/workspaces/<id>/members  — [admin] add an already-registered user.
                                          Body: { "email": "...", "role": "viewer|editor|admin" }
    """
    if request.method == "GET":
        wid, error = resolve_workspace(request, {"workspace_id": workspace_id})
        if error:
            return error
        members = Membership.objects.filter(workspace_id=wid).select_related("user").order_by("id")
        return Response(MemberSerializer(members, many=True).data)

    wid, error = resolve_workspace(request, {"workspace_id": workspace_id}, roles=(ROLE_ADMIN,))
    if error:
        return error
    serializer = MemberAddSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    email = serializer.validated_data["email"].strip().lower()
    try:
        target = User.objects.get(email__iexact=email, is_active=True)
    except User.DoesNotExist:
        return Response(
            {"error": "No account with that email. Ask them to sign up first, then add them."},
            status=status.HTTP_404_NOT_FOUND,
        )
    if Membership.objects.filter(workspace_id=wid, user=target).exists():
        return Response({"error": "Already a member. Use PATCH to change their role."}, status=status.HTTP_409_CONFLICT)
    membership = Workspace.objects.get(id=wid).add_member(target, serializer.validated_data["role"])
    logger.info("%s added %s to workspace %s as %s", request.user.email, target.email, wid, membership.role)
    return Response(MemberSerializer(membership).data, status=status.HTTP_201_CREATED)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAnyRole])
def workspace_member(request, workspace_id, user_id):
    """
    PATCH  /auth/workspaces/<id>/members/<user_id>  — [admin] change role. Body: { "role": "..." }
    DELETE /auth/workspaces/<id>/members/<user_id>  — [admin] remove a member, or any member leaving.
    A workspace always keeps at least one admin.
    """
    leaving = request.method == "DELETE" and user_id == request.user.id
    wid, error = resolve_workspace(
        request, {"workspace_id": workspace_id}, roles=None if leaving else (ROLE_ADMIN,)
    )
    if error:
        return error
    try:
        membership = Membership.objects.select_related("user").get(workspace_id=wid, user_id=user_id)
    except Membership.DoesNotExist:
        return Response({"error": "Not a member of this workspace"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "PATCH":
        serializer = RoleUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        new_role = serializer.validated_data["role"]
        if membership.role == ROLE_ADMIN and new_role != ROLE_ADMIN and _admin_count(wid) <= 1:
            return Response({"error": "A workspace needs at least one admin."}, status=status.HTTP_400_BAD_REQUEST)
        membership.role = new_role
        membership.save(update_fields=["role"])
        logger.info("%s set %s to %s in workspace %s", request.user.email, membership.user.email, new_role, wid)
        return Response(MemberSerializer(membership).data)

    if membership.role == ROLE_ADMIN and _admin_count(wid) <= 1:
        return Response(
            {"error": "The last admin cannot leave. Promote someone else first."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    membership.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


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
    # Per workspace first, so one tenant's bulk upload cannot fill the shared
    # queue and turn every other tenant's uploads into 503s. 429, not 503: the
    # service is fine, this workspace has simply reached its share.
    in_flight = IngestedFile.objects.filter(workspace=workspace, status__in=['PENDING', 'PROCESSING']).count()
    if in_flight >= settings.MAX_INGESTION_PER_WORKSPACE:
        return Response(
            {"error": f"This workspace already has {in_flight} documents being processed "
                      f"(limit {settings.MAX_INGESTION_PER_WORKSPACE}). Upload more once some finish."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": "30"},
        )

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
@permission_classes([IsAnyRole])
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

    workspace_id, error_response = resolve_workspace(request, request.data, roles=EDIT_ROLES)
    if error_response:
        return error_response

    return _run_ingestion(s3_key, request.user, workspace_id)


# ─────────────────────────────────────────────────────────────────────────────
# AI — POST /app/ai/upload-direct   [editor, admin only]
# Upload a file from the browser directly — saves to S3 then ingests
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAnyRole])
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
    workspace_id, error_response = resolve_workspace(request, request.data, roles=EDIT_ROLES)
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

    # A repeat of a question this workspace has already asked, against the same
    # documents, comes from the cache: no retrieval, no LLM call, no quota used.
    cache_key = None
    if answer_cache.enabled():
        lookup_started = time.time()
        cached, cache_key = answer_cache.get(workspace_id, question, kwargs.get("top_k"))
        if cached is not None:
            result = {**cached, "cached": True,
                      "usage": {"llm_calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "models": []}}
            log_prediction_and_check_drift(
                workspace_id=workspace_id, user=request.user, question=question, result=result,
                response_time_ms=int((time.time() - lookup_started) * 1000), cache_hit=True,
            )
            return Response(result, status=status.HTTP_200_OK)

    # The workspace's shared allowance, after the cache (a hit costs nothing) and
    # after resolve_workspace (so nobody can spend another tenant's allowance).
    retry_after = workspace_retry_after(workspace_id)
    if retry_after:
        return Response(
            {"error": "This workspace is asking questions faster than its shared limit allows. "
                      f"Try again in {retry_after} s."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(retry_after)},
        )

    # Daily per-user cap on LLM-backed queries. No role is exempt: every sign-up is
    # admin of their own workspace, so an exemption would be an open cost hole.
    user_role = request.user.role_in(workspace_id)
    day_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    used_today = PredictionLog.objects.filter(
        user=request.user, timestamp__gte=day_start, cache_hit=False
    ).count()
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
            user_role=user_role,
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

    if cache_key:
        answer_cache.put(cache_key, result)
    result["cached"] = False
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
@permission_classes([IsAnyRole])
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
    # and only workspaces where they are an editor or admin may delete.
    files = IngestedFile.objects.filter(
        workspace__memberships__user=request.user, workspace__memberships__role__in=EDIT_ROLES
    )
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
    answer_cache.bump_corpus_version(file_obj.workspace_id)
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
# AI — GET /app/ai/monitoring   [workspace editor, admin only]
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsAnyRole])
def get_monitoring_stats(request):
    """
    GET /app/ai/monitoring
    Query params: workspace_id=1
    Returns aggregated metrics for the dashboard.
    """
    workspace_id, error_response = resolve_workspace(request, request.query_params, roles=EDIT_ROLES)
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
@permission_classes([IsAnyRole])
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

    workspace_id, error_resp = resolve_workspace(request, request.data, roles=EDIT_ROLES)
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
