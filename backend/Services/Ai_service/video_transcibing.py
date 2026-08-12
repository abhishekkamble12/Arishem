"""
Video transcription service using local faster-whisper.

Flow:
  1. Video/audio file already exists locally in local_storage (uploaded by the client)
  2. Load faster-whisper model (base size for speed)
  3. Transcribe the media file directly
  4. Return the transcript text as a LangChain Document so it can be
     chunked and embedded exactly like a PDF

Supported input formats:
  mp4, mov, avi, mkv, mp3, wav, flac, ogg, m4a
"""

import os
import logging
import uuid
from pathlib import PurePosixPath
from django.conf import settings

from langchain_core.documents import Document

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

logger = logging.getLogger(__name__)

SUPPORTED_MEDIA_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv",   # video
    ".mp3", ".wav", ".flac", ".ogg", ".m4a",  # audio
}

LOCAL_STORAGE_DIR = os.path.join(settings.BASE_DIR, "local_storage")

# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------
_whisper_model = None

def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        if WhisperModel is None:
            raise RuntimeError("faster-whisper is not installed. Please install it to support media transcription.")
        # Load a small fast model for local demo
        logger.info("Loading faster-whisper 'base' model...")
        _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
    return _whisper_model

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

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def transcribe_media(bucket_name: str, s3_key: str) -> Document:
    """
    Transcribe a video or audio file stored locally.

    Returns:
        A single LangChain Document with the full transcript as page_content
        and source metadata attached.
    """
    ext = _validate_extension(s3_key)
    local_path = os.path.join(LOCAL_STORAGE_DIR, s3_key)
    
    if not os.path.exists(local_path):
        raise FileNotFoundError(f"Media file not found locally: {local_path}")

    # Unique job name for logging
    job_name = f"local-transcribe-{uuid.uuid4().hex[:8]}"

    logger.info("Starting local Whisper transcription job '%s' for %s", job_name, local_path)
    
    model = _get_whisper_model()
    segments, info = model.transcribe(local_path, beam_size=5)
    
    logger.info("Detected language '%s' with probability %f", info.language, info.language_probability)
    
    transcript_text = ""
    for segment in segments:
        transcript_text += segment.text + " "

    transcript_text = transcript_text.strip()
    
    if not transcript_text:
        logger.warning("Local whisper returned empty transcript for %s", local_path)
        transcript_text = "[No speech detected]"

    return Document(
        page_content=transcript_text,
        metadata={
            "source": s3_key,
            "bucket": "local_storage",
            "job_name": job_name,
            "media_type": ext.lstrip("."),
        },
    )
