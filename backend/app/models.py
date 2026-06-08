from django.contrib.auth.models import AbstractUser, Group
from django.db import models


# ── Roles ─────────────────────────────────────────────────────────────────────
# We use Django's built-in Group model as the role carrier.
ROLE_ADMIN  = "admin"
ROLE_EDITOR = "editor"
ROLE_VIEWER = "viewer"
ALL_ROLES   = [ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER]


class User(AbstractUser):
    """
    Custom user model — extends Django's AbstractUser.
    Role is stored via Django's Group membership (one group per user).

    Always use AUTH_USER_MODEL / get_user_model() to reference this.
    """
    email = models.EmailField(unique=True)

    # Use email as the login identifier instead of username
    USERNAME_FIELD  = "email"
    REQUIRED_FIELDS = ["username"]   # kept for createsuperuser compatibility

    class Meta:
        db_table = "app_user"

    @property
    def role(self) -> str:
        """Return the user's role name, defaulting to viewer."""
        group = self.groups.first()
        return group.name if group else ROLE_VIEWER

    def has_role(self, *roles: str) -> bool:
        return self.role in roles

    def __str__(self):
        return f"{self.email} ({self.role})"


# ── Ingested file tracker ─────────────────────────────────────────────────────

class IngestedFile(models.Model):
    """
    Tracks every file successfully ingested into Qdrant.
    Records which user uploaded it for audit purposes.
    """

    class FileType(models.TextChoices):
        PDF  = "pdf",  "PDF"
        DOCX = "docx", "Word Document"
        PPTX = "pptx", "PowerPoint"
        MP4  = "mp4",  "MP4 Video"
        MOV  = "mov",  "MOV Video"
        AVI  = "avi",  "AVI Video"
        MKV  = "mkv",  "MKV Video"
        MP3  = "mp3",  "MP3 Audio"
        WAV  = "wav",  "WAV Audio"
        FLAC = "flac", "FLAC Audio"
        OGG  = "ogg",  "OGG Audio"
        M4A  = "m4a",  "M4A Audio"

    # ── FIX: these two fields were missing from the model ────────────────────
    s3_bucket      = models.CharField(max_length=255)
    # 500 chars keeps us well under MySQL's 3072-byte unique-index limit (utf8mb4 = 4 bytes/char)
    s3_key         = models.CharField(max_length=500)

    file_type      = models.CharField(max_length=10, choices=FileType.choices)
    chunks_stored  = models.PositiveIntegerField(default=0)
    ingested_at    = models.DateTimeField(auto_now_add=True)
    transcribe_job = models.CharField(max_length=255, blank=True, null=True)
    uploaded_by    = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="ingested_files",
    )

    class Meta:
        unique_together = ("s3_bucket", "s3_key")
        ordering = ["-ingested_at"]

    def __str__(self):
        return f"{self.s3_key} ({self.file_type}) — {self.chunks_stored} chunks"
