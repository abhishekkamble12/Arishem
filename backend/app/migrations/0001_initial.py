# Generated migration — creates app_user and app_ingestedfile tables.
# app_user is our custom User model (email-based login, role via Group).

import django.contrib.auth.models
import django.contrib.auth.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="User",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                ("last_login", models.DateTimeField(blank=True, null=True, verbose_name="last login")),
                ("is_superuser", models.BooleanField(
                    default=False,
                    help_text="Designates that this user has all permissions without explicitly assigning them.",
                    verbose_name="superuser status",
                )),
                ("username", models.CharField(
                    error_messages={"unique": "A user with that username already exists."},
                    help_text="Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.",
                    max_length=150,
                    unique=True,
                    validators=[django.contrib.auth.validators.UnicodeUsernameValidator()],
                    verbose_name="username",
                )),
                ("first_name", models.CharField(blank=True, max_length=150, verbose_name="first name")),
                ("last_name", models.CharField(blank=True, max_length=150, verbose_name="last name")),
                ("is_staff", models.BooleanField(
                    default=False,
                    help_text="Designates whether the user can log into this admin site.",
                    verbose_name="staff status",
                )),
                ("is_active", models.BooleanField(
                    default=True,
                    help_text="Designates whether this user should be treated as active.",
                    verbose_name="active",
                )),
                ("date_joined", models.DateTimeField(default=django.utils.timezone.now, verbose_name="date joined")),
                ("email", models.EmailField(max_length=254, unique=True)),
                ("groups", models.ManyToManyField(
                    blank=True,
                    help_text="The groups this user belongs to.",
                    related_name="user_set",
                    related_query_name="user",
                    to="auth.group",
                    verbose_name="groups",
                )),
                ("user_permissions", models.ManyToManyField(
                    blank=True,
                    help_text="Specific permissions for this user.",
                    related_name="user_set",
                    related_query_name="user",
                    to="auth.permission",
                    verbose_name="user permissions",
                )),
            ],
            options={"db_table": "app_user"},
            managers=[("objects", django.contrib.auth.models.UserManager())],
        ),
        migrations.CreateModel(
            name="IngestedFile",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("s3_bucket", models.CharField(max_length=255)),
                ("s3_key", models.CharField(max_length=500)),
                ("file_type", models.CharField(
                    choices=[
                        ("pdf", "PDF"), ("docx", "Word Document"), ("pptx", "PowerPoint"),
                        ("mp4", "MP4 Video"), ("mov", "MOV Video"), ("avi", "AVI Video"), ("mkv", "MKV Video"),
                        ("mp3", "MP3 Audio"), ("wav", "WAV Audio"), ("flac", "FLAC Audio"),
                        ("ogg", "OGG Audio"), ("m4a", "M4A Audio"),
                    ],
                    max_length=10,
                )),
                ("chunks_stored", models.PositiveIntegerField(default=0)),
                ("ingested_at", models.DateTimeField(auto_now_add=True)),
                ("transcribe_job", models.CharField(blank=True, max_length=255, null=True)),
                ("uploaded_by", models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="ingested_files",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "ordering": ["-ingested_at"],
                "unique_together": {("s3_bucket", "s3_key")},
            },
        ),
    ]
