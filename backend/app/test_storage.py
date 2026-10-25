"""S3-compatible storage backend, with boto3 faked."""

import os
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from Services import storage


@override_settings(STORAGE_BACKEND="s3", OBJECT_STORAGE_BUCKET="bkt")
class S3BackendTests(SimpleTestCase):
    def setUp(self):
        self.s3 = MagicMock()
        p = patch.object(storage, "_s3", return_value=self.s3)
        p.start()
        self.addCleanup(p.stop)

    def test_save_upload_puts_object_in_bucket(self):
        f = SimpleUploadedFile("a.pdf", b"data")
        self.assertTrue(storage.save_upload(f, "ws_1/k.pdf"))
        args = self.s3.upload_fileobj.call_args.args
        self.assertEqual(args[1:], ("bkt", "ws_1/k.pdf"))

    def test_save_upload_reports_failure(self):
        self.s3.upload_fileobj.side_effect = RuntimeError("boom")
        self.assertFalse(storage.save_upload(SimpleUploadedFile("a.pdf", b"x"), "ws_1/k.pdf"))

    def test_delete_object(self):
        self.assertTrue(storage.delete_object("ws_1/k.pdf"))
        self.s3.delete_object.assert_called_once_with(Bucket="bkt", Key="ws_1/k.pdf")

    def test_local_copy_downloads_to_temp_and_cleans_up(self):
        def fake_download(bucket, key, path):
            with open(path, "wb") as fh:
                fh.write(b"hello")

        self.s3.download_file.side_effect = fake_download
        with storage.local_copy("ws_1/k.pdf") as path:
            self.assertTrue(path.endswith(".pdf"))
            with open(path, "rb") as fh:
                self.assertEqual(fh.read(), b"hello")
        self.assertFalse(os.path.exists(path))
