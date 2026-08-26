"""
Audio Processor — YouTube download + audio conversion utilities.

Provides two main functions:
  - download_youtube(url, output_dir)  → downloads best audio from a YouTube URL
  - convert_to_wav(file_path)          → converts any audio/video to 16kHz mono WAV

Dependencies:
  - yt-dlp   (pip install yt-dlp)
  - pydub    (pip install pydub)
  - ffmpeg   must be installed system-wide and on PATH
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def download_youtube(url: str, output_dir: str | None = None) -> str:
    """
    Download the best audio stream from a YouTube URL using yt-dlp.

    Args:
        url:        Full YouTube video URL.
        output_dir: Directory to save the downloaded file. Defaults to a
                    system temp directory.

    Returns:
        Absolute path to the downloaded audio file (webm/mp4/m4a format).

    Raises:
        RuntimeError: If yt-dlp fails or is not installed.
    """
    try:
        import yt_dlp  # noqa: F401 — just check it's importable
    except ImportError:
        raise RuntimeError(
            "yt-dlp is not installed. Run: pip install yt-dlp"
        )

    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="arishem_yt_")

    output_dir = str(Path(output_dir).resolve())
    os.makedirs(output_dir, exist_ok=True)

    # yt-dlp output template — %(title)s.%(ext)s is human-readable
    output_template = os.path.join(output_dir, "%(id)s.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
    }

    logger.info("Downloading YouTube audio from: %s", url)
    try:
        import yt_dlp
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # After FFmpegExtractAudio post-processor, file is .mp3
            video_id = info.get("id", "audio")
            downloaded_path = os.path.join(output_dir, f"{video_id}.mp3")

            if not Path(downloaded_path).exists():
                # Fallback: find any file in output_dir
                files = list(Path(output_dir).glob("*"))
                if not files:
                    raise RuntimeError("yt-dlp ran but no file was produced.")
                downloaded_path = str(files[0])

        logger.info("Downloaded to: %s", downloaded_path)
        return downloaded_path

    except Exception as e:
        logger.exception("YouTube download failed for URL '%s': %s", url, e)
        raise RuntimeError(f"Failed to download YouTube audio: {e}") from e


def convert_to_wav(file_path: str, output_dir: str | None = None) -> str:
    """
    Convert any audio or video file to 16kHz mono WAV using ffmpeg.

    This normalises the audio to a format that Whisper handles optimally.

    Args:
        file_path:  Path to the source audio/video file.
        output_dir: Where to save the WAV file. Defaults to the same
                    directory as the source file.

    Returns:
        Absolute path to the converted WAV file.

    Raises:
        FileNotFoundError: If file_path does not exist.
        RuntimeError:      If ffmpeg conversion fails.
    """
    source = Path(file_path).resolve()
    if not source.exists():
        raise FileNotFoundError(f"Source file not found: {file_path}")

    if output_dir is None:
        output_dir = str(source.parent)

    wav_path = Path(output_dir) / (source.stem + ".wav")

    if wav_path.exists():
        logger.info("WAV already exists at '%s', skipping conversion.", wav_path)
        return str(wav_path)

    cmd = [
        "ffmpeg",
        "-i", str(source),
        "-ar", "16000",       # 16kHz sample rate (Whisper's native)
        "-ac", "1",           # mono
        "-c:a", "pcm_s16le",  # 16-bit PCM
        "-y",                 # overwrite if exists
        str(wav_path),
    ]

    logger.info("Converting '%s' → '%s' via ffmpeg…", source.name, wav_path.name)
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=600,  # 10-minute timeout for long videos
        )
        if result.returncode != 0:
            err = result.stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"ffmpeg exited with code {result.returncode}: {err}")

        logger.info("Conversion complete: %s", wav_path)
        return str(wav_path)

    except FileNotFoundError:
        raise RuntimeError(
            "ffmpeg is not installed or not on PATH. "
            "Please install ffmpeg: https://ffmpeg.org/download.html"
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("ffmpeg conversion timed out (>10 minutes).")
    except Exception as e:
        logger.exception("ffmpeg conversion failed: %s", e)
        raise RuntimeError(f"Audio conversion failed: {e}") from e


def cleanup_temp_files(*paths: str) -> None:
    """Delete temporary files after processing to free disk space."""
    for path in paths:
        try:
            if path and Path(path).exists():
                Path(path).unlink()
                logger.debug("Deleted temp file: %s", path)
        except Exception as e:
            logger.warning("Failed to delete temp file '%s': %s", path, e)
