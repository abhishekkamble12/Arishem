"""
Meeting Transcriber — Local Whisper via faster-whisper.

Uses the faster-whisper library (already in requirements.txt) to transcribe
audio/video files locally without any cloud API calls.

Singleton model loading: the Whisper model is loaded once per process and
reused across calls to avoid repeated disk I/O and GPU/CPU warm-up.
"""

import logging
import os
from pathlib import Path

from decouple import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
WHISPER_MODEL_SIZE = config("WHISPER_MODEL", default="small")
WHISPER_DEVICE     = config("WHISPER_DEVICE", default="cpu")   # "cpu" or "cuda"
WHISPER_COMPUTE    = config("WHISPER_COMPUTE_TYPE", default="int8")  # "int8", "float16"

_model = None  # singleton


def _get_model():
    """Load and cache the faster-whisper model (singleton)."""
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        logger.info(
            "Loading faster-whisper model '%s' on device='%s' compute_type='%s'",
            WHISPER_MODEL_SIZE, WHISPER_DEVICE, WHISPER_COMPUTE,
        )
        _model = WhisperModel(
            WHISPER_MODEL_SIZE,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE,
        )
        logger.info("faster-whisper model loaded successfully.")
    return _model


def transcribe_file(file_path: str, language: str = "en") -> str:
    """
    Transcribe an audio/video file using local Whisper.

    Args:
        file_path: Absolute path to the audio/video file.
        language:  ISO-639-1 language code (default 'en'). Pass None for
                   automatic language detection.

    Returns:
        Full transcript as a plain string.

    Raises:
        FileNotFoundError: If file_path does not exist.
        RuntimeError:      If transcription fails.
    """
    if not Path(file_path).exists():
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    model = _get_model()

    logger.info("Transcribing '%s' with Whisper (lang=%s)…", file_path, language)

    try:
        segments, info = model.transcribe(
            file_path,
            language=language if language else None,
            beam_size=5,
            vad_filter=True,    # remove silence automatically
        )
        logger.info(
            "Detected language: '%s' (probability=%.2f)",
            info.language, info.language_probability,
        )

        transcript = " ".join(segment.text.strip() for segment in segments)
        logger.info(
            "Transcription complete: %d characters from '%s'",
            len(transcript), os.path.basename(file_path),
        )
        return transcript.strip()

    except Exception as e:
        logger.exception("Whisper transcription failed for '%s': %s", file_path, e)
        raise RuntimeError(f"Transcription failed: {e}") from e
