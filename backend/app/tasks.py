import logging

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from Services.Ai_service.embedding import delete_file_vectors, embed_and_store
from Services.Extractor import extract_and_chunk

from .models import IngestedFile, Workspace

logger = logging.getLogger(__name__)
OBJECT_STORAGE_BUCKET = settings.OBJECT_STORAGE_BUCKET

MEDIA_TYPES = {"mp4", "mov", "avi", "mkv", "mp3", "wav", "flac", "ogg", "m4a"}


@shared_task(bind=True)
def run_ingestion_task(self, s3_key: str, user_id: int, workspace_id: int, file_id: int):
    """
    Celery background task for file ingestion (extraction + embedding + storage).

    Idempotent: if the broker redelivers the task, a file that already
    reached SUCCESS is skipped, and any vectors left over from a previous
    partial attempt are removed before re-embedding.
    """
    User = get_user_model()
    try:
        user = User.objects.get(id=user_id)
        workspace = Workspace.objects.get(id=workspace_id)
        ingested_file = IngestedFile.objects.get(id=file_id)
    except Exception as e:
        logger.exception("Failed to load DB models for task")
        return f"Model loading failed: {str(e)}"

    if ingested_file.status == 'SUCCESS':
        logger.info("File #%d already ingested; skipping duplicate task", file_id)
        return f"Already ingested ({ingested_file.chunks_stored} chunks)"

    # Update status to PROCESSING
    ingested_file.status = 'PROCESSING'
    ingested_file.error_message = None
    ingested_file.save(update_fields=["status", "error_message"])

    try:
        # 1. Extraction & Chunking
        chunks = extract_and_chunk(bucket_name=OBJECT_STORAGE_BUCKET, s3_key=s3_key)
        if not chunks:
            raise ValueError("No text could be extracted from the file")

        # Citations should show the name the user uploaded, not the storage key
        display_name = ingested_file.original_filename or s3_key
        for chunk in chunks:
            chunk.metadata["source"] = display_name

        # 2. Embedding & Storage (clear any partial write from an earlier attempt)
        delete_file_vectors(file_id, workspace.id)
        stored = embed_and_store(chunks, workspace.id, uploaded_by=user.email, file_id=file_id)

        # 3. Update metadata
        transcribe_job = chunks[0].metadata.get("job_name")

        ingested_file.chunks_stored = stored
        ingested_file.transcribe_job = transcribe_job
        ingested_file.status = 'SUCCESS'
        ingested_file.last_indexed_timestamp = timezone.now()
        ingested_file.save()
        logger.info("Successfully ingested '%s' via task", s3_key)

        # Trigger meeting intelligence analysis if audio/video or meeting category
        if ingested_file.file_type in MEDIA_TYPES or ingested_file.document_category == 'meeting':
            logger.info("Queuing meeting analysis task for file #%d", file_id)
            run_meeting_analysis_task.delay(file_id, [c.page_content for c in chunks])

        return f"Ingested {stored} chunks"

    except Exception as e:
        logger.exception("Background ingestion failed for '%s'", s3_key)
        ingested_file.status = 'FAILED'
        ingested_file.error_message = str(e)
        ingested_file.save(update_fields=["status", "error_message"])
        raise


@shared_task
def run_youtube_ingestion_task(url: str, user_id: int, workspace_id: int, file_id: int):
    """
    Download a YouTube video's audio, transcribe it locally with Whisper,
    embed the transcript and queue meeting analysis.

    Runs in a worker because download + transcription can take minutes,
    far longer than an HTTP request should be held open.
    """
    from langchain_core.documents import Document
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from Services.meeting.audio_processor import cleanup_temp_files, convert_to_wav, download_youtube
    from Services.meeting.transcriber import transcribe_file

    User = get_user_model()
    try:
        user = User.objects.get(id=user_id)
        ingested_file = IngestedFile.objects.get(id=file_id)
    except Exception as e:
        logger.exception("Failed to load DB models for YouTube task")
        return f"Model loading failed: {str(e)}"

    if ingested_file.status == 'SUCCESS':
        return f"Already ingested ({ingested_file.chunks_stored} chunks)"

    ingested_file.status = 'PROCESSING'
    ingested_file.save(update_fields=["status"])

    audio_file = wav_file = None
    try:
        audio_file = download_youtube(url)
        wav_file = convert_to_wav(audio_file)
        transcript = transcribe_file(wav_file)

        splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=150)
        doc = Document(page_content=transcript, metadata={"source": url, "media_type": "youtube"})
        chunks = splitter.split_documents([doc])

        delete_file_vectors(file_id, workspace_id)
        stored = embed_and_store(chunks, workspace_id, uploaded_by=user.email, file_id=file_id)

        ingested_file.chunks_stored = stored
        ingested_file.status = 'SUCCESS'
        ingested_file.last_indexed_timestamp = timezone.now()
        ingested_file.save()

        run_meeting_analysis_task.delay(file_id, [c.page_content for c in chunks])
        return f"Ingested {stored} chunks"

    except Exception as e:
        logger.exception("YouTube ingestion failed for %s", url)
        ingested_file.status = 'FAILED'
        ingested_file.error_message = str(e)
        ingested_file.save(update_fields=["status", "error_message"])
        raise
    finally:
        cleanup_temp_files(audio_file, wav_file)


@shared_task
def run_meeting_analysis_task(file_id: int, chunk_texts: list = None):
    """
    Celery task to run meeting intelligence:
      1. Generates meeting title
      2. Performs map-reduce summarization
      3. Extracts action items, key decisions, and open questions
      4. Saves results in MeetingAnalysis model
    """
    from Services.meeting import (
        extract_structured_meeting_data,
        generate_title,
        summarize,
    )

    from .models import MeetingAnalysis

    try:
        ingested_file = IngestedFile.objects.get(id=file_id)
    except IngestedFile.DoesNotExist:
        logger.error("Meeting analysis failed: IngestedFile #%d not found", file_id)
        return

    logger.info("Starting meeting analysis for file #%d (%s)", file_id, ingested_file.original_filename)

    full_transcript = "\n\n".join(chunk_texts) if chunk_texts else ""

    # Generate insights
    title = generate_title(full_transcript)
    summary = summarize(full_transcript)

    # Extract structured data in one LLM call
    structured_data = extract_structured_meeting_data(full_transcript)
    action_items = structured_data.get("action_items", [])
    key_decisions = structured_data.get("key_decisions", [])
    open_questions = structured_data.get("open_questions", [])

    # Save to MeetingAnalysis model
    analysis, _ = MeetingAnalysis.objects.update_or_create(
        file=ingested_file,
        defaults={
            "title": title,
            "summary": summary,
            "action_items": action_items,
            "key_decisions": key_decisions,
            "open_questions": open_questions,
            "full_transcript": full_transcript,
        }
    )

    # Also update IngestedFile metadata
    ingested_file.title = title
    ingested_file.summary = summary
    ingested_file.document_category = 'meeting'
    ingested_file.save()

    logger.info("Meeting analysis completed for file #%d: '%s'", file_id, title)
    return f"Analyzed meeting #{file_id}"



@shared_task
def reconcile_stuck_ingestions():
    """
    Reconciliation job to resolve the dual-write consistency problem.
    Finds any file stuck in PENDING/PROCESSING for over 30 minutes and marks it as FAILED.
    """
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
