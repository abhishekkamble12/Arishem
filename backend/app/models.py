from django.db import models


class IngestedFile(models.Model):
    """
    Tracks every file that has been successfully ingested into Qdrant.
    Used to prevent re-ingesting the same S3 object and to give the
    frontend a list of available documents.
    """

    class FileType(models.TextChoices):
        PDF   = "pdf",  "PDF"
        DOCX  = "docx", "Word Document"
        PPTX  = "pptx", "PowerPoint"
        MP4   = "mp4",  "MP4 Video"
        MOV   = "mov",  "MOV Video"
        AVI   = "avi",  "AVI Video"
        MKV   = "mkv",  "MKV Video"
        MP3   = "mp3",  "MP3 Audio"
        WAV   = "wav",  "WAV Audio"
        FLAC  = "flac", "FLAC Audio"
        OGG   = "ogg",  "OGG Audio"
        M4A   = "m4a",  "M4A Audio"

    s3_bucket    = models.CharField(max_length=255)
    s3_key       = models.CharField(max_length=1024)
    file_type    = models.CharField(max_length=10, choices=FileType.choices)
    chunks_stored = models.PositiveIntegerField(default=0)
    ingested_at  = models.DateTimeField(auto_now_add=True)
    # Optional: store the Transcribe job name for media files
    transcribe_job = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        # Prevent the same S3 object from being ingested twice
        unique_together = ("s3_bucket", "s3_key")
        ordering = ["-ingested_at"]

    def __str__(self):
        return f"{self.s3_key} ({self.file_type}) — {self.chunks_stored} chunks"
