"""
Extractor — orchestrates the full ingestion pipeline:
  S3 download → text extraction → chunking → List[Document]

Supported formats:
  .pdf        — PyMuPDFLoader              (fast, page-aware)
  .docx       — Docx2txtLoader             (python-docx based)
  .pptx       — UnstructuredPowerPointLoader (slide-aware)
  .mp4/.mov/  — AWS Transcribe             (speaker-diarised transcript)
  .avi/.mkv/
  .mp3/.wav/
  .flac/.ogg/
  .m4a
"""

import logging
from pathlib import PurePosixPath
from typing import List

from langchain_community.document_loaders import (
    Docx2txtLoader,
    PyMuPDFLoader,
    UnstructuredPowerPointLoader,
)
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .Ai_service.load_data import download_from_s3, SUPPORTED_EXTENSIONS as DOC_EXTENSIONS
from .Ai_service.video_transcibing import (
    transcribe_media,
    SUPPORTED_MEDIA_EXTENSIONS,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Chunking config
# ---------------------------------------------------------------------------
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", ". ", " ", ""],
)

# Map extension → LangChain loader class (documents only)
_LOADER_MAP = {
    ".pdf":  PyMuPDFLoader,
    ".docx": Docx2txtLoader,
    ".pptx": UnstructuredPowerPointLoader,
}


def _get_loader(ext: str, file_path: str):
    loader_cls = _LOADER_MAP.get(ext)
    if loader_cls is None:
        raise ValueError(f"No loader registered for extension '{ext}'")
    return loader_cls(file_path)


def extract_and_chunk(bucket_name: str, s3_key: str) -> List[Document]:
    """
    Download a file from S3, extract its text, and split into overlapping
    chunks ready for embedding.

    Automatically routes to the correct extractor based on file extension:
      - Documents (.pdf, .docx, .pptx) → downloaded locally, parsed by LangChain
      - Media (.mp4, .mp3, etc.)       → transcribed via AWS Transcribe

    Each returned Document carries metadata:
        source     — original s3_key
        bucket     — S3 bucket name
        page       — page/slide number (documents only)
        job_name   — Transcribe job name (media only)
        media_type — file type without dot (media only)

    Args:
        bucket_name: S3 bucket name.
        s3_key:      Object key, e.g. "reports/q1.pdf" or "videos/lecture.mp4"

    Returns:
        List of LangChain Document chunks.

    Raises:
        ValueError:  Unsupported file type.
        Exception:   Propagates S3 / loader / Transcribe errors.
    """
    ext = PurePosixPath(s3_key).suffix.lower()

    # ── Media: transcribe via AWS Transcribe ─────────────────────────────
    if ext in SUPPORTED_MEDIA_EXTENSIONS:
        logger.info("Routing %s to AWS Transcribe", s3_key)
        transcript_doc = transcribe_media(bucket_name, s3_key)
        chunks = _splitter.split_documents([transcript_doc])
        logger.info("Produced %d chunks from transcript of '%s'", len(chunks), s3_key)
        return chunks

    # ── Documents: download locally and parse ────────────────────────────
    if ext in DOC_EXTENSIONS:
        with download_from_s3(bucket_name, s3_key) as file_path:
            logger.info("Loading %s file from %s", ext, file_path)
            loader = _get_loader(ext, file_path)
            pages: List[Document] = loader.load()

        if not pages:
            logger.warning("No content extracted from s3://%s/%s", bucket_name, s3_key)
            return []

        logger.info("Extracted %d page(s)/slide(s), chunking…", len(pages))

        for page in pages:
            page.metadata.setdefault("source", s3_key)
            page.metadata.setdefault("bucket", bucket_name)

        chunks = _splitter.split_documents(pages)
        logger.info("Produced %d chunks from %d page(s)/slide(s)", len(chunks), len(pages))
        return chunks

    # ── Unsupported ───────────────────────────────────────────────────────
    all_supported = sorted(DOC_EXTENSIONS | SUPPORTED_MEDIA_EXTENSIONS)
    raise ValueError(
        f"Unsupported file type '{ext}' for key '{s3_key}'. "
        f"Supported: {', '.join(all_supported)}"
    )
