"""
Tests — boot-time warm-up loads the slow dependencies, and never blocks start-up.
"""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from Services.warmup import warm_up


class WarmUpTests(SimpleTestCase):

    def test_loads_the_embedding_model_and_builds_the_llm_client(self):
        embeddings = MagicMock()
        with patch("Services.Ai_service.embedding.get_embeddings", return_value=embeddings), \
             patch("Services.agent._get_llm") as get_llm:
            warm_up()
        embeddings.embed_query.assert_called_once()
        get_llm.assert_called_once_with()

    def test_ingestion_workers_skip_the_llm_client(self):
        with patch("Services.Ai_service.embedding.get_embeddings"), \
             patch("Services.agent._get_llm") as get_llm:
            warm_up(include_llm=False)
        get_llm.assert_not_called()

    def test_a_failure_never_stops_the_worker_booting(self):
        """No GROQ_API_KEY yet must still give a server that answers /app/health."""
        with patch("Services.Ai_service.embedding.get_embeddings", side_effect=RuntimeError("no model")), \
             patch("Services.agent._get_llm", side_effect=ValueError("no GROQ_API_KEY")):
            elapsed = warm_up()  # must not raise
        self.assertGreaterEqual(elapsed, 0)

    def test_warm_up_makes_no_api_call(self):
        """Building the client is free; warming up must not spend tokens."""
        with patch("Services.Ai_service.embedding.get_embeddings"), \
             patch("Services.agent._get_llm") as get_llm:
            warm_up()
        get_llm.return_value.invoke.assert_not_called()


class GunicornHookTests(SimpleTestCase):

    def test_post_worker_init_warms_up(self):
        import importlib.util
        import os

        from django.conf import settings

        spec = importlib.util.spec_from_file_location(
            "gunicorn_conf", os.path.join(settings.BASE_DIR, "gunicorn.conf.py"))
        conf = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(conf)

        worker = MagicMock(pid=123)
        with patch("Services.warmup.warm_up", return_value=1.5) as warm:
            conf.post_worker_init(worker)
        warm.assert_called_once()
        worker.log.info.assert_called_once()
