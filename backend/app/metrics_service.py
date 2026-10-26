from datetime import timedelta

from django.conf import settings
from django.db.models import Avg, Sum
from django.utils import timezone

from .alerting import send_drift_alert
from .models import ROLE_ADMIN, DriftLog, PredictionLog, Workspace


def log_prediction_and_check_drift(workspace_id, user, question, result, response_time_ms, error_msg=None):
    """
    Logs the RAG prediction and synchronously checks for drift.
    (Ideally, the drift checking should be moved to a Celery task).
    """
    confidence = result.get("confidence") if result else None
    prediction_text = result.get("answer") if result else ""
    usage = (result or {}).get("usage") or {}

    PredictionLog.objects.create(
        workspace_id=workspace_id,
        user=user,
        input_text=question,
        prediction_text=prediction_text,
        response_time_ms=response_time_ms,
        confidence=confidence,
        error_msg=error_msg,
        refused=bool((result or {}).get("refused")),
        llm_calls=usage.get("llm_calls", 0),
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
    )

    if error_msg is None:
        _check_for_drift(workspace_id)

def _check_for_drift(workspace_id):
    recent_logs = list(PredictionLog.objects.filter(workspace_id=workspace_id, confidence__isnull=False).order_by('-id')[:50])
    if len(recent_logs) >= 50:
        avg_confidence = sum(log.confidence for log in recent_logs) / 50.0
        if avg_confidence < settings.RAG_CONFIDENCE_THRESHOLD:
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
                # Roles live on Membership now, not Django groups. Filtering on
                # groups__name silently matched nobody, so alerts went nowhere.
                admin_emails = list(
                    workspace.memberships.filter(role=ROLE_ADMIN).values_list("user__email", flat=True)
                )
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

    usage = predictions.aggregate(
        llm_calls=Sum("llm_calls"),
        prompt_tokens=Sum("prompt_tokens"),
        completion_tokens=Sum("completion_tokens"),
    )
    prompt_tokens = usage["prompt_tokens"] or 0
    completion_tokens = usage["completion_tokens"] or 0
    # $0.00 until the operator sets the per-million-token rates; see settings.
    cost = (
        prompt_tokens * settings.LLM_INPUT_COST_PER_MTOK
        + completion_tokens * settings.LLM_OUTPUT_COST_PER_MTOK
    ) / 1_000_000

    # Refusals skip synthesis and self-critique. In agentic mode the decomposition
    # call has already happened, so this is a large saving, not a free one.
    refused = predictions.filter(refused=True).count()

    return {
        "total_predictions": total_predictions,
        "error_count": error_count,
        "avg_latency": round(avg_latency, 2),
        "avg_confidence": round(avg_confidence, 4),
        "chart_data": chart_data,
        "recent_drifts": recent_drifts,
        "llm_calls": usage["llm_calls"] or 0,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "estimated_cost_usd": round(cost, 6),
        "cost_rates_configured": bool(
            settings.LLM_INPUT_COST_PER_MTOK or settings.LLM_OUTPUT_COST_PER_MTOK
        ),
        "refused_queries": refused,
    }
