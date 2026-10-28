"""
Tests — the CloudWatch metrics the alarms in deploy/cloudformation.yml depend on.
CloudWatch silently ignores a malformed EMF line, and an alarm on a metric that
never arrives either never fires or always does, so the format is pinned here.
"""

import io
import json
from contextlib import redirect_stdout
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from . import observability
from .models import IngestedFile
from .tasks import publish_queue_metrics
from .test_fairness_and_cache import _register
from .tests import _make_user


def _captured(fn, *args, **kwargs):
    out = io.StringIO()
    with redirect_stdout(out):
        fn(*args, **kwargs)
    return [json.loads(line) for line in out.getvalue().splitlines() if line.startswith("{")]


@override_settings(EMIT_METRICS=True)
class EmfFormatTests(TestCase):

    def test_a_query_is_one_valid_emf_record(self):
        [record] = _captured(observability.record_query, 1234, error=False, cache_hit=True, tokens=900)

        spec = record["_aws"]["CloudWatchMetrics"][0]
        self.assertEqual(spec["Namespace"], "Arishem")
        self.assertEqual(spec["Dimensions"], [["Service"]])
        self.assertEqual(record["Service"], "api")
        # Every declared metric has a value at the top level, which is where CloudWatch looks.
        for metric in spec["Metrics"]:
            self.assertIn(metric["Name"], record)
        self.assertEqual(record["QueryLatency"], 1234)
        self.assertEqual(record["QueryCacheHit"], 1)
        self.assertEqual(record["QueryError"], 0)
        self.assertIsInstance(record["_aws"]["Timestamp"], int)

    def test_no_per_tenant_dimension(self):
        """Each dimension value is a separately billed metric; tenants must not multiply the bill."""
        [record] = _captured(observability.record_query, 10, error=False, cache_hit=False, tokens=0)
        self.assertNotIn("workspace_id", json.dumps(record["_aws"]))

    @patch("app.views.rag_query", side_effect=RuntimeError("Groq is down"))
    def test_a_failed_query_reports_an_error(self, _rag):
        from django.test import Client

        client = Client()
        user, auth = _register(client, "o@test.com")
        records = _captured(client.post, "/app/ai/query",
                            {"question": "q", "workspace_id": user["workspaces"][0]["id"]},
                            content_type="application/json", **auth)
        self.assertEqual([r["QueryError"] for r in records], [1])

    def test_queue_metrics_report_depth_and_the_oldest_waits_age(self):
        ws = _make_user("q@test.com", "Pass1234!", "admin").workspaces.first()
        old = IngestedFile.objects.create(object_bucket="b", object_key="ws/old.pdf", file_type="pdf",
                                          workspace=ws, status="PENDING")
        IngestedFile.objects.filter(id=old.id).update(ingested_at=timezone.now() - timedelta(minutes=5))
        IngestedFile.objects.create(object_bucket="b", object_key="ws/new.pdf", file_type="pdf",
                                    workspace=ws, status="PROCESSING")
        IngestedFile.objects.create(object_bucket="b", object_key="ws/done.pdf", file_type="pdf",
                                    workspace=ws, status="SUCCESS")

        [record] = _captured(publish_queue_metrics)

        self.assertEqual(record["Service"], "worker")
        self.assertEqual(record["IngestionInFlight"], 2)
        self.assertAlmostEqual(record["OldestPendingSeconds"], 300, delta=5)


class DisabledByDefaultTests(TestCase):

    def test_nothing_is_printed_unless_enabled(self):
        self.assertEqual(_captured(observability.record_query, 1, error=False, cache_hit=False, tokens=0), [])
