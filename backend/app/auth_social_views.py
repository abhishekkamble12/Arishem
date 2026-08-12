import requests
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from decouple import config

from .models import ROLE_VIEWER, Workspace
from .serializers import UserSerializer

User = get_user_model()

GOOGLE_CLIENT_ID = config("google_client_id", default="")
GITHUB_CLIENT_ID = config("GITHUB_CLIENT_ID", default="")
GITHUB_SECRET = config("GITHUB_SECRET", default="")

@api_view(["POST"])
@permission_classes([AllowAny])
def google_login(request):
    """
    POST /auth/google
    Body: { "token": "..." }
    """
    token = request.data.get("token")
    if not token:
        return Response({"error": "No token provided"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), GOOGLE_CLIENT_ID)
        email = idinfo.get("email")
        if not email:
            return Response({"error": "No email from Google"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Get or create user
        username = email.split("@")[0]
        user, created = User.objects.get_or_create(
            email=email,
            defaults={"username": username}
        )
        if created:
            user.set_unusable_password()
            group, _ = Group.objects.get_or_create(name=ROLE_VIEWER)
            user.groups.set([group])
            workspace = Workspace.objects.create(name=f"{user.username}'s Workspace")
            workspace.members.add(user)
            user.save()

        if not user.is_active:
            return Response({"error": "Account is disabled"}, status=status.HTTP_403_FORBIDDEN)

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "user": UserSerializer(user).data,
                "tokens": {
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                },
            },
            status=status.HTTP_200_OK if not created else status.HTTP_201_CREATED,
        )

    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_401_UNAUTHORIZED)


@api_view(["POST"])
@permission_classes([AllowAny])
def github_login(request):
    """
    POST /auth/github
    Body: { "code": "..." }
    """
    code = request.data.get("code")
    if not code:
        return Response({"error": "No code provided"}, status=status.HTTP_400_BAD_REQUEST)

    if not GITHUB_CLIENT_ID or not GITHUB_SECRET:
         return Response({"error": "GitHub OAuth not fully configured"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # 1. Exchange code for access token
    token_url = "https://github.com/login/oauth/access_token"
    headers = {"Accept": "application/json"}
    data = {
        "client_id": GITHUB_CLIENT_ID,
        "client_secret": GITHUB_SECRET,
        "code": code,
    }
    
    response = requests.post(token_url, headers=headers, data=data)
    if response.status_code != 200:
        return Response({"error": "Failed to authenticate with GitHub"}, status=status.HTTP_401_UNAUTHORIZED)
        
    token_data = response.json()
    access_token = token_data.get("access_token")
    if not access_token:
        return Response({"error": "No access token from GitHub"}, status=status.HTTP_401_UNAUTHORIZED)

    # 2. Fetch user's emails
    emails_url = "https://api.github.com/user/emails"
    headers = {"Authorization": f"Bearer {access_token}"}
    emails_response = requests.get(emails_url, headers=headers)
    
    if emails_response.status_code != 200:
        return Response({"error": "Failed to fetch user emails from GitHub"}, status=status.HTTP_401_UNAUTHORIZED)
        
    emails = emails_response.json()
    primary_email = next((email["email"] for email in emails if email["primary"] and email["verified"]), None)
    
    if not primary_email:
        # Fallback to any verified email
        primary_email = next((email["email"] for email in emails if email["verified"]), None)

    if not primary_email:
        return Response({"error": "No verified primary email found on GitHub"}, status=status.HTTP_400_BAD_REQUEST)

    # 3. Get or create user
    username = primary_email.split("@")[0]
    user, created = User.objects.get_or_create(
        email=primary_email,
        defaults={"username": username}
    )
    if created:
        user.set_unusable_password()
        group, _ = Group.objects.get_or_create(name=ROLE_VIEWER)
        user.groups.set([group])
        workspace = Workspace.objects.create(name=f"{user.username}'s Workspace")
        workspace.members.add(user)
        user.save()

    if not user.is_active:
        return Response({"error": "Account is disabled"}, status=status.HTTP_403_FORBIDDEN)

    refresh = RefreshToken.for_user(user)
    return Response(
        {
            "user": UserSerializer(user).data,
            "tokens": {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
        },
        status=status.HTTP_200_OK if not created else status.HTTP_201_CREATED,
    )
