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

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from decouple import config
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

    if IngestedFile.objects.filter(s3_bucket=S3_BUCKET, s3_key=s3_key).exists():
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
        s3_bucket      = S3_BUCKET,
        s3_key         = s3_key,
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
                "s3_key": file_obj.s3_key,
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

    workspace_id = request.data.get("workspace_id")
    if not workspace_id:
        first_ws = request.user.workspaces.first()
        if not first_ws:
            return Response({"error": "No workspace available."}, status=status.HTTP_400_BAD_REQUEST)
        workspace_id = first_ws.id

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
    try:
        s3 = _get_s3()
        s3.upload_fileobj(file_obj, S3_BUCKET, s3_key)
        logger.info("Uploaded '%s' to s3://%s/%s", original_name, S3_BUCKET, s3_key)
    except (ClientError, BotoCoreError) as e:
        logger.exception("S3 upload failed for '%s'", original_name)
        return Response({"error": f"S3 upload failed: {str(e)}"}, status=status.HTTP_502_BAD_GATEWAY)

    # Now ingest from S3
    workspace_id = request.data.get("workspace_id")
    if not workspace_id:
        first_ws = request.user.workspaces.first()
        if not first_ws:
            return Response({"error": "No workspace available."}, status=status.HTTP_400_BAD_REQUEST)
        workspace_id = first_ws.id

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

    workspace_id = request.data.get("workspace_id")
    if not workspace_id:
        first_ws = request.user.workspaces.first()
        if not first_ws:
            return Response({"error": "No workspace available."}, status=status.HTTP_400_BAD_REQUEST)
        workspace_id = first_ws.id
    else:
        try:
            workspace_id = int(workspace_id)
        except (ValueError, TypeError):
            return Response({"error": "workspace_id must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

        if not request.user.workspaces.filter(id=workspace_id).exists():
            return Response({"error": "Workspace not found or access denied"}, status=status.HTTP_403_FORBIDDEN)

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

    # Log prediction
    confidence = result.get("confidence") if result else None
    prediction_text = result.get("answer") if result else ""
    user = request.user if request.user.is_authenticated else None

    PredictionLog.objects.create(
        workspace_id=workspace_id,
        user=user,
        input_text=question,
        prediction_text=prediction_text,
        response_time_ms=response_time_ms,
        confidence=confidence,
        error_msg=error_msg,
    )

    # Simple Drift Check & Email Alert (e.g. run every 50 queries)
    # Get last 50 queries for this workspace
    recent_logs = list(PredictionLog.objects.filter(workspace_id=workspace_id, confidence__isnull=False).order_by('-id')[:50])
    if len(recent_logs) >= 50:
        avg_confidence = sum(log.confidence for log in recent_logs) / 50.0
        # Assume drift if avg confidence drops below 0.35 (just an arbitrary threshold for the assignment)
        if avg_confidence < 0.35:
            # Check if we already logged drift recently
            recent_drift = DriftLog.objects.filter(workspace_id=workspace_id, timestamp__gte=timezone.now() - timedelta(hours=1)).exists()
            if not recent_drift:
                DriftLog.objects.create(
                    workspace_id=workspace_id,
                    drift_score=avg_confidence,
                    is_drift_detected=True,
                    reference_count=50,
                    current_count=50,
                )
                workspace = Workspace.objects.get(id=workspace_id)
                admin_emails = list(workspace.members.filter(groups__name="admin").values_list("email", flat=True))
                send_drift_alert(workspace.name, avg_confidence, admin_emails)

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
    workspace_id = request.query_params.get("workspace_id")
    if not workspace_id:
        first_ws = request.user.workspaces.first()
        if not first_ws:
            return Response({"files": [], "total": 0}, status=status.HTTP_200_OK)
        workspace_id = first_ws.id
    else:
        try:
            workspace_id = int(workspace_id)
        except (ValueError, TypeError):
            return Response({"error": "workspace_id must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

        if not request.user.workspaces.filter(id=workspace_id).exists():
            return Response({"error": "Workspace not found or access denied"}, status=status.HTTP_403_FORBIDDEN)

    files = list(
        IngestedFile.objects.filter(workspace_id=workspace_id).values(
            "id", "s3_key", "file_type", "chunks_stored", "status", "error_message", "ingested_at", "uploaded_by__email"
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
    DELETE /app/ai/files/delete (actually mapped to DELETE /app/ai/files/delete or /app/ai/files)
    Body: { "s3_key": "uploads/report.pdf" }
    Removes the DB record so the file can be re-ingested.
    Does NOT delete from S3 or Qdrant (vectors remain but are orphaned).
    """
    s3_key = request.data.get("s3_key", "").strip()
    if not s3_key:
        return Response({"error": "s3_key is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        file_obj = IngestedFile.objects.get(s3_bucket=S3_BUCKET, s3_key=s3_key)
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
    workspace_id = request.query_params.get("workspace_id")
    if not workspace_id:
        first_ws = request.user.workspaces.first()
        if not first_ws:
            return Response({"error": "No workspace available."}, status=status.HTTP_400_BAD_REQUEST)
        workspace_id = first_ws.id
    else:
        try:
            workspace_id = int(workspace_id)
        except (ValueError, TypeError):
            return Response({"error": "workspace_id must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

        if not request.user.workspaces.filter(id=workspace_id).exists():
            return Response({"error": "Workspace not found or access denied"}, status=status.HTTP_403_FORBIDDEN)

    predictions = PredictionLog.objects.filter(workspace_id=workspace_id)
    total_predictions = predictions.count()
    error_count = predictions.filter(error_msg__isnull=False).count()
    avg_latency = predictions.aggregate(Avg("response_time_ms"))["response_time_ms__avg"] or 0
    avg_confidence = predictions.aggregate(Avg("confidence"))["confidence__avg"] or 0

    # Predictions per day (last 7 days)
    seven_days_ago = timezone.now() - timedelta(days=7)
    recent_predictions = predictions.filter(timestamp__gte=seven_days_ago)
    
    # We'll group manually to avoid DB-specific datetime truncation issues
    per_day_counts = {}
    for i in range(7):
        d = (timezone.now() - timedelta(days=i)).date()
        per_day_counts[d.isoformat()] = 0
        
    for p in recent_predictions:
        d_str = p.timestamp.date().isoformat()
        if d_str in per_day_counts:
            per_day_counts[d_str] += 1

    chart_data = [{"date": k, "count": v} for k, v in sorted(per_day_counts.items())]

    recent_drifts = list(
        DriftLog.objects.filter(workspace_id=workspace_id)
        .order_by("-timestamp")
        .values("id", "drift_score", "timestamp")[:5]
    )

    return Response({
        "total_predictions": total_predictions,
        "error_count": error_count,
        "avg_latency": round(avg_latency, 2),
        "avg_confidence": round(avg_confidence, 4),
        "chart_data": chart_data,
        "recent_drifts": recent_drifts,
    }, status=status.HTTP_200_OK)



