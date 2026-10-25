"""
Input / cost limits and the Qdrant collection-safety guarantee.
All offline: the vector store, LLM and Qdrant client are faked.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

from app.models import PredictionLog
from app.throttling import AuthRateThrottle

User = get_user_model()
PASSWORD = "Pass1234!"


def _register(client, email):
    resp = client.post(
        "/app/auth/register",
        {"email": email, "password": PASSWORD, "password2": PASSWORD},
        content_type="application/json",
    )
    assert resp.status_code == 201, resp.content
    data = resp.json()
    return data["user"], {"HTTP_AUTHORIZATION": f"Bearer {data['tokens']['access']}"}


class QueryLimitTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user, self.auth = _register(self.client, "q@test.com")

    def _query(self, **body):
        return self.client.post(
            "/app/ai/query", body, content_type="application/json", **self.auth
        )

    @patch("app.views.rag_query")
    def test_overlong_question_rejected_before_llm(self, rag):
        resp = self._query(question="x" * 1001)
        self.assertEqual(resp.status_code, 400)
        rag.assert_not_called()

    @patch("app.views.rag_query")
    def test_top_k_out_of_range_rejected(self, rag):
        for bad in (0, -1, 11, 10_000):
            self.assertEqual(self._query(question="hi", top_k=bad).status_code, 400)
        rag.assert_not_called()

    @patch("app.views.rag_query", return_value={"answer": "ok", "confidence": 0.9})
    def test_top_k_in_range_accepted(self, rag):
        self.assertEqual(self._query(question="hi", top_k=10).status_code, 200)
        self.assertEqual(rag.call_args.kwargs["top_k"], 10)

    @override_settings(DAILY_QUERY_QUOTA=2)
    @patch("app.views.rag_query", return_value={"answer": "ok", "confidence": 0.9})
    def test_daily_quota_enforced(self, rag):
        self.assertEqual(self._query(question="one").status_code, 200)
        self.assertEqual(self._query(question="two").status_code, 200)
        self.assertEqual(self._query(question="three").status_code, 429)
        self.assertEqual(rag.call_count, 2)

    @override_settings(DAILY_QUERY_QUOTA=1)
    @patch("app.views.rag_query", return_value={"answer": "ok", "confidence": 0.9})
    def test_quota_is_per_user(self, rag):
        self.assertEqual(self._query(question="one").status_code, 200)
        _, other_auth = _register(self.client, "other@test.com")
        resp = self.client.post(
            "/app/ai/query", {"question": "mine"}, content_type="application/json", **other_auth
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PredictionLog.objects.count(), 2)


class UploadLimitTests(TestCase):
    @override_settings(MAX_UPLOAD_MB=1)
    @patch("app.views.save_upload")
    def test_oversized_upload_rejected_before_storage(self, store):
        client = Client()
        _, auth = _register(client, "u@test.com")
        big = SimpleUploadedFile("big.pdf", b"0" * (1024 * 1024 + 1), content_type="application/pdf")
        resp = client.post("/app/ai/upload-direct", {"file": big}, **auth)
        self.assertEqual(resp.status_code, 413)
        store.assert_not_called()


class AuthThrottleTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_login_is_rate_limited_per_ip(self):
        with patch.dict(AuthRateThrottle.THROTTLE_RATES, {"auth": "3/min"}):
            client = Client()
            codes = [
                client.post(
                    "/app/auth/login",
                    {"email": "nobody@test.com", "password": "wrong"},
                    content_type="application/json",
                ).status_code
                for _ in range(5)
            ]
        self.assertEqual(codes[:3], [401, 401, 401])
        self.assertEqual(codes[3:], [429, 429])


class OptionalFeatureGateTests(TestCase):
    @override_settings(ENABLE_MEETINGS=False)
    @patch("app.views.save_upload")
    def test_media_upload_rejected_when_meetings_disabled(self, store):
        client = Client()
        _, auth = _register(client, "m@test.com")
        clip = SimpleUploadedFile("talk.mp4", b"x", content_type="video/mp4")
        resp = client.post("/app/ai/upload-direct", {"file": clip}, **auth)
        self.assertEqual(resp.status_code, 415)
        self.assertNotIn(".mp4", resp.json()["supported"])
        store.assert_not_called()

    @override_settings(ENABLE_MEETINGS=False)
    def test_text_and_markdown_are_accepted_document_types(self):
        from app.views import _allowed_extensions

        self.assertTrue({".pdf", ".docx", ".txt", ".md"} <= _allowed_extensions())
