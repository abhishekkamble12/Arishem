import logging
from contextlib import contextmanager
from pathlib import PurePosixPath

from ..storage import local_copy

logger = logging.getLogger(__name__)

# Supported file types and their temp-file suffixes
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".txt", ".md"}


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
    Yield a local path for the stored object (see storage.local_copy).
    Raises ValueError for unsupported extensions or unsafe keys, and
    FileNotFoundError if the object is missing. `bucket_name` is kept for
    call-site compatibility; the bucket comes from settings.
    """
    ext = _get_extension(s3_key)
    logger.info("Reading stored object %s (type: %s)", s3_key, ext)
    with local_copy(s3_key) as path:
        yield path
