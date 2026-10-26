"""
Tests — the LLM client's reliability settings. Offline: nothing here calls Groq,
it only inspects how the client is configured.
"""

from unittest.mock import patch

from django.test import TestCase
from Services import agent


class LlmClientTests(TestCase):

    def setUp(self):
        agent._llm = None  # the client is a module-level singleton
        self.addCleanup(setattr, agent, "_llm", None)
        key = patch.dict("os.environ", {"GROQ_API_KEY": "test-key-not-used"})
        key.start()
        self.addCleanup(key.stop)

    def test_primary_is_backed_by_a_fallback_model(self):
        llm = agent._get_llm()
        self.assertTrue(getattr(llm, "fallbacks", ()), "expected a fallback chain")
        self.assertEqual(llm.runnable.model_name, agent.GROQ_MODEL)
        self.assertEqual(llm.fallbacks[0].model_name, agent.GROQ_FALLBACK_MODEL)

    def test_no_fallback_chain_when_both_models_are_the_same(self):
        with patch.object(agent, "GROQ_FALLBACK_MODEL", agent.GROQ_MODEL):
            llm = agent._get_llm()
        self.assertFalse(getattr(llm, "fallbacks", ()))
        self.assertEqual(llm.model_name, agent.GROQ_MODEL)

    def test_requests_time_out_and_retry(self):
        """A hung Groq connection must not hold a gunicorn worker open forever."""
        client = agent._build_llm("openai/gpt-oss-20b")
        self.assertEqual(client.request_timeout, agent.LLM_TIMEOUT_SECONDS)
        self.assertEqual(client.max_retries, agent.LLM_MAX_RETRIES)
        self.assertGreater(agent.LLM_TIMEOUT_SECONDS, 0)

    def test_default_model_is_one_groq_still_serves(self):
        """
        Groq retires models; a retired id makes every query fail. These two were
        checked against GET /openai/v1/models. If this fails, re-check that list.
        """
        self.assertIn(agent.GROQ_MODEL, {"openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b"})
        self.assertNotIn("llama-3.3-70b", agent.GROQ_MODEL)
