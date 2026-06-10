from django.apps import AppConfig


class AppConfig(AppConfig):
    # Use AutoField (INT) to match the existing auth_user.id column in MySQL.
    # The DB was created before BigAutoField became Django's default, so we
    # keep INT throughout for FK compatibility.
    default_auto_field = "django.db.models.AutoField"
    name = "app"

    def ready(self):
        from django.db import connection
        try:
            with connection.cursor() as c:
                # Check and rename auth_user_groups -> app_user_groups
                c.execute("SHOW TABLES LIKE 'app_user_groups'")
                app_user_groups_exists = bool(c.fetchone())
                c.execute("SHOW TABLES LIKE 'auth_user_groups'")
                auth_user_groups_exists = bool(c.fetchone())

                if auth_user_groups_exists and not app_user_groups_exists:
                    print("[Auto-migration] Renaming auth_user_groups -> app_user_groups...")
                    c.execute("RENAME TABLE auth_user_groups TO app_user_groups")
                    print("[Auto-migration] Successfully renamed auth_user_groups -> app_user_groups")

                # Check and rename auth_user_user_permissions -> app_user_user_permissions
                c.execute("SHOW TABLES LIKE 'app_user_user_permissions'")
                app_user_user_permissions_exists = bool(c.fetchone())
                c.execute("SHOW TABLES LIKE 'auth_user_user_permissions'")
                auth_user_user_permissions_exists = bool(c.fetchone())

                if auth_user_user_permissions_exists and not app_user_user_permissions_exists:
                    print("[Auto-migration] Renaming auth_user_user_permissions -> app_user_user_permissions...")
                    c.execute("RENAME TABLE auth_user_user_permissions TO app_user_user_permissions")
                    print("[Auto-migration] Successfully renamed auth_user_user_permissions -> app_user_user_permissions")
        except Exception as e:
            print(f"[Auto-migration] Error running table renames: {e}")

