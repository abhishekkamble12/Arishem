"""
Smoke tests — verify the Django app loads and the three API endpoints
are reachable without hitting any real external services.
"""

from django.test import TestCase, Client
from django.urls import reverse


class HealthCheckTest(TestCase):
    """Verify Django starts up and the URL config is wired correctly."""

    def setUp(self):
        self.client = Client()

    def test_upload_endpoint_exists(self):
        """POST /app/ai/upload should return 400 (missing body), not 404."""
        response = self.client.post(
            "/app/ai/upload",
            data={},
            content_type="application/json",
        )
        # 400 = endpoint exists but s3_key is missing — that's correct behaviour
        self.assertEqual(response.status_code, 400)

    def test_query_endpoint_exists(self):
        """POST /app/ai/query should return 400 (missing body), not 404."""
        response = self.client.post(
            "/app/ai/query",
            data={},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_files_endpoint_exists(self):
        """GET /app/ai/files should return 200 with an empty list."""
        response = self.client.get("/app/ai/files")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("files", data)
        self.assertIn("total", data)
        self.assertEqual(data["total"], 0)

    def test_url_reverse(self):
        """All named URLs should resolve without errors."""
        self.assertEqual(reverse("store_vectordb"), "/app/ai/upload")
        self.assertEqual(reverse("query_vectordb"), "/app/ai/query")
        self.assertEqual(reverse("list_files"),     "/app/ai/files")
