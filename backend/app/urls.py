from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    # ── Auth ──────────────────────────────────────────────────────────────
    path("auth/register",       views.register,            name="auth_register"),
    path("auth/login",          views.login,               name="auth_login"),
    path("auth/token/refresh",  TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/me",             views.me,                  name="auth_me"),
    path("auth/workspaces",     views.list_workspaces,     name="list_workspaces"),

    # ── AI pipeline ───────────────────────────────────────────────────────
    path("ai/upload",           views.store_vectordb,      name="store_vectordb"),
    path("ai/upload-direct",    views.upload_direct,       name="upload_direct"),
    path("ai/query",            views.query_vectordb,      name="query_vectordb"),
    path("ai/files",            views.list_files,          name="list_files"),
    path("ai/files/delete",     views.delete_file,         name="delete_file"),
    path("ai/tasks/<str:task_id>", views.check_task_status, name="check_task_status"),
    path("ai/monitoring",       views.get_monitoring_stats, name="monitoring_stats"),
]
