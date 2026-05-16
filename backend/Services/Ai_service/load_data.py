"""
S3 file downloader — supports PDF, DOCX, and PPTX.

Uses boto3's default credential chain (env vars → ~/.aws/credentials → IAM role).
Never hardcode credentials here — set AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
in .env for local dev, and attach an IAM role in production.
"""

import os
import tempfile
import logging
from contextlib import contextmanager
from pathlib import PurePosixPath

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from decouple import config

logger = logging.getLogger(__name__)

# Supported file types and their temp-file suffixes
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx"}

_s3_client = None


def _get_s3_client():
    """Lazy singleton S3 client — reuses the connection across calls."""
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            region_name=config("AWS_REGION", default="us-east-1"),
        )
    return _s3_client


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
    Context manager that downloads a file from S3 into a NamedTemporaryFile,
    yields the local file path, then cleans up automatically.

    Supports: .pdf, .docx, .pptx
    The temp file is given the correct suffix so loaders can detect the type.

    Usage:
        with download_from_s3(bucket, key) as path:
            # path will be e.g. /tmp/tmpXXXX.docx
            docs = Docx2txtLoader(path).load()

    Args:
        bucket_name: S3 bucket name.
        s3_key:      Object key, e.g. "uploads/report.docx"

    Raises:
        ValueError:                  Unsupported file extension.
        botocore.ClientError:        Object not found or access denied.
        botocore.BotoCoreError:      Network / config errors.
    """
    ext = _get_extension(s3_key)
    tmp_path = None

    try:
        client = _get_s3_client()
        logger.info("Downloading s3://%s/%s (type: %s)", bucket_name, s3_key, ext)

        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp_path = tmp.name

        client.download_file(bucket_name, s3_key, tmp_path)
        logger.info("Downloaded to %s", tmp_path)
        yield tmp_path

    except ClientError as e:
        code = e.response["Error"]["Code"]
        logger.error(
            "S3 ClientError [%s] for s3://%s/%s: %s", code, bucket_name, s3_key, e
        )
        raise
    except BotoCoreError as e:
        logger.error("BotoCoreError downloading s3://%s/%s: %s", bucket_name, s3_key, e)
        raise
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
            logger.debug("Cleaned up temp file %s", tmp_path)
    
