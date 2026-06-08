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
