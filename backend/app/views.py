"""
API views — three endpoints:

  POST /app/ai/upload   — ingest a file from S3 into Qdrant
  POST /app/ai/query    — ask a question, get a RAG answer
  GET  /app/ai/files    — list all ingested files
"""

import logging
from pathlib import PurePosixPath

from decouple import config
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from Services.Extractor import extract_and_chunk
from Services.Ai_service.embedding import embed_and_store
from Services.Ai_service.load_data import SUPPORTED_EXTENSIONS as DOC_EXTENSIONS
from Services.Ai_service.video_transcibing import SUPPORTED_MEDIA_EXTENSIONS
from Services.agent import query as rag_query

from .models import IngestedFile

logger = logging.getLogger(__name__)

S3_BUCKET    = config("S3_BUCKET")
ALL_SUPPORTED = sorted(DOC_EXTENSIONS | SUPPORTED_MEDIA_EXTENSIONS)


# ─────────────────────────────────────────────────────────────────────────────
# POST /app/ai/upload
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["POST"])
def store_vectordb(request):
    """
    Ingest a file from S3 into Qdrant.

    Body (JSON):
        { "s3_key": "path/to/file.pdf" }

    Accepts: .pdf  .docx  .pptx  .mp4  .mov  .avi  .mkv
             .mp3  .wav   .flac  .ogg  .m4a

    Returns 409 if the file was already ingested.
    """
    s3_key = request.data.get("s3_key", "").strip()
    if not s3_key:
        return Response({"error": "s3_key is required"}, status=status.HTTP_400_BAD_REQUEST)

    ext = PurePosixPath(s3_key).suffix.lower()
    if ext not in DOC_EXTENSIONS and ext not in SUPPORTED_MEDIA_EXTENSIONS:
        return Response(
            {"error": f"Unsupported file type '{ext}'", "supported": ALL_SUPPORTED},
            status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )

    # ── Deduplication check ───────────────────────────────────────────────
    if IngestedFile.objects.filter(s3_bucket=S3_BUCKET, s3_key=s3_key).exists():
        return Response(
            {"error": f"'{s3_key}' has already been ingested. Delete it first to re-ingest."},
            status=status.HTTP_409_CONFLICT,
        )

    # ── Extract + chunk ───────────────────────────────────────────────────
    try:
        chunks = extract_and_chunk(bucket_name=S3_BUCKET, s3_key=s3_key)
    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception("Extraction failed for '%s'", s3_key)
        return Response({"error": f"Extraction failed: {str(e)}"}, status=status.HTTP_502_BAD_GATEWAY)

    if not chunks:
        return Response(
            {"error": "No text could be extracted from the file"},
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    # ── Embed + store ─────────────────────────────────────────────────────
    try:
        stored = embed_and_store(chunks)
    except Exception as e:
        logger.exception("Embedding/storage failed for '%s'", s3_key)
        return Response({"error": f"Embedding/storage failed: {str(e)}"}, status=status.HTTP_502_BAD_GATEWAY)

    # ── Record in MySQL ───────────────────────────────────────────────────
    # Pull transcribe job name from metadata if it was a media file
    transcribe_job = None
    if chunks and "job_name" in chunks[0].metadata:
        transcribe_job = chunks[0].metadata["job_name"]

    IngestedFile.objects.create(
        s3_bucket=S3_BUCKET,
        s3_key=s3_key,
        file_type=ext.lstrip("."),
        chunks_stored=stored,
        transcribe_job=transcribe_job,
    )

    return Response(
        {
            "message": "File ingested successfully",
            "s3_key": s3_key,
            "file_type": ext.lstrip("."),
            "chunks_stored": stored,
        },
        status=status.HTTP_201_CREATED,
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /app/ai/query
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["POST"])
def query_vectordb(request):
    """
    Ask a question over all ingested documents.

    Body (JSON):
        {
            "question": "What are the key findings?",
            "top_k": 5          ← optional, default from RAG_TOP_K env var
        }

    Returns:
        {
            "answer":  "...",
            "sources": ["report.pdf", "lecture.mp4"],
            "chunks":  5
        }
    """
    question = request.data.get("question", "").strip()
    if not question:
        return Response({"error": "question is required"}, status=status.HTTP_400_BAD_REQUEST)

    top_k = request.data.get("top_k", None)
    kwargs = {}
    if top_k is not None:
        try:
            kwargs["top_k"] = int(top_k)
        except (ValueError, TypeError):
            return Response({"error": "top_k must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        result = rag_query(question, **kwargs)
    except Exception as e:
        logger.exception("RAG query failed for question: '%s'", question[:80])
        return Response({"error": f"Query failed: {str(e)}"}, status=status.HTTP_502_BAD_GATEWAY)

    return Response(result, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────────
# GET /app/ai/files
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["GET"])
def list_files(request):
    """
    List all files that have been ingested into Qdrant.

    Returns:
        {
            "files": [
                {
                    "s3_key": "reports/q1.pdf",
                    "file_type": "pdf",
                    "chunks_stored": 42,
                    "ingested_at": "2026-05-16T10:30:00Z"
                },
                ...
            ],
            "total": 3
        }
    """
    files = IngestedFile.objects.all().values(
        "s3_key", "file_type", "chunks_stored", "ingested_at"
    )
    return Response({"files": list(files), "total": len(files)}, status=status.HTTP_200_OK)
