"""
Production DB migration helper.

Renames auth_user -> app_user (our custom User model now uses db_table='app_user'),
creates/fixes app_ingestedfile, and syncs django_migrations records.

Safe to re-run — all operations check before acting.
"""
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
django.setup()

from django.db import connection
from django.utils import timezone

with connection.cursor() as c:

    # ── 1. Rename auth_user -> app_user if needed ────────────────────────────
    c.execute("SHOW TABLES LIKE 'app_user'")
    app_user_exists = bool(c.fetchone())

    c.execute("SHOW TABLES LIKE 'auth_user'")
    auth_user_exists = bool(c.fetchone())

    if app_user_exists:
        print("app_user already exists — skipping rename")
    elif auth_user_exists:
        # Drop FK constraints that reference auth_user before renaming
        # Find FK constraints on django_admin_log
        c.execute("""
            SELECT CONSTRAINT_NAME FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'django_admin_log'
              AND REFERENCED_TABLE_NAME = 'auth_user'
        """)
        for (fk_name,) in c.fetchall():
            c.execute(f"ALTER TABLE django_admin_log DROP FOREIGN KEY `{fk_name}`")
            print(f"  Dropped FK {fk_name} on django_admin_log")

        # Find FK constraints on auth_user_groups
        c.execute("""
            SELECT CONSTRAINT_NAME FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'auth_user_groups'
              AND REFERENCED_TABLE_NAME = 'auth_user'
        """)
        for (fk_name,) in c.fetchall():
            c.execute(f"ALTER TABLE auth_user_groups DROP FOREIGN KEY `{fk_name}`")
            print(f"  Dropped FK {fk_name} on auth_user_groups")

        # Find FK constraints on auth_user_user_permissions
        c.execute("""
            SELECT CONSTRAINT_NAME FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'auth_user_user_permissions'
              AND REFERENCED_TABLE_NAME = 'auth_user'
        """)
        for (fk_name,) in c.fetchall():
            c.execute(f"ALTER TABLE auth_user_user_permissions DROP FOREIGN KEY `{fk_name}`")
            print(f"  Dropped FK {fk_name} on auth_user_user_permissions")

        # Now rename
        c.execute("RENAME TABLE auth_user TO app_user")
        print("Renamed auth_user -> app_user")
    else:
        print("Neither auth_user nor app_user exists — will be created by migrate")

    # Rename groups & user permissions tables if they exist under old names
    c.execute("SHOW TABLES LIKE 'app_user_groups'")
    app_user_groups_exists = bool(c.fetchone())
    c.execute("SHOW TABLES LIKE 'auth_user_groups'")
    auth_user_groups_exists = bool(c.fetchone())

    if auth_user_groups_exists and not app_user_groups_exists:
        c.execute("RENAME TABLE auth_user_groups TO app_user_groups")
        print("Renamed auth_user_groups -> app_user_groups")

    c.execute("SHOW TABLES LIKE 'app_user_user_permissions'")
    app_user_user_permissions_exists = bool(c.fetchone())
    c.execute("SHOW TABLES LIKE 'auth_user_user_permissions'")
    auth_user_user_permissions_exists = bool(c.fetchone())

    if auth_user_user_permissions_exists and not app_user_user_permissions_exists:
        c.execute("RENAME TABLE auth_user_user_permissions TO app_user_user_permissions")
        print("Renamed auth_user_user_permissions -> app_user_user_permissions")

    # Recreate FKs pointing to app_user
    c.execute("SHOW TABLES LIKE 'app_user_groups'")
    if c.fetchone():
        c.execute("""
            SELECT CONSTRAINT_NAME FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'app_user_groups'
              AND CONSTRAINT_NAME = 'fk_aug_user'
        """)
        if not c.fetchone():
            c.execute("""
                ALTER TABLE app_user_groups
                ADD CONSTRAINT fk_aug_user FOREIGN KEY (user_id) REFERENCES app_user(id) ON DELETE CASCADE
            """)
            print("Recreated FK fk_aug_user on app_user_groups")

    c.execute("SHOW TABLES LIKE 'app_user_user_permissions'")
    if c.fetchone():
        c.execute("""
            SELECT CONSTRAINT_NAME FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'app_user_user_permissions'
              AND CONSTRAINT_NAME = 'fk_auup_user'
        """)
        if not c.fetchone():
            c.execute("""
                ALTER TABLE app_user_user_permissions
                ADD CONSTRAINT fk_auup_user FOREIGN KEY (user_id) REFERENCES app_user(id) ON DELETE CASCADE
            """)
            print("Recreated FK fk_auup_user on app_user_user_permissions")

    c.execute("SHOW TABLES LIKE 'django_admin_log'")
    if c.fetchone():
        c.execute("""
            SELECT CONSTRAINT_NAME FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'django_admin_log'
              AND CONSTRAINT_NAME = 'fk_dal_user'
        """)
        if not c.fetchone():
            c.execute("""
                ALTER TABLE django_admin_log
                ADD CONSTRAINT fk_dal_user FOREIGN KEY (user_id) REFERENCES app_user(id) ON DELETE CASCADE
            """)
            print("Recreated FK fk_dal_user on django_admin_log")


    # ── 2. Create / fix app_ingestedfile ─────────────────────────────────────
    c.execute("SHOW TABLES LIKE 'app_ingestedfile'")
    if c.fetchone():
        # Fix FK to point to app_user if it still points to auth_user
        c.execute("""
            SELECT CONSTRAINT_NAME FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'app_ingestedfile'
              AND REFERENCED_TABLE_NAME = 'auth_user'
        """)
        rows = c.fetchall()
        for (fk_name,) in rows:
            c.execute(f"ALTER TABLE app_ingestedfile DROP FOREIGN KEY `{fk_name}`")
            c.execute(f"""
                ALTER TABLE app_ingestedfile
                ADD CONSTRAINT fk_ingestedfile_user
                    FOREIGN KEY (uploaded_by_id) REFERENCES app_user(id) ON DELETE SET NULL
            """)
            print(f"Updated app_ingestedfile FK from auth_user -> app_user")

        # Fix s3_key column length if needed
        c.execute("""
            SELECT CHARACTER_MAXIMUM_LENGTH FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'app_ingestedfile'
              AND COLUMN_NAME = 's3_key'
        """)
        row = c.fetchone()
        if row and row[0] != 500:
            c.execute("ALTER TABLE app_ingestedfile MODIFY s3_key VARCHAR(500) NOT NULL")
            print(f"Fixed s3_key: VARCHAR({row[0]}) -> VARCHAR(500)")
        else:
            print("app_ingestedfile looks correct")
    else:
        c.execute("""
            CREATE TABLE app_ingestedfile (
                id              INT           NOT NULL AUTO_INCREMENT PRIMARY KEY,
                s3_bucket       VARCHAR(255)  NOT NULL,
                s3_key          VARCHAR(500)  NOT NULL,
                file_type       VARCHAR(10)   NOT NULL,
                chunks_stored   INT UNSIGNED  NOT NULL DEFAULT 0,
                ingested_at     DATETIME(6)   NOT NULL,
                transcribe_job  VARCHAR(255)  NULL,
                uploaded_by_id  INT           NULL,
                UNIQUE KEY uq_bucket_key (s3_bucket, s3_key),
                CONSTRAINT fk_ingestedfile_user
                    FOREIGN KEY (uploaded_by_id)
                    REFERENCES app_user(id)
                    ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        print("Created app_ingestedfile")

    # ── 3. Sync django_migrations ─────────────────────────────────────────────
    c.execute(
        "SELECT COUNT(*) FROM django_migrations WHERE app=%s AND name=%s",
        ["app", "0001_initial"],
    )
    if c.fetchone()[0] == 0:
        c.execute(
            "INSERT INTO django_migrations (app, name, applied) VALUES (%s, %s, %s)",
            ["app", "0001_initial", timezone.now()],
        )
        print("Recorded app.0001_initial in django_migrations")
    else:
        print("app.0001_initial already in django_migrations")

print("\nDone. Run: python manage.py check")
