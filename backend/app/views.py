import logging

from decouple import config
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from Services.Extractor import extract_and_chunk
from Services.Ai_service.embedding import embed_and_store
from Services.Ai_service.load_data import SUPPORTED_EXTENSIONS as DOC_EXTENSIONS
from Services.Ai_service.video_transcibing import SUPPORTED_MEDIA_EXTENSIONS

logger = logging.getLogger(__name__)

S3_BUCKET = config("S3_BUCKET")

ALL_SUPPORTED = sorted(DOC_EXTENSIONS | SUPPORTED_MEDIA_EXTENSIONS)


@api_view(["POST"])
def store_vectordb(request):
    """
    POST /app/ai/upload
    Body (JSON): { "s3_key": "path/to/file.pdf" }

    Accepts documents (.pdf, .docx, .pptx) and media (.mp4, .mp3, etc.).
    Downloads/transcribes the file, chunks the text, embeds with Bedrock Titan,
    and stores vectors in Qdrant.
    """
    s3_key = request.data.get("s3_key", "").strip()
    if not s3_key:
        return Response(
            {"error": "s3_key is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Validate extension before doing any S3 work
    from pathlib import PurePosixPath
    ext = PurePosixPath(s3_key).suffix.lower()
    if ext not in DOC_EXTENSIONS and ext not in SUPPORTED_MEDIA_EXTENSIONS:
        return Response(
            {
                "error": f"Unsupported file type '{ext}'",
                "supported": ALL_SUPPORTED,
            },
            status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )

    try:
        chunks = extract_and_chunk(bucket_name=S3_BUCKET, s3_key=s3_key)
    except Exception as e:
        logger.exception("Failed to extract content from S3 key '%s'", s3_key)
        return Response(
            {"error": f"Extraction failed: {str(e)}"},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    if not chunks:
        return Response(
            {"error": "No text could be extracted from the file"},
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    try:
        stored = embed_and_store(chunks)
    except Exception as e:
        logger.exception("Failed to embed/store chunks for key '%s'", s3_key)
        return Response(
            {"error": f"Embedding/storage failed: {str(e)}"},
            status=status.HTTP_502_BAD_GATEWAY,
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
