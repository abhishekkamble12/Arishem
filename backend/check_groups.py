"""Check auth_user_groups table structure and FK targets."""
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
django.setup()

from django.db import connection
with connection.cursor() as c:
    # Check what table auth_user_groups FKs point to
    c.execute("""
        SELECT CONSTRAINT_NAME, TABLE_NAME, COLUMN_NAME,
               REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
        FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'auth_user_groups'
          AND REFERENCED_TABLE_NAME IS NOT NULL
    """)
    print("auth_user_groups FKs:")
    for row in c.fetchall():
        print(" ", row)

    # Check what table app_user FKs point to
    c.execute("""
        SELECT CONSTRAINT_NAME, TABLE_NAME, COLUMN_NAME,
               REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
        FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = DATABASE()
          AND REFERENCED_TABLE_NAME IN ('app_user', 'auth_user')
    """)
    print("\nAll FKs pointing to app_user or auth_user:")
    for row in c.fetchall():
        print(" ", row)

    # Check if app_user exists and its column types
    c.execute("SHOW TABLES LIKE 'app_user'")
    print("\napp_user exists:", bool(c.fetchone()))

    c.execute("SHOW TABLES LIKE 'auth_user'")
    print("auth_user exists:", bool(c.fetchone()))
