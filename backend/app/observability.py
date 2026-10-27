"""
Operational metrics, published as CloudWatch Embedded Metric Format (EMF).

Each call prints one JSON line to stdout. In production Docker's awslogs driver
ships stdout to CloudWatch Logs, and CloudWatch turns any line in this format into
metric data points, so the app needs no agent, no extra AWS permission beyond
writing its own logs, and no PutMetricData call on the request path. Alarms on
these metrics are defined in deploy/cloudformation.yml.

Off unless EMIT_METRICS is set: in development the JSON lines would only be noise.

Metrics carry one dimension, Service. Not the workspace: every distinct dimension
value is a separate custom metric billed at $0.30/month, so a per-tenant
dimension would make the monitoring bill grow with the customer count.
"""

import json
import sys
import time

from django.conf import settings

NAMESPACE = "Arishem"


def emit(service: str, unit_by_metric: dict[str, str], values: dict[str, float]) -> None:
    """Publish values (one per metric in unit_by_metric) for one event."""
    if not settings.EMIT_METRICS:
        return
    record = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [{
                "Namespace": NAMESPACE,
                "Dimensions": [["Service"]],
                "Metrics": [{"Name": name, "Unit": unit} for name, unit in unit_by_metric.items()],
            }],
        },
        "Service": service,
        **values,
    }
    # Straight to stdout, not through logging: CloudWatch only parses a log event
    # that is the JSON object alone, and the log formatter would prefix it.
    sys.stdout.write(json.dumps(record) + "\n")
    sys.stdout.flush()


_QUERY_UNITS = {
    "QueryLatency": "Milliseconds",
    "QueryError": "Count",
    "QueryCacheHit": "Count",
    "QueryTokens": "Count",
}


def record_query(response_time_ms: int, error: bool, cache_hit: bool, tokens: int) -> None:
    """One answered (or failed) question. Error and CacheHit are 0/1, so their Average is a rate."""
    emit("api", _QUERY_UNITS, {
        "QueryLatency": response_time_ms,
        "QueryError": int(error),
        "QueryCacheHit": int(cache_hit),
        "QueryTokens": tokens,
    })


_QUEUE_UNITS = {"IngestionInFlight": "Count", "OldestPendingSeconds": "Seconds"}


def record_ingestion_queue(in_flight: int, oldest_pending_seconds: float) -> None:
    """
    Published every minute by the worker's beat schedule. Its absence is itself a
    signal: the "worker down" alarm fires when this metric stops arriving.
    """
    emit("worker", _QUEUE_UNITS, {
        "IngestionInFlight": in_flight,
        "OldestPendingSeconds": round(oldest_pending_seconds, 1),
    })
