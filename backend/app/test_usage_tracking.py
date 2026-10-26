"""
Tests — per-query token accounting. Offline: the collector is fed synthetic LLM
results, so nothing here calls Groq.
"""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from Services.agent import UsageCollector

from .metrics_service import get_workspace_monitoring_stats
from .models import PredictionLog
from .tests import _get_token, _make_user

PW = "Pass1234!"


def _llm_result(prompt=0, completion=0, via_message=False):
    """Mimic a LangChain LLMResult, either flavour of usage reporting."""
    if via_message:
        message = SimpleNamespace(usage_metadata={"input_tokens": prompt, "output_tokens": completion})
        return SimpleNamespace(llm_output=None, generations=[[SimpleNamespace(message=message)]])
    return SimpleNamespace(
        llm_output={"token_usage": {"prompt_tokens": prompt, "completion_tokens": completion}},
        generations=[[SimpleNamespace(message=SimpleNamespace(usage_metadata=None))]],
    )


class UsageCollectorTests(TestCase):

    def test_totals_accumulate_across_the_calls_one_query_makes(self):
        c = UsageCollector()
        c.on_llm_end(_llm_result(100, 20))
        c.on_llm_end(_llm_result(250, 40))
        c.on_llm_end(_llm_result(80, 10))
        self.assertEqual(c.as_dict(), {"llm_calls": 3, "prompt_tokens": 430, "completion_tokens": 70})

    def test_usage_metadata_on_the_message_is_also_read(self):
        c = UsageCollector()
        c.on_llm_end(_llm_result(12, 3, via_message=True))
        self.assertEqual(c.as_dict(), {"llm_calls": 1, "prompt_tokens": 12, "completion_tokens": 3})

    def test_the_model_behind_each_call_is_recorded(self):
        """The fallback can substitute a second model; a report must be able to tell."""
        c = UsageCollector()
        primary = _llm_result(10, 2)
        primary.llm_output["model_name"] = "openai/gpt-oss-20b"
        fallback = _llm_result(10, 2)
        fallback.llm_output["model_name"] = "openai/gpt-oss-120b"
        c.on_llm_end(primary)
        c.on_llm_end(fallback)
        self.assertEqual(c.models, {"openai/gpt-oss-20b", "openai/gpt-oss-120b"})

    def test_a_response_with_no_usage_still_counts_the_call(self):
        c = UsageCollector()
        c.on_llm_end(SimpleNamespace(llm_output=None, generations=[]))
        self.assertEqual(c.as_dict(), {"llm_calls": 1, "prompt_tokens": 0, "completion_tokens": 0})


class QueryUsageTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = _make_user("usage@test.com", PW, "admin")
        self.ws = self.user.workspaces.first().id
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {_get_token(self.client, 'usage@test.com', PW)}"}

    def _query(self, result):
        with patch("app.views.rag_query", return_value=result):
            return self.client.post("/app/ai/query",
                                    {"question": "hi", "workspace_id": self.ws},
                                    content_type="application/json", **self.auth)

    def test_token_usage_is_persisted_with_the_prediction(self):
        resp = self._query({"answer": "ok", "confidence": 0.8,
                            "usage": {"llm_calls": 4, "prompt_tokens": 900, "completion_tokens": 120}})
        self.assertEqual(resp.status_code, 200)
        log = PredictionLog.objects.get()
        self.assertEqual((log.llm_calls, log.prompt_tokens, log.completion_tokens), (4, 900, 120))

    def test_a_result_without_usage_records_zeros_rather_than_failing(self):
        """Older callers and the refusal path may not report usage at all."""
        self.assertEqual(self._query({"answer": "ok", "confidence": 0.8}).status_code, 200)
        log = PredictionLog.objects.get()
        self.assertEqual((log.llm_calls, log.prompt_tokens, log.completion_tokens), (0, 0, 0))

    def test_monitoring_sums_usage_and_counts_refusals(self):
        self._query({"answer": "a", "confidence": 0.9,
                     "usage": {"llm_calls": 3, "prompt_tokens": 1000, "completion_tokens": 200}})
        # A refusal in agentic mode has already paid for the decomposition call, so
        # it is counted by its own flag rather than by having spent no tokens.
        self._query({"answer": "refused", "confidence": 0.1, "refused": True,
                     "usage": {"llm_calls": 1, "prompt_tokens": 239, "completion_tokens": 68}})

        stats = get_workspace_monitoring_stats(self.ws)
        self.assertEqual(stats["llm_calls"], 4)
        self.assertEqual(stats["prompt_tokens"], 1239)
        self.assertEqual(stats["completion_tokens"], 268)
        self.assertEqual(stats["refused_queries"], 1)

    def test_a_refused_query_is_flagged_as_such(self):
        self._query({"answer": "no", "confidence": 0.1, "refused": True,
                     "usage": {"llm_calls": 1, "prompt_tokens": 10, "completion_tokens": 2}})
        self.assertTrue(PredictionLog.objects.get().refused)

    def test_an_answered_query_is_not_flagged_refused(self):
        self._query({"answer": "yes", "confidence": 0.9,
                     "usage": {"llm_calls": 3, "prompt_tokens": 10, "completion_tokens": 2}})
        self.assertFalse(PredictionLog.objects.get().refused)

    @override_settings(LLM_INPUT_COST_PER_MTOK=0.1, LLM_OUTPUT_COST_PER_MTOK=0.5)
    def test_cost_is_computed_from_the_configured_rates(self):
        self._query({"answer": "a", "confidence": 0.9,
                     "usage": {"llm_calls": 1, "prompt_tokens": 1_000_000, "completion_tokens": 2_000_000}})
        stats = get_workspace_monitoring_stats(self.ws)
        self.assertAlmostEqual(stats["estimated_cost_usd"], 0.1 + 1.0, places=6)
        self.assertTrue(stats["cost_rates_configured"])

    @override_settings(LLM_INPUT_COST_PER_MTOK=0.0, LLM_OUTPUT_COST_PER_MTOK=0.0)
    def test_unset_rates_report_zero_rather_than_an_invented_price(self):
        self._query({"answer": "a", "confidence": 0.9,
                     "usage": {"llm_calls": 1, "prompt_tokens": 5000, "completion_tokens": 500}})
        stats = get_workspace_monitoring_stats(self.ws)
        self.assertEqual(stats["estimated_cost_usd"], 0.0)
        self.assertFalse(stats["cost_rates_configured"])
        self.assertEqual(stats["prompt_tokens"], 5000)   # tokens are still the real measurement
