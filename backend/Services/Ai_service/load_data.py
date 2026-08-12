import os
import logging
from contextlib import contextmanager
from pathlib import PurePosixPath
from django.conf import settings

logger = logging.getLogger(__name__)

# Supported file types and their temp-file suffixes
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx"}

LOCAL_STORAGE_DIR = os.path.join(settings.BASE_DIR, "local_storage")


def _get_extension(s3_key: str) -> str:
    """
    Extract and validate the file extension from an S3 key.

    Uses the key path itself — no extra API call needed.
    Raises ValueError for unsupported types.
    """
    ext = PurePosixPath(s3_key).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{ext}' for key '{s3_key}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    return ext


@contextmanager
def download_from_s3(bucket_name: str, s3_key: str):
    """
    Context manager that yields the local file path from local_storage.

    Supports: .pdf, .docx, .pptx

    Usage:
        with download_from_s3(bucket, key) as path:
            docs = Docx2txtLoader(path).load()

    Args:
        bucket_name: Ignored in local setup.
        s3_key:      Object key, e.g. "uploads/report.docx"

    Raises:
        ValueError:                  Unsupported file extension.
        FileNotFoundError:           Object not found locally.
    """
    ext = _get_extension(s3_key)
    
    local_path = os.path.join(LOCAL_STORAGE_DIR, s3_key)
    
    if not os.path.exists(local_path):
        logger.error("Local file not found: %s", local_path)
        raise FileNotFoundError(f"File not found: {local_path}")

    logger.info("Reading local file %s (type: %s)", local_path, ext)
    
    try:
        yield local_path
    finally:
        pass # No cleanup needed as we are reading the original file directly

