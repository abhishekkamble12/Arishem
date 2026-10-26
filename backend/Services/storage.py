"""
Object storage helpers.

Two backends, chosen by settings.STORAGE_BACKEND:
  local  – files under LOCAL_STORAGE_DIR (development, tests)
  s3     – any S3-compatible bucket (AWS S3, Cloudflare R2, MinIO) through boto3;
           set OBJECT_STORAGE_ENDPOINT_URL for non-AWS providers.

Both use the same key layout. Keys are always namespaced by workspace so
tenants can never collide or overwrite each other:

    ws_<workspace_id>/<uuid>_<sanitised filename>
"""

import logging
import os
import re
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import PurePosixPath

from django.conf import settings

logger = logging.getLogger(__name__)

LOCAL_STORAGE_DIR = os.path.join(settings.BASE_DIR, "local_storage")

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def workspace_prefix(workspace_id: int) -> str:
    return f"ws_{workspace_id}/"


def build_object_key(workspace_id: int, filename: str) -> str:
    """Return a collision-proof key for a new upload inside a workspace."""
    name = PurePosixPath(filename.replace("\\", "/")).name
    name = _UNSAFE_CHARS.sub("_", name).strip("._") or "file"
    return f"{workspace_prefix(workspace_id)}{uuid.uuid4().hex}_{name}"


def is_key_in_workspace(s3_key: str, workspace_id: int) -> bool:
    """True if the key is a plain relative path inside the workspace prefix."""
    parts = PurePosixPath(s3_key).parts
    return (
        s3_key.startswith(workspace_prefix(workspace_id))
        and "\\" not in s3_key
        and ".." not in parts
    )


def resolve_local_path(s3_key: str) -> str:
    """
    Map a storage key to an absolute path, refusing anything that would
    escape LOCAL_STORAGE_DIR (e.g. '../../etc/passwd.pdf').
    """
    root = os.path.realpath(LOCAL_STORAGE_DIR)
    path = os.path.realpath(os.path.join(root, s3_key))
    if os.path.commonpath([root, path]) != root:
        raise ValueError(f"Invalid storage key '{s3_key}'")
    return path


def _use_s3() -> bool:
    return settings.STORAGE_BACKEND == "s3"


_s3_client = None


def _s3():
    """Lazy boto3 client. Credentials come from env / the platform's IAM role."""
    global _s3_client
    if _s3_client is None:
        import boto3
        from botocore.config import Config

        _s3_client = boto3.client(
            "s3",
            endpoint_url=settings.OBJECT_STORAGE_ENDPOINT_URL or None,
            aws_access_key_id=settings.OBJECT_STORAGE_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.OBJECT_STORAGE_SECRET_ACCESS_KEY or None,
            region_name=settings.OBJECT_STORAGE_REGION,
            config=Config(retries={"max_attempts": 3, "mode": "standard"}, connect_timeout=5, read_timeout=30),
        )
    return _s3_client


def save_upload(file_obj, key: str) -> bool:
    """Store a Django UploadedFile under `key`. Returns True on success."""
    try:
        if _use_s3():
            file_obj.seek(0)
            _s3().upload_fileobj(file_obj, settings.OBJECT_STORAGE_BUCKET, key)
            return True
        target_path = resolve_local_path(key)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, "wb") as destination:
            for chunk in file_obj.chunks():
                destination.write(chunk)
        return True
    except Exception:
        logger.exception("Storing upload failed for key '%s'", key)
        return False


def delete_object(key: str) -> bool:
    """Delete a stored object. Missing objects count as already deleted."""
    try:
        if _use_s3():
            _s3().delete_object(Bucket=settings.OBJECT_STORAGE_BUCKET, Key=key)  # idempotent in S3
            return True
        os.remove(resolve_local_path(key))
        return True
    except FileNotFoundError:
        return True
    except Exception:
        logger.exception("Failed to delete stored object '%s'", key)
        return False


@contextmanager
def local_copy(key: str):
    """
    Yield a local filesystem path holding the object's bytes.
    Local backend: the stored file itself. S3 backend: a temp file that is
    removed afterwards, so loaders that need a path (PyMuPDF, docx2txt) work.
    """
    if not _use_s3():
        path = resolve_local_path(key)
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {key}")
        yield path
        return

    suffix = os.path.splitext(key)[1]
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        try:
            _s3().download_file(settings.OBJECT_STORAGE_BUCKET, key, tmp_path)
        except Exception as exc:
            # Both backends must fail the same way for the same cause, or the
            # caller's error handling only works on one of them. boto raises
            # ClientError 404/NoSuchKey where the local backend raises OSError.
            code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if code in ("404", "NoSuchKey"):
                raise FileNotFoundError(f"File not found: {key}") from exc
            raise
        yield tmp_path
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
