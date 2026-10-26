import logging

import requests
from decouple import config
from django.contrib.auth import get_user_model
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .models import ROLE_ADMIN, Workspace, unique_username
from .serializers import UserSerializer
from .throttling import AuthRateThrottle

logger = logging.getLogger(__name__)
User = get_user_model()

GOOGLE_CLIENT_ID = config("GOOGLE_CLIENT_ID", default=config("google_client_id", default=""))
GITHUB_CLIENT_ID = config("GITHUB_CLIENT_ID", default="")
GITHUB_SECRET = config("GITHUB_SECRET", default="")


def _sign_in(email: str):
    """
    Find or create the account behind a verified third-party email, and issue
    tokens for it.

    Emails are lower-cased because the password path does the same: without it
    Google's "Foo@x.com" and a sign-up as "foo@x.com" become two accounts that
    cannot see each other's workspaces. Matching on the email is deliberate
    account linking, and it is only safe because callers verify the address
    first — see the email_verified check in google_login.
    """
    email = email.strip().lower()
    user = User.objects.filter(email__iexact=email).first()
    created = user is None

    if created:
        user = User.objects.create(email=email, username=unique_username(email))
        user.set_unusable_password()   # this account can only ever sign in via the provider
        user.save()
        workspace = Workspace.objects.create(name=f"{user.username}'s Workspace")
        workspace.add_member(user, ROLE_ADMIN)

    if not user.is_active:
        return None, Response({"error": "Account is disabled"}, status=status.HTTP_403_FORBIDDEN)

    refresh = RefreshToken.for_user(user)
    return Response(
        {
            "user": UserSerializer(user).data,
            "tokens": {"access": str(refresh.access_token), "refresh": str(refresh)},
        },
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    ), None


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthRateThrottle])
def google_login(request):
    """
    POST /auth/google
    Body: { "token": "<Google ID token from the browser>" }

    Verifies the ID token's signature and audience against GOOGLE_CLIENT_ID, then
    signs the holder in, creating the account and its workspace on first visit.
    """
    token = request.data.get("token")
    if not token:
        return Response({"error": "No token provided"}, status=status.HTTP_400_BAD_REQUEST)

    if not GOOGLE_CLIENT_ID:
        # Without an audience to check against, a token from any Google app would
        # be accepted, so refuse rather than verify against an empty client id.
        return Response(
            {"error": "Google sign-in is not configured on this server."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    try:
        idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), GOOGLE_CLIENT_ID)
    except Exception as exc:
        # Bad signature, wrong audience, expired token, or Google unreachable.
        logger.warning("Google ID token rejected: %s", exc)
        return Response({"error": "Invalid Google token"}, status=status.HTTP_401_UNAUTHORIZED)

    email = idinfo.get("email")
    if not email:
        return Response({"error": "No email from Google"}, status=status.HTTP_400_BAD_REQUEST)

    # Without this, anyone running a Google Workspace domain could mint a token
    # for an unverified address and take over the password account on that email.
    if str(idinfo.get("email_verified", "")).lower() not in ("true", "1"):
        return Response(
            {"error": "This Google account's email is not verified."},
            status=status.HTTP_403_FORBIDDEN,
        )

    response, error = _sign_in(email)
    return error or response


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthRateThrottle])
def github_login(request):
    """
    POST /auth/github
    Body: { "code": "..." }
    """
    code = request.data.get("code")
    if not code:
        return Response({"error": "No code provided"}, status=status.HTTP_400_BAD_REQUEST)

    if not GITHUB_CLIENT_ID or not GITHUB_SECRET:
        # Missing configuration is not a server fault; say so without a 500.
        return Response(
            {"error": "GitHub sign-in is not configured on this server."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

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

    # 3. Sign in. GitHub already told us the address is verified.
    response, error = _sign_in(primary_email)
    return error or response
