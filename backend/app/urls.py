from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    # ── Auth ──────────────────────────────────────────────────────────────
    path("auth/register",      views.register,       name="auth_register"),
    path("auth/login",         views.login,          name="auth_login"),
    path("auth/token/refresh", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/me",            views.me,             name="auth_me"),

    # ── AI pipeline ───────────────────────────────────────────────────────
    path("ai/upload",          views.store_vectordb, name="store_vectordb"),
    path("ai/query",           views.query_vectordb, name="query_vectordb"),
    path("ai/files",           views.list_files,     name="list_files"),
]
