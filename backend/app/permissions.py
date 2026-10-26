"""
Permissions.

Roles are per workspace (see models.Membership), so a DRF permission class cannot
decide on its own. Views require authentication here and then call
`utils.resolve_workspace(request, data, roles=...)`, which checks the caller's
role in the workspace being acted on.
"""

from rest_framework.permissions import BasePermission


class IsAnyRole(BasePermission):
    """Any authenticated user. Workspace role is enforced by resolve_workspace()."""
    message = "Authentication required."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)
