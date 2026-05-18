"""
Custom DRF permission classes for role-based access control.

Usage on a view:
    @api_view(["POST"])
    @permission_classes([IsAdminOrEditor])
    def upload(request): ...
"""

from rest_framework.permissions import BasePermission
from .models import ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER


class IsAdmin(BasePermission):
    """Only users in the 'admin' group."""
    message = "Admin role required."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.has_role(ROLE_ADMIN)
        )


class IsAdminOrEditor(BasePermission):
    """Users in 'admin' or 'editor' groups — can upload files."""
    message = "Editor or Admin role required."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.has_role(ROLE_ADMIN, ROLE_EDITOR)
        )


class IsAnyRole(BasePermission):
    """Any authenticated user regardless of role — can query and list."""
    message = "Authentication required."

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated
