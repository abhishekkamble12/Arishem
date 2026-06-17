from django.contrib.auth.models import AbstractUser, Group
from django.db import models


# ── Roles ─────────────────────────────────────────────────────────────────────
# We use Django's built-in Group model as the role carrier.
ROLE_ADMIN  = "admin"
ROLE_EDITOR = "editor"
ROLE_VIEWER = "viewer"
ALL_ROLES   = [ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER]


class Workspace(models.Model):
    """
    Groups users and ingested files to provide SaaS-style tenant isolation.
    """
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    members = models.ManyToManyField("User", related_name="workspaces")

    def __str__(self):
        return self.name


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
    status         = models.CharField(
        max_length=20,
        choices=[
            ('PENDING', 'Pending'),
            ('PROCESSING', 'Processing'),
            ('SUCCESS', 'Success'),
            ('FAILED', 'Failed')
        ],
        default='SUCCESS'
    )
    error_message  = models.TextField(blank=True, null=True)
    uploaded_by    = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="ingested_files",
    )
    workspace      = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="files",
    )

    class Meta:
        unique_together = ("s3_bucket", "s3_key")
        ordering = ["-ingested_at"]

    def __str__(self):
        return f"{self.s3_key} ({self.file_type}) — {self.chunks_stored} chunks"


# ── AI Observability & Monitoring ─────────────────────────────────────────────

class PredictionLog(models.Model):
    """
    Logs every prediction/RAG query made by users for observability.
    """
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="predictions")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    input_text = models.TextField()
    prediction_text = models.TextField()
    response_time_ms = models.PositiveIntegerField()
    confidence = models.FloatField(null=True, blank=True) # E.g., avg retrieval score
    error_msg = models.TextField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"Prediction {self.id} | {self.response_time_ms}ms"


class DriftLog(models.Model):
    """
    Records events when data drift is detected (e.g., avg retrieval confidence drops).
    """
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="drifts")
    drift_score = models.FloatField()
    is_drift_detected = models.BooleanField(default=True)
    reference_count = models.IntegerField(default=50)
    current_count = models.IntegerField(default=50)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"Drift {self.id} | Score: {self.drift_score}"
