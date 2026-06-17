import logging
from celery import shared_task
from django.contrib.auth import get_user_model
from Services.Extractor import extract_and_chunk
from Services.Ai_service.embedding import embed_and_store
from .models import IngestedFile, Workspace
from decouple import config

logger = logging.getLogger(__name__)
S3_BUCKET = config("S3_BUCKET")

@shared_task(bind=True)
def run_ingestion_task(self, s3_key: str, user_id: int, workspace_id: int, file_id: int):
    """
    Celery background task for file ingestion (extraction + embedding + storage).
    """
    User = get_user_model()
    try:
        user = User.objects.get(id=user_id)
        workspace = Workspace.objects.get(id=workspace_id)
        ingested_file = IngestedFile.objects.get(id=file_id)
    except Exception as e:
        logger.exception("Failed to load DB models for task")
        return f"Model loading failed: {str(e)}"

    # Update status to PROCESSING
    ingested_file.status = 'PROCESSING'
    ingested_file.save()

    try:
        # 1. Extraction & Chunking
        chunks = extract_and_chunk(bucket_name=S3_BUCKET, s3_key=s3_key)
        if not chunks:
            raise ValueError("No text could be extracted from the file")

        # 2. Embedding & Storage
        stored = embed_and_store(chunks, workspace.id, uploaded_by=user.email)

        # 3. Update metadata
        transcribe_job = None
        if chunks and "job_name" in chunks[0].metadata:
            transcribe_job = chunks[0].metadata["job_name"]

        ingested_file.chunks_stored = stored
        ingested_file.transcribe_job = transcribe_job
        ingested_file.status = 'SUCCESS'
        ingested_file.save()
        logger.info("Successfully ingested '%s' via task", s3_key)
        return f"Ingested {stored} chunks"

    except Exception as e:
        logger.exception("Background ingestion failed for '%s'", s3_key)
        ingested_file.status = 'FAILED'
        ingested_file.error_message = str(e)
        ingested_file.save()
        raise e


@shared_task
def reconcile_stuck_ingestions():
    """
    Reconciliation job to resolve the dual-write consistency problem.
    Finds any file stuck in PENDING/PROCESSING for over 30 minutes and marks it as FAILED.
    """
    from django.utils import timezone
    from datetime import timedelta

    cutoff = timezone.now() - timedelta(minutes=30)
    stuck_files = IngestedFile.objects.filter(
        status__in=['PENDING', 'PROCESSING'],
        ingested_at__lt=cutoff
    )

    count = stuck_files.count()
    if count > 0:
        logger.warning("Found %d stuck ingestion records. Marking as FAILED.", count)
        for f in stuck_files:
            f.status = 'FAILED'
            f.error_message = "Ingestion timed out during background processing (stuck in queue > 30 mins)."
            f.save()

    return f"Reconciled {count} records."
