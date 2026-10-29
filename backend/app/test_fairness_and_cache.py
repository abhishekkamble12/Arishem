"""
Tests — the answer cache and the per-workspace limits that keep one tenant from
crowding out the rest. Offline: the RAG call is a mock, the cache is in memory.
"""

from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from langchain_core.documents import Document
from rest_framework_simplejwt.tokens import RefreshToken

from . import answer_cache
from .models import IngestedFile, PredictionLog, User, Workspace
from .tasks import run_ingestion_task
from .tests import _make_user


def _register(_client, email):
    """
    A user who is admin of their own workspace, and auth headers for them. Made
    directly rather than through /auth/register, whose per-IP throttle is shared
    by every test in the run.
    """
    user = _make_user(email, "Pass1234!", "admin")
    data = {"id": user.id, "workspaces": [{"id": user.workspaces.first().id}]}
    return data, {"HTTP_AUTHORIZATION": f"Bearer {RefreshToken.for_user(user).access_token}"}


def _workspace_of(auth_user_email):
    return User.objects.get(email=auth_user_email).workspaces.first().id


ANSWER = {"answer": "20 days", "confidence": 0.4, "usage": {"llm_calls": 3, "prompt_tokens": 900,
                                                            "completion_tokens": 60, "models": ["m"]}}


class NormaliseTests(TestCase):

    def test_case_spacing_and_trailing_punctuation_are_folded(self):
        self.assertEqual(answer_cache.normalise_question("  How many PTO days?  "), "how many pto days")
        self.assertEqual(answer_cache.normalise_question("how   many pto\tdays"), "how many pto days")

    def test_punctuation_inside_the_question_is_kept(self):
        # Folding these would make different questions share an answer.
        self.assertNotEqual(answer_cache.normalise_question("Is the limit 5.5%?"),
                            answer_cache.normalise_question("Is the limit 55%?"))
        self.assertNotEqual(answer_cache.normalise_question("Is it -5 degrees?"),
                            answer_cache.normalise_question("Is it 5 degrees?"))


@override_settings(ANSWER_CACHE_TTL_SECONDS=60, WORKSPACE_QUERY_RATE="")
class AnswerCacheTests(TestCase):

    def setUp(self):
        cache.clear()
        self.client = Client()
        self.user, self.auth = _register(self.client, "c@test.com")
        self.ws = self.user["workspaces"][0]["id"]

    def _ask(self, question, auth=None, ws=None):
        return self.client.post("/app/ai/query", {"question": question, "workspace_id": ws or self.ws},
                                content_type="application/json", **(auth or self.auth))

    @patch("app.views.rag_query", return_value=dict(ANSWER))
    def test_a_repeated_question_is_answered_without_the_llm(self, rag):
        first = self._ask("How many PTO days do full-time employees get?").json()
        second = self._ask("how many pto days do full-time employees get").json()

        self.assertEqual(rag.call_count, 1)
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(second["answer"], "20 days")
        self.assertEqual(second["usage"]["llm_calls"], 0)
        hit = PredictionLog.objects.get(cache_hit=True)
        self.assertEqual(hit.llm_calls, 0)

    @patch("app.views.rag_query", return_value=dict(ANSWER))
    def test_a_different_question_is_not_served_from_the_cache(self, rag):
        self._ask("How many PTO days do full-time employees get?")
        self._ask("How many PTO days do part-time employees get?")
        self.assertEqual(rag.call_count, 2)

    @patch("app.views.rag_query", return_value=dict(ANSWER))
    def test_a_change_to_the_documents_invalidates_cached_answers(self, rag):
        self._ask("How many PTO days?")
        answer_cache.bump_corpus_version(self.ws)  # what ingestion and deletion do
        self.assertFalse(self._ask("How many PTO days?").json()["cached"])
        self.assertEqual(rag.call_count, 2)

    @patch("app.views.rag_query", return_value=dict(ANSWER))
    def test_one_workspace_never_sees_another_workspaces_cached_answer(self, rag):
        self._ask("How many PTO days?")
        _, other_auth = _register(self.client, "other@test.com")
        other_ws = _workspace_of("other@test.com")

        self.assertFalse(self._ask("How many PTO days?", auth=other_auth, ws=other_ws).json()["cached"])
        self.assertEqual(rag.call_count, 2)

    @override_settings(DAILY_QUERY_QUOTA=1)
    @patch("app.views.rag_query", return_value=dict(ANSWER))
    def test_cache_hits_do_not_use_the_daily_quota(self, rag):
        self.assertEqual(self._ask("How many PTO days?").status_code, 200)
        self.assertEqual(self._ask("How many PTO days?").status_code, 200)  # hit, free
        self.assertEqual(self._ask("Something new?").status_code, 429)     # quota of 1 spent

    @patch("app.views.rag_query", side_effect=RuntimeError("Groq is down"))
    def test_failures_are_not_cached(self, rag):
        self.assertEqual(self._ask("How many PTO days?").status_code, 502)
        self.assertEqual(self._ask("How many PTO days?").status_code, 502)
        self.assertEqual(rag.call_count, 2)

    def test_ingesting_a_document_moves_the_workspace_to_a_new_corpus_version(self):
        before = Workspace.objects.get(id=self.ws).corpus_version
        f = IngestedFile.objects.create(object_bucket="b", object_key=f"ws_{self.ws}/a_x.txt",
                                        file_type="txt", workspace_id=self.ws, status="PENDING")
        with patch("app.tasks.extract_and_chunk", return_value=[Document(page_content="x", metadata={})]), \
             patch("app.tasks.delete_file_vectors"), patch("app.tasks.embed_and_store", return_value=1):
            run_ingestion_task.apply(kwargs=dict(s3_key=f.object_key, user_id=self.user["id"],
                                                 workspace_id=self.ws, file_id=f.id))
        self.assertEqual(Workspace.objects.get(id=self.ws).corpus_version, before + 1)


@override_settings(WORKSPACE_QUERY_RATE="2/min")
class WorkspaceRateTests(TestCase):

    def setUp(self):
        cache.clear()
        self.client = Client()
        self.user, self.auth = _register(self.client, "w@test.com")
        self.ws = self.user["workspaces"][0]["id"]

    def _ask(self, auth, ws, question="q"):
        return self.client.post("/app/ai/query", {"question": question, "workspace_id": ws},
                                content_type="application/json", **auth)

    @patch("app.views.rag_query", return_value=dict(ANSWER))
    def test_a_workspace_over_its_shared_limit_gets_429_with_retry_after(self, rag):
        self.assertEqual(self._ask(self.auth, self.ws, "one").status_code, 200)
        self.assertEqual(self._ask(self.auth, self.ws, "two").status_code, 200)
        resp = self._ask(self.auth, self.ws, "three")
        self.assertEqual(resp.status_code, 429)
        self.assertGreaterEqual(int(resp["Retry-After"]), 1)
        self.assertEqual(rag.call_count, 2)

    @patch("app.views.rag_query", return_value=dict(ANSWER))
    def test_the_limit_is_shared_by_every_member_of_the_workspace(self, rag):
        _, teammate_auth = _register(self.client, "mate@test.com")
        Workspace.objects.get(id=self.ws).add_member(User.objects.get(email="mate@test.com"), "viewer")
        self.assertEqual(self._ask(self.auth, self.ws, "one").status_code, 200)
        self.assertEqual(self._ask(teammate_auth, self.ws, "two").status_code, 200)
        self.assertEqual(self._ask(teammate_auth, self.ws, "three").status_code, 429)

    @patch("app.views.rag_query", return_value=dict(ANSWER))
    def test_a_busy_workspace_does_not_slow_down_another(self, rag):
        for q in ("one", "two", "three"):
            self._ask(self.auth, self.ws, q)
        _, other_auth = _register(self.client, "quiet@test.com")
        other_ws = _workspace_of("quiet@test.com")
        self.assertEqual(self._ask(other_auth, other_ws).status_code, 200)

    @patch("app.views.rag_query", return_value=dict(ANSWER))
    def test_naming_another_tenants_workspace_does_not_spend_its_allowance(self, rag):
        """The limit is applied after authorisation, so a forged id is rejected uncounted."""
        _, attacker_auth = _register(self.client, "attacker@test.com")
        for _ in range(5):
            self.assertEqual(self._ask(attacker_auth, self.ws).status_code, 403)
        self.assertEqual(self._ask(self.auth, self.ws).status_code, 200)


@override_settings(MAX_INGESTION_PER_WORKSPACE=2, MAX_INGESTION_QUEUE_DEPTH=50)
class IngestionShareTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user, self.auth = _register(self.client, "i@test.com")
        self.ws = self.user["workspaces"][0]["id"]

    def _upload(self, auth, ws, key):
        return self.client.post("/app/ai/upload", {"s3_key": key, "workspace_id": ws},
                                content_type="application/json", **auth)

    @patch("app.views.run_ingestion_task.delay")
    def test_one_workspace_cannot_take_every_ingestion_slot(self, delay):
        delay.return_value.id = "t"
        self.assertEqual(self._upload(self.auth, self.ws, f"ws_{self.ws}/a.pdf").status_code, 202)
        self.assertEqual(self._upload(self.auth, self.ws, f"ws_{self.ws}/b.pdf").status_code, 202)
        third = self._upload(self.auth, self.ws, f"ws_{self.ws}/c.pdf")
        self.assertEqual(third.status_code, 429)
        self.assertIn("Retry-After", third)

        # Another tenant still gets a slot in the shared queue.
        _, other_auth = _register(self.client, "j@test.com")
        other_ws = _workspace_of("j@test.com")
        self.assertEqual(self._upload(other_auth, other_ws, f"ws_{other_ws}/a.pdf").status_code, 202)
