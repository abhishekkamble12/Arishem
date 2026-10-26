"""
Tests — tenant isolation, role management, storage keys and file deletion.
"""

import os
import shutil
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from Services import storage

from .models import IngestedFile, MeetingAnalysis
from .tests import _get_token, _make_user

User = get_user_model()


class StorageKeyTests(TestCase):

    def test_keys_are_namespaced_and_unique(self):
        a = storage.build_object_key(1, "report.pdf")
        b = storage.build_object_key(1, "report.pdf")
        self.assertTrue(a.startswith("ws_1/"))
        self.assertTrue(a.endswith("_report.pdf"))
        self.assertNotEqual(a, b)

    def test_filename_is_sanitised(self):
        key = storage.build_object_key(3, "../../etc/pass wd.pdf")
        self.assertTrue(key.startswith("ws_3/"))
        self.assertNotIn("..", key)
        self.assertTrue(key.endswith("_pass_wd.pdf"))

    def test_key_must_be_inside_workspace(self):
        self.assertTrue(storage.is_key_in_workspace("ws_1/a.pdf", 1))
        self.assertFalse(storage.is_key_in_workspace("ws_2/a.pdf", 1))
        self.assertFalse(storage.is_key_in_workspace("ws_1/../ws_2/a.pdf", 1))
        self.assertFalse(storage.is_key_in_workspace("ws_10/a.pdf", 1))

    def test_resolve_rejects_traversal(self):
        with self.assertRaises(ValueError):
            storage.resolve_local_path("../../outside.pdf")


class IngestionIsolationTests(TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        patcher = patch.object(storage, "LOCAL_STORAGE_DIR", self.tmp)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        delay = patch("app.views.run_ingestion_task.delay")
        self.mock_delay = delay.start()
        self.mock_delay.return_value.id = "task-1"
        self.addCleanup(delay.stop)

        self.client = Client()
        self.user_a = _make_user("a@test.com", "Pass1234!", "editor")
        self.user_b = _make_user("b@test.com", "Pass1234!", "editor")
        self.ws_a = self.user_a.workspaces.first()
        self.ws_b = self.user_b.workspaces.first()
        self.auth_a = {"HTTP_AUTHORIZATION": f"Bearer {_get_token(self.client, 'a@test.com', 'Pass1234!')}"}
        self.auth_b = {"HTTP_AUTHORIZATION": f"Bearer {_get_token(self.client, 'b@test.com', 'Pass1234!')}"}

    def _upload(self, auth, name="report.pdf"):
        return self.client.post(
            "/app/ai/upload-direct",
            {"file": SimpleUploadedFile(name, b"%PDF-1.4 test"), "workspace_id": ""},
            **auth,
        )

    def test_same_filename_in_two_workspaces_does_not_collide(self):
        resp_a = self._upload(self.auth_a)
        resp_b = self._upload(self.auth_b)
        self.assertEqual(resp_a.status_code, 202)
        self.assertEqual(resp_b.status_code, 202)

        key_a = resp_a.json()["file"]["s3_key"]
        key_b = resp_b.json()["file"]["s3_key"]
        self.assertTrue(key_a.startswith(f"ws_{self.ws_a.id}/"))
        self.assertTrue(key_b.startswith(f"ws_{self.ws_b.id}/"))
        self.assertTrue(os.path.exists(storage.resolve_local_path(key_a)))
        self.assertTrue(os.path.exists(storage.resolve_local_path(key_b)))
        self.assertEqual(resp_a.json()["file"]["original_filename"], "report.pdf")

    def test_rejected_upload_is_removed_from_storage(self):
        with self.settings(MAX_INGESTION_QUEUE_DEPTH=0):
            resp = self._upload(self.auth_a)
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(os.listdir(os.path.join(self.tmp, f"ws_{self.ws_a.id}")), [])

    def test_upload_by_key_rejects_path_traversal(self):
        resp = self.client.post(
            "/app/ai/upload", {"s3_key": f"ws_{self.ws_a.id}/../../secrets.pdf"},
            content_type="application/json", **self.auth_a,
        )
        self.assertEqual(resp.status_code, 400)
        self.mock_delay.assert_not_called()

    def test_upload_by_key_rejects_other_workspace(self):
        resp = self.client.post(
            "/app/ai/upload", {"s3_key": f"ws_{self.ws_b.id}/report.pdf"},
            content_type="application/json", **self.auth_a,
        )
        self.assertEqual(resp.status_code, 400)
        self.mock_delay.assert_not_called()


@patch("app.views.delete_file_vectors")
class DeleteFileTests(TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        patcher = patch.object(storage, "LOCAL_STORAGE_DIR", self.tmp)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.client = Client()
        self.user_a = _make_user("a@test.com", "Pass1234!", "editor")
        self.user_b = _make_user("b@test.com", "Pass1234!", "editor")
        self.ws_a = self.user_a.workspaces.first()
        self.auth_a = {"HTTP_AUTHORIZATION": f"Bearer {_get_token(self.client, 'a@test.com', 'Pass1234!')}"}
        self.auth_b = {"HTTP_AUTHORIZATION": f"Bearer {_get_token(self.client, 'b@test.com', 'Pass1234!')}"}

        self.key = f"ws_{self.ws_a.id}/abc_report.pdf"
        path = storage.resolve_local_path(self.key)
        os.makedirs(os.path.dirname(path))
        with open(path, "wb") as f:
            f.write(b"data")
        self.file = IngestedFile.objects.create(
            object_bucket="b", object_key=self.key, original_filename="report.pdf",
            file_type="pdf", workspace=self.ws_a, uploaded_by=self.user_a, status="SUCCESS",
        )

    def _delete(self, auth, **body):
        return self.client.delete("/app/ai/files/delete", body, content_type="application/json", **auth)

    def test_delete_removes_vectors_object_and_record(self, mock_vectors):
        resp = self._delete(self.auth_a, file_id=self.file.id)
        self.assertEqual(resp.status_code, 200)
        mock_vectors.assert_called_once_with(self.file.id, self.ws_a.id)
        self.assertFalse(IngestedFile.objects.filter(id=self.file.id).exists())
        self.assertFalse(os.path.exists(storage.resolve_local_path(self.key)))

    def test_other_tenant_gets_404_and_nothing_is_deleted(self, mock_vectors):
        resp = self._delete(self.auth_b, file_id=self.file.id)
        self.assertEqual(resp.status_code, 404)
        mock_vectors.assert_not_called()
        self.assertTrue(IngestedFile.objects.filter(id=self.file.id).exists())

    def test_in_progress_file_cannot_be_deleted(self, mock_vectors):
        self.file.status = "PROCESSING"
        self.file.save()
        resp = self._delete(self.auth_a, file_id=self.file.id)
        self.assertEqual(resp.status_code, 409)
        mock_vectors.assert_not_called()

    def test_vector_failure_keeps_record_for_retry(self, mock_vectors):
        mock_vectors.side_effect = RuntimeError("qdrant down")
        resp = self._delete(self.auth_a, file_id=self.file.id)
        self.assertEqual(resp.status_code, 502)
        self.assertTrue(IngestedFile.objects.filter(id=self.file.id).exists())
        self.assertTrue(os.path.exists(storage.resolve_local_path(self.key)))

    def test_legacy_delete_by_key_still_works(self, mock_vectors):
        resp = self._delete(self.auth_a, s3_key=self.key)
        self.assertEqual(resp.status_code, 200)


class MeetingEndpointTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user_a = _make_user("a@test.com", "Pass1234!", "editor")
        _make_user("b@test.com", "Pass1234!", "editor")
        self.ws_a = self.user_a.workspaces.first()
        self.auth_a = {"HTTP_AUTHORIZATION": f"Bearer {_get_token(self.client, 'a@test.com', 'Pass1234!')}"}
        self.auth_b = {"HTTP_AUTHORIZATION": f"Bearer {_get_token(self.client, 'b@test.com', 'Pass1234!')}"}

    def test_analysis_hidden_from_other_tenants(self):
        f = IngestedFile.objects.create(
            object_bucket="b", object_key=f"ws_{self.ws_a.id}/m.mp3", file_type="mp3",
            workspace=self.ws_a, status="SUCCESS",
        )
        MeetingAnalysis.objects.create(file=f, title="Secret roadmap")

        self.assertEqual(self.client.get(f"/app/ai/meetings/{f.id}/analysis", **self.auth_a).status_code, 200)
        self.assertEqual(self.client.get(f"/app/ai/meetings/{f.id}/analysis", **self.auth_b).status_code, 404)

    @patch("app.views.run_youtube_ingestion_task.delay")
    def test_youtube_ingestion_is_queued(self, mock_delay):
        mock_delay.return_value.id = "yt-task"
        resp = self.client.post(
            "/app/ai/meetings/ingest-youtube", {"url": "https://www.youtube.com/watch?v=abc123&t=5"},
            content_type="application/json", **self.auth_a,
        )
        self.assertEqual(resp.status_code, 202)
        file_obj = IngestedFile.objects.get(id=resp.json()["file_id"])
        self.assertEqual(file_obj.status, "PENDING")
        self.assertEqual(file_obj.original_filename, "YouTube_abc123")
        mock_delay.assert_called_once()

    @patch("app.views.run_youtube_ingestion_task.delay")
    def test_youtube_rejects_lookalike_hosts(self, mock_delay):
        for url in ["https://evil.com/?youtube.com", "https://youtube.com.evil.com/watch?v=x", "ftp://youtu.be/x"]:
            resp = self.client.post(
                "/app/ai/meetings/ingest-youtube", {"url": url},
                content_type="application/json", **self.auth_a,
            )
            self.assertEqual(resp.status_code, 400, msg=url)
        mock_delay.assert_not_called()


class HealthTests(TestCase):

    def test_health_is_public(self):
        resp = Client().get("/app/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")
