"""
Tests — auth flow + API endpoint smoke tests.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch

User = get_user_model()


def _make_user(email, password, role):
    user = User.objects.create_user(
        email=email, username=email.split("@")[0], password=password
    )
    group, _ = Group.objects.get_or_create(name=role)
    user.groups.set([group])
    
    from .models import Workspace
    ws = Workspace.objects.create(name=f"{user.username}'s Workspace")
    ws.members.add(user)
    return user


def _get_token(client, email, password):
    resp = client.post(
        "/app/auth/login",
        {"email": email, "password": password},
        content_type="application/json",
    )
    return resp.json()["tokens"]["access"]


class AuthTests(TestCase):

    def setUp(self):
        self.client = Client()

    def test_register_creates_viewer_by_default(self):
        resp = self.client.post(
            "/app/auth/register",
            {"email": "v@test.com", "password": "Pass1234!", "password2": "Pass1234!"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["user"]["role"], "viewer")
        self.assertIn("access", data["tokens"])

    def test_register_with_role(self):
        resp = self.client.post(
            "/app/auth/register",
            {"email": "e@test.com", "password": "Pass1234!", "password2": "Pass1234!", "role": "editor"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["user"]["role"], "editor")

    def test_login_returns_tokens(self):
        _make_user("u@test.com", "Pass1234!", "viewer")
        resp = self.client.post(
            "/app/auth/login",
            {"email": "u@test.com", "password": "Pass1234!"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.json()["tokens"])

    def test_login_wrong_password(self):
        _make_user("u2@test.com", "Pass1234!", "viewer")
        resp = self.client.post(
            "/app/auth/login",
            {"email": "u2@test.com", "password": "wrong"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)

    def test_me_requires_auth(self):
        resp = self.client.get("/app/auth/me")
        self.assertEqual(resp.status_code, 401)

    def test_me_returns_user(self):
        _make_user("me@test.com", "Pass1234!", "editor")
        token = _get_token(self.client, "me@test.com", "Pass1234!")
        resp = self.client.get(
            "/app/auth/me",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["email"], "me@test.com")
        self.assertEqual(resp.json()["role"], "editor")


class PermissionTests(TestCase):

    def setUp(self):
        self.client = Client()

        viewer = _make_user("viewer@test.com", "Pass1234!", "viewer")
        self.viewer_token = _get_token(self.client, "viewer@test.com", "Pass1234!")

        editor = _make_user("editor@test.com", "Pass1234!", "editor")
        self.editor_token = _get_token(self.client, "editor@test.com", "Pass1234!")

    def _auth(self, token):
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_upload_blocked_for_viewer(self):
        resp = self.client.post(
            "/app/ai/upload",
            {"s3_key": "test.pdf"},
            content_type="application/json",
            **self._auth(self.viewer_token),
        )
        self.assertEqual(resp.status_code, 403)

    @patch('app.views.run_ingestion_task.delay')
    def test_upload_allowed_for_editor(self, mock_delay):
        # Will fail at extraction (no real S3), but must NOT be 401 or 403
        mock_delay.return_value.id = "mock_task_id"
        resp = self.client.post(
            "/app/ai/upload",
            {"s3_key": "test.pdf"},
            content_type="application/json",
            **self._auth(self.editor_token),
        )
        self.assertNotIn(resp.status_code, [401, 403])

    def test_query_allowed_for_viewer(self):
        # Will fail at Qdrant (no real cluster), but must NOT be 401 or 403
        resp = self.client.post(
            "/app/ai/query",
            {"question": "hello"},
            content_type="application/json",
            **self._auth(self.viewer_token),
        )
        self.assertNotIn(resp.status_code, [401, 403])

    def test_files_allowed_for_viewer(self):
        resp = self.client.get(
            "/app/ai/files",
            **self._auth(self.viewer_token),
        )
        self.assertEqual(resp.status_code, 200)

    def test_unauthenticated_blocked_everywhere(self):
        for method, url, body in [
            ("post", "/app/ai/upload",  {"s3_key": "x.pdf"}),
            ("post", "/app/ai/query",   {"question": "x"}),
            ("get",  "/app/ai/files",   None),
        ]:
            if method == "get":
                resp = self.client.get(url)
            else:
                resp = self.client.post(url, body, content_type="application/json")
            self.assertEqual(resp.status_code, 401, msg=f"{method.upper()} {url} should be 401")


class WorkspaceTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_a = _make_user("user_a@test.com", "Pass1234!", "editor")
        self.token_a = _get_token(self.client, "user_a@test.com", "Pass1234!")

        self.user_b = _make_user("user_b@test.com", "Pass1234!", "editor")
        self.token_b = _get_token(self.client, "user_b@test.com", "Pass1234!")

    def test_registration_creates_workspace(self):
        resp = self.client.post(
            "/app/auth/register",
            {"email": "new_user@test.com", "password": "Pass1234!", "password2": "Pass1234!"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertIn("workspaces", resp.json()["user"])
        self.assertEqual(len(resp.json()["user"]["workspaces"]), 1)
        self.assertEqual(resp.json()["user"]["workspaces"][0]["name"], "new_user's Workspace")

    def test_list_workspaces(self):
        resp = self.client.get(
            "/app/auth/workspaces",
            HTTP_AUTHORIZATION=f"Bearer {self.token_a}"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)
        self.assertEqual(resp.json()[0]["name"], "user_a's Workspace")

    def test_cross_workspace_access_denied(self):
        ws_b = self.user_b.workspaces.first()
        # User A tries to query using User B's workspace ID
        resp = self.client.post(
            "/app/ai/query",
            {"question": "hello", "workspace_id": ws_b.id},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token_a}"
        )
        self.assertEqual(resp.status_code, 403)
