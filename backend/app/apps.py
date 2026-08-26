from django.apps import AppConfig


class AppConfig(AppConfig):
    # Use AutoField (INT) to match the existing auth_user.id column in MySQL.
    # The DB was created before BigAutoField became Django's default, so we
    # keep INT throughout for FK compatibility.
    default_auto_field = "django.db.models.AutoField"
    name = "app"

