from rest_framework import status
from rest_framework.response import Response

def resolve_workspace(request, data_dict):
    """
    Extracts workspace_id from the request data or query params.
    Falls back to the user's first workspace.
    Validates that the workspace_id is an integer and that the user has access.
    
    Returns:
        (workspace_id, None) on success
        (None, Response(error)) on failure
    """
    workspace_id = data_dict.get("workspace_id")
    if not workspace_id:
        first_ws = request.user.workspaces.first()
        if not first_ws:
            return None, Response({"error": "No workspace available."}, status=status.HTTP_400_BAD_REQUEST)
        workspace_id = first_ws.id
    else:
        try:
            workspace_id = int(workspace_id)
        except (ValueError, TypeError):
            return None, Response({"error": "workspace_id must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

        if not request.user.workspaces.filter(id=workspace_id).exists():
            return None, Response({"error": "Workspace not found or access denied"}, status=status.HTTP_403_FORBIDDEN)
            
    return workspace_id, None
