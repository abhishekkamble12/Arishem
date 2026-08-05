from datetime import timedelta
from django.utils import timezone
from django.db.models import Avg
from .models import PredictionLog, DriftLog, Workspace
from .alerting import send_drift_alert

def log_prediction_and_check_drift(workspace_id, user, question, result, response_time_ms, error_msg=None):
    """
    Logs the RAG prediction and synchronously checks for drift.
    (Ideally, the drift checking should be moved to a Celery task).
    """
    confidence = result.get("confidence") if result else None
    prediction_text = result.get("answer") if result else ""

    PredictionLog.objects.create(
        workspace_id=workspace_id,
        user=user,
        input_text=question,
        prediction_text=prediction_text,
        response_time_ms=response_time_ms,
        confidence=confidence,
        error_msg=error_msg,
    )

    if error_msg is None:
        _check_for_drift(workspace_id)

def _check_for_drift(workspace_id):
    recent_logs = list(PredictionLog.objects.filter(workspace_id=workspace_id, confidence__isnull=False).order_by('-id')[:50])
    if len(recent_logs) >= 50:
        avg_confidence = sum(log.confidence for log in recent_logs) / 50.0
        if avg_confidence < 0.35:
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

def get_workspace_monitoring_stats(workspace_id):
    predictions = PredictionLog.objects.filter(workspace_id=workspace_id)
    total_predictions = predictions.count()
    error_count = predictions.filter(error_msg__isnull=False).count()
    avg_latency = predictions.aggregate(Avg("response_time_ms"))["response_time_ms__avg"] or 0
    avg_confidence = predictions.aggregate(Avg("confidence"))["confidence__avg"] or 0

    seven_days_ago = timezone.now() - timedelta(days=7)
    recent_predictions = predictions.filter(timestamp__gte=seven_days_ago)
    
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

    return {
        "total_predictions": total_predictions,
        "error_count": error_count,
        "avg_latency": round(avg_latency, 2),
        "avg_confidence": round(avg_confidence, 4),
        "chart_data": chart_data,
        "recent_drifts": recent_drifts,
    }
