"""
Video transcription service using AWS Transcribe.

Flow:
  1. Video/audio file already exists in S3 (uploaded by the client)
  2. Start an AWS Transcribe job pointing at that S3 URI
  3. Poll until the job completes (or fails)
  4. Fetch the transcript JSON from the output S3 URI
  5. Return the transcript text as a LangChain Document so it can be
     chunked and embedded exactly like a PDF

Supported input formats (AWS Transcribe accepts all of these):
  mp4, mov, avi, mkv, mp3, wav, flac, ogg, m4a

Environment variables required (set in .env):
    AWS_REGION              — e.g. us-east-1
    OBJECT_STORAGE_BUCKET               — bucket where videos are stored
    TRANSCRIBE_OUTPUT_BUCKET — bucket where JSON transcripts go
                               (can be the same as OBJECT_STORAGE_BUCKET)
"""

import json
import logging
import time
import uuid
from pathlib import PurePosixPath

import boto3
from botocore.exceptions import ClientError
from decouple import config
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
AWS_REGION = config("AWS_REGION", default="us-east-1")
TRANSCRIBE_OUTPUT_BUCKET = config("TRANSCRIBE_OUTPUT_BUCKET", default=config("OBJECT_STORAGE_BUCKET"))

SUPPORTED_MEDIA_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv",   # video
    ".mp3", ".wav", ".flac", ".ogg", ".m4a",  # audio
}

# How long to wait between status polls (seconds)
_POLL_INTERVAL = 5
# Maximum total wait time before giving up (seconds) — 30 minutes
_MAX_WAIT = 1800

# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------
_transcribe_client = None
_s3_client = None


def _get_transcribe_client():
    global _transcribe_client
    if _transcribe_client is None:
        _transcribe_client = boto3.client("transcribe", region_name=AWS_REGION)
    return _transcribe_client


def _get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3", region_name=AWS_REGION)
    return _s3_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_extension(s3_key: str) -> str:
    ext = PurePosixPath(s3_key).suffix.lower()
    if ext not in SUPPORTED_MEDIA_EXTENSIONS:
        raise ValueError(
            f"Unsupported media type '{ext}' for key '{s3_key}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_MEDIA_EXTENSIONS))}"
        )
    return ext


def _media_format(ext: str) -> str:
    """Map file extension to the format string AWS Transcribe expects."""
    _map = {
        ".mp4": "mp4", ".mov": "mov", ".avi": "avi", ".mkv": "mkv",
        ".mp3": "mp3", ".wav": "wav", ".flac": "flac",
        ".ogg": "ogg", ".m4a": "mp4",  # m4a is an mp4 container
    }
    return _map[ext]


def _poll_job(job_name: str) -> dict:
    """
    Block until the Transcribe job reaches a terminal state.
    Returns the completed job dict.
    Raises RuntimeError if the job fails or times out.
    """
    client = _get_transcribe_client()
    elapsed = 0

    while elapsed < _MAX_WAIT:
        response = client.get_transcription_job(TranscriptionJobName=job_name)
        job = response["TranscriptionJob"]
        job_status = job["TranscriptionJobStatus"]

        if job_status == "COMPLETED":
            logger.info("Transcription job '%s' completed", job_name)
            return job
        elif job_status == "FAILED":
            reason = job.get("FailureReason", "unknown")
            raise RuntimeError(f"Transcription job '{job_name}' failed: {reason}")

        logger.debug("Job '%s' status: %s — waiting %ds…", job_name, job_status, _POLL_INTERVAL)
        time.sleep(_POLL_INTERVAL)
        elapsed += _POLL_INTERVAL

    raise TimeoutError(
        f"Transcription job '{job_name}' did not complete within {_MAX_WAIT}s"
    )


def _fetch_transcript_text(transcript_uri: str) -> str:
    """
    Download the Transcribe output JSON from S3 and extract the transcript text.

    Handles both URI formats AWS Transcribe may return:
        https://s3.amazonaws.com/bucket/key          (us-east-1 path-style)
        https://s3.us-west-2.amazonaws.com/bucket/key (regional path-style)
        https://bucket.s3.amazonaws.com/key          (virtual-hosted style)
        https://bucket.s3.us-east-1.amazonaws.com/key
    """
    from urllib.parse import urlparse

    parsed = urlparse(transcript_uri)
    host   = parsed.hostname  # e.g. "s3.amazonaws.com" or "s3.us-east-1.amazonaws.com"
                              # or "mybucket.s3.amazonaws.com"
    path   = parsed.path.lstrip("/")  # e.g. "bucket/prefix/job.json" or "prefix/job.json"

    # Virtual-hosted style: bucket name is a subdomain of s3*.amazonaws.com
    # e.g. mybucket.s3.amazonaws.com  or  mybucket.s3.us-east-1.amazonaws.com
    if host and not host.startswith("s3"):
        # host looks like "mybucket.s3.amazonaws.com"
        bucket = host.split(".")[0]
        key    = path
    else:
        # Path-style: first path component is the bucket
        bucket, _, key = path.partition("/")

    logger.debug("Fetching transcript: bucket=%s key=%s", bucket, key)

    s3  = _get_s3_client()
    obj = s3.get_object(Bucket=bucket, Key=key)
    data = json.loads(obj["Body"].read())

    # AWS Transcribe JSON structure:
    # { "results": { "transcripts": [ { "transcript": "..." } ] } }
    transcripts = data.get("results", {}).get("transcripts", [])
    if not transcripts:
        raise ValueError("Transcribe output contained no transcript text")

    return transcripts[0]["transcript"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def transcribe_media(bucket_name: str, s3_key: str) -> Document:
    """
    Transcribe a video or audio file stored in S3.

    Starts an AWS Transcribe job, waits for completion, fetches the output,
    and returns a LangChain Document containing the transcript text.

    The returned Document can be passed directly to RecursiveCharacterTextSplitter
    and then to embed_and_store() — same pipeline as PDF/DOCX.

    Args:
        bucket_name: S3 bucket where the media file lives.
        s3_key:      Object key, e.g. "videos/lecture.mp4"

    Returns:
        A single LangChain Document with the full transcript as page_content
        and source metadata attached.

    Raises:
        ValueError:    Unsupported file type or empty transcript.
        RuntimeError:  Transcribe job failed.
        TimeoutError:  Job did not finish within MAX_WAIT seconds.
        ClientError:   S3 / Transcribe API errors.
    """
    ext = _validate_extension(s3_key)
    media_uri = f"s3://{bucket_name}/{s3_key}"

    # Unique job name — Transcribe requires globally unique names per account
    job_name = f"arishem-{uuid.uuid4().hex[:12]}"
    output_key_prefix = f"transcripts/{PurePosixPath(s3_key).stem}/"

    client = _get_transcribe_client()

    logger.info("Starting Transcribe job '%s' for %s", job_name, media_uri)
    client.start_transcription_job(
        TranscriptionJobName=job_name,
        Media={"MediaFileUri": media_uri},
        MediaFormat=_media_format(ext),
        LanguageCode="en-US",          # change or make configurable as needed
        OutputBucketName=TRANSCRIBE_OUTPUT_BUCKET,
        OutputKey=output_key_prefix,
        Settings={
            "ShowSpeakerLabels": True,
            "MaxSpeakerLabels": 10,    # diarisation — who said what
        },
    )

    # Block until done
    completed_job = _poll_job(job_name)
    transcript_uri = completed_job["Transcript"]["TranscriptFileUri"]

    logger.info("Fetching transcript from %s", transcript_uri)
    transcript_text = _fetch_transcript_text(transcript_uri)

    return Document(
        page_content=transcript_text,
        metadata={
            "source": s3_key,
            "bucket": bucket_name,
            "job_name": job_name,
            "media_type": ext.lstrip("."),
        },
    )
