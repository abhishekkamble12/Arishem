"""
Django settings for Arishem backend.
All secrets and environment-specific values come from environment variables.
Never hardcode credentials here.
"""

import os
import sys
from pathlib import Path

from decouple import config

# Export Groq credentials
_groq_key = config("GROQ_API_KEY", default=None)
if _groq_key:
    os.environ["GROQ_API_KEY"] = _groq_key







# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent

# Make Services/ importable as a top-level package (sits alongside app/ and backend/)
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# ── Security ──────────────────────────────────────────────────────────────────
SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1").split(",")

# ── Application ───────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",  # enables refresh token blacklisting
    "app",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "app.middleware.RequestLoggingMiddleware",
]

# Browser origins allowed to call the API (comma-separated, no wildcard).
# Auth is a Bearer token in a header, not a cookie, so credentials aren't needed.
CORS_ALLOWED_ORIGINS = [
    o.strip() for o in config("CORS_ALLOWED_ORIGINS", default="http://localhost:5173").split(",") if o.strip()
]

# Origins Django accepts POSTs from behind a TLS-terminating proxy. The API itself
# authenticates with a Bearer token, but the admin and the DRF browsable API are
# cookie-based and reject form posts without this.
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in config("CSRF_TRUSTED_ORIGINS", default="").split(",") if o.strip()
]

if not DEBUG:
    SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
    SECURE_REDIRECT_EXEMPT = [r"^app/health$"]  # container/LB health checks arrive over plain HTTP
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  # behind the host's TLS proxy
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_CONTENT_TYPE_NOSNIFF = True

# Disable redirect from /path to /path/ — our URLs have no trailing slashes
# and POST bodies are lost on 301 redirects in many clients.
APPEND_SLASH = False

ROOT_URLCONF = "backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "backend.wsgi.application"

# ── Database ──────────────────────────────────────────────────────────────────
# DATABASE_URL (e.g. postgres://user:pass@host:5432/dbname?sslmode=require) is the
# managed-Postgres path. Unset, it falls back to a local SQLite file for development.
_database_url = config("DATABASE_URL", default="")
if _database_url:
    import dj_database_url

    DATABASES = {"default": dj_database_url.parse(_database_url, conn_max_age=60, conn_health_checks=True)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": config("DB_NAME", default=BASE_DIR / "db.sqlite3"),
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# Custom user model — must be set before first migration
AUTH_USER_MODEL = "app.User"

# ── Password validation ────────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ── Internationalisation ───────────────────────────────────────────────────────
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ── Static files ──────────────────────────────────────────────────────────────
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# ── REST Framework ────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "cost_control": "100/min",
        "auth": config("THROTTLE_RATE_AUTH", default="20/min"),
    },
}

# ── JWT ───────────────────────────────────────────────────────────────────────
from datetime import timedelta

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME":  timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS":  True,
    "BLACKLIST_AFTER_ROTATION": True,  # old refresh tokens are invalidated immediately
    "ALGORITHM": "HS256",
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# ── Logging ───────────────────────────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "arishem.requests": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# ── Celery & Task Broker Settings ─────────────────────────────────────────────
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="amqp://guest:guest@localhost:5672//")
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default="redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

# Periodic jobs (run by `celery -A backend beat`)
CELERY_BEAT_SCHEDULE = {
    "reconcile-stuck-ingestions": {
        "task": "app.tasks.reconcile_stuck_ingestions",
        "schedule": 600.0,  # every 10 minutes
    },
}

# Ingestion Queue Limits (Backpressure management)
MAX_INGESTION_QUEUE_DEPTH = config("MAX_INGESTION_QUEUE_DEPTH", default=50, cast=int)


# ── Optional features (off for the first deployment) ──────────────────────────
# Code stays in the repo; only routes and accepted file types are gated.
# Meetings needs `pip install -r requirements-optional.txt` (Whisper, yt-dlp, ffmpeg).
ENABLE_MEETINGS = config("ENABLE_MEETINGS", default=False, cast=bool)
# Social sign-in is on by default: the endpoints answer 503 with a readable
# message until GOOGLE_CLIENT_ID / GITHUB_* are set, so enabling it costs nothing
# and the login page's buttons are not wired to routes that do not exist.
ENABLE_SOCIAL_AUTH = config("ENABLE_SOCIAL_AUTH", default=True, cast=bool)
GOOGLE_CLIENT_ID = config("GOOGLE_CLIENT_ID", default=config("google_client_id", default=""))

# ── Object storage ────────────────────────────────────────────────────────────
STORAGE_BACKEND = config("STORAGE_BACKEND", default="local")  # "local" | "s3"
OBJECT_STORAGE_BUCKET = config("OBJECT_STORAGE_BUCKET", default="arishem-documents")
OBJECT_STORAGE_ENDPOINT_URL = config("OBJECT_STORAGE_ENDPOINT_URL", default="")
OBJECT_STORAGE_ACCESS_KEY_ID = config("OBJECT_STORAGE_ACCESS_KEY_ID", default="")
OBJECT_STORAGE_SECRET_ACCESS_KEY = config("OBJECT_STORAGE_SECRET_ACCESS_KEY", default="")
OBJECT_STORAGE_REGION = config("OBJECT_STORAGE_REGION", default="us-east-1")
if STORAGE_BACKEND not in ("local", "s3"):
    raise ValueError("STORAGE_BACKEND must be 'local' or 's3'")

# ── Signup, input and cost limits ─────────────────────────────────────────────
# Roles are per workspace: a new user is admin of their own personal workspace and
# gets access to others only when that workspace's admin adds them.

MAX_WORKSPACES_PER_USER = config("MAX_WORKSPACES_PER_USER", default=5, cast=int)

# USD per million tokens, for turning the recorded token counts into a cost.
# Deliberately 0.0 by default: the rates belong to whoever runs this and change
# without notice, so the monitoring endpoint reports $0.00 until they are set
# rather than showing a number this project invented.
LLM_INPUT_COST_PER_MTOK = config("LLM_INPUT_COST_PER_MTOK", default=0.0, cast=float)
LLM_OUTPUT_COST_PER_MTOK = config("LLM_OUTPUT_COST_PER_MTOK", default=0.0, cast=float)
MAX_QUESTION_CHARS = config("MAX_QUESTION_CHARS", default=1000, cast=int)
MAX_TOP_K = config("MAX_TOP_K", default=10, cast=int)
MAX_UPLOAD_MB = config("MAX_UPLOAD_MB", default=25, cast=int)
# Per-user daily cap on /ai/query (each query can cost up to 4 LLM calls).
# Counted from PredictionLog, so it survives restarts and works across workers.
DAILY_QUERY_QUOTA = config("DAILY_QUERY_QUOTA", default=100, cast=int)

# ── Cache (throttle counters) ─────────────────────────────────────────────────
# Per-process memory by default; set CACHE_URL=redis://host:6379/2 so rate limits
# are shared across Gunicorn workers and survive restarts.
_cache_url = config("CACHE_URL", default="")
if _cache_url:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": _cache_url}}
