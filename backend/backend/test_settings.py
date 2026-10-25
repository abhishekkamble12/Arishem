"""
Test settings — inherits everything from settings.py but switches the DB
to SQLite in-memory so tests never touch RDS.
"""
from .settings import *  # noqa: F401, F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Optional features stay covered by tests even though they default to off.
ENABLE_MEETINGS = True
ENABLE_SOCIAL_AUTH = True

# Fast (insecure) hashing — test-only, cuts ~1s off every login
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Tests log in dozens of times from one IP; the real limit is covered by its own test.
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {**REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "auth": "10000/min"}}

# Tests must not depend on the DEBUG env var: never redirect test clients to HTTPS.
SECURE_SSL_REDIRECT = False
