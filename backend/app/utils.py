from rest_framework import status
from rest_framework.response import Response


def resolve_workspace(request, data_dict, roles=None):
    """
    Extracts workspace_id from the request data or query params (falls back to the
    user's first workspace), checks the user is a member, and, when `roles` is
    given, that their role *in that workspace* is one of them.

    Returns:
        (workspace_id, None) on success
        (None, Response(error)) on failure
    """
    workspace_id = data_dict.get("workspace_id")
    if not workspace_id:
        first_ws = request.user.workspaces.order_by("id").first()
        if not first_ws:
            return None, Response({"error": "No workspace available."}, status=status.HTTP_400_BAD_REQUEST)
        workspace_id = first_ws.id
    else:
        try:
            workspace_id = int(workspace_id)
        except (ValueError, TypeError):
            return None, Response({"error": "workspace_id must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

    role = request.user.role_in(workspace_id)
    if role is None:
        return None, Response({"error": "Workspace not found or access denied"}, status=status.HTTP_403_FORBIDDEN)
    if roles is not None and role not in roles:
        return None, Response(
            {"error": f"This action needs one of: {', '.join(roles)} (you are {role} in this workspace)."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return workspace_id, None
