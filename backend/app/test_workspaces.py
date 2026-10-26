"""
Tests — per-workspace roles: creating project workspaces, managing members, and
making sure a role in one workspace grants nothing in another.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from .models import Membership
from .tests import _get_token, _make_user

User = get_user_model()
PW = "Pass1234!"


def _auth(client, email):
    return {"HTTP_AUTHORIZATION": f"Bearer {_get_token(client, email, PW)}"}


class WorkspaceRoleTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.owner = _make_user("owner@test.com", PW, "admin")
        self.bob = _make_user("bob@test.com", PW, "admin")  # admin of *his own* workspace
        self.owner_auth = _auth(self.client, "owner@test.com")
        self.bob_auth = _auth(self.client, "bob@test.com")

        # A shared project workspace owned by `owner`
        resp = self.client.post(
            "/app/auth/workspaces", {"name": "Payments team"},
            content_type="application/json", **self.owner_auth,
        )
        self.assertEqual(resp.status_code, 201)
        self.ws = resp.json()["id"]
        self.assertEqual(resp.json()["role"], "admin")

    def _members(self, auth, ws=None):
        return self.client.get(f"/app/auth/workspaces/{ws or self.ws}/members", **auth)

    def _add(self, email, role, auth, ws=None):
        return self.client.post(
            f"/app/auth/workspaces/{ws or self.ws}/members", {"email": email, "role": role},
            content_type="application/json", **auth,
        )

    def _patch(self, user, role, auth):
        return self.client.patch(
            f"/app/auth/workspaces/{self.ws}/members/{user.id}", {"role": role},
            content_type="application/json", **auth,
        )

    def test_admin_adds_member_and_lists_them(self):
        resp = self._add("bob@test.com", "viewer", self.owner_auth)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["role"], "viewer")
        emails = {m["email"]: m["role"] for m in self._members(self.owner_auth).json()}
        self.assertEqual(emails, {"owner@test.com": "admin", "bob@test.com": "viewer"})

    def test_unknown_email_is_a_clear_404(self):
        resp = self._add("nobody@test.com", "viewer", self.owner_auth)
        self.assertEqual(resp.status_code, 404)

    def test_non_member_cannot_see_or_add(self):
        self.assertEqual(self._members(self.bob_auth).status_code, 403)
        self.assertEqual(self._add("bob@test.com", "admin", self.bob_auth).status_code, 403)

    def test_role_is_scoped_to_the_workspace(self):
        # Bob is admin of his own workspace but only a viewer in the shared one
        self._add("bob@test.com", "viewer", self.owner_auth)
        self.assertEqual(self._add("owner@test.com", "viewer", self.bob_auth).status_code, 403)
        self.assertEqual(self._patch(self.bob, "admin", self.bob_auth).status_code, 403)

        resp = self.client.post(
            "/app/ai/upload", {"s3_key": f"ws_{self.ws}/x.pdf", "workspace_id": self.ws},
            content_type="application/json", **self.bob_auth,
        )
        self.assertEqual(resp.status_code, 403)
        self.assertIn("viewer", resp.json()["error"])

    def test_viewer_can_query_but_editor_can_upload(self):
        self._add("bob@test.com", "viewer", self.owner_auth)
        with patch("app.views.rag_query", return_value={"answer": "ok", "confidence": 0.9}):
            resp = self.client.post(
                "/app/ai/query", {"question": "hi", "workspace_id": self.ws},
                content_type="application/json", **self.bob_auth,
            )
        self.assertEqual(resp.status_code, 200)

        self._patch(self.bob, "editor", self.owner_auth)
        with patch("app.views.run_ingestion_task.delay") as delay:
            delay.return_value.id = "t1"
            resp = self.client.post(
                "/app/ai/upload", {"s3_key": f"ws_{self.ws}/x.pdf", "workspace_id": self.ws},
                content_type="application/json", **self.bob_auth,
            )
        self.assertEqual(resp.status_code, 202)

    def test_last_admin_cannot_be_demoted_or_leave(self):
        self.assertEqual(self._patch(self.owner, "viewer", self.owner_auth).status_code, 400)
        resp = self.client.delete(f"/app/auth/workspaces/{self.ws}/members/{self.owner.id}", **self.owner_auth)
        self.assertEqual(resp.status_code, 400)

        # With a second admin, the first can step down
        self._add("bob@test.com", "admin", self.owner_auth)
        self.assertEqual(self._patch(self.owner, "viewer", self.owner_auth).status_code, 200)

    def test_admin_removes_member_and_member_can_leave(self):
        self._add("bob@test.com", "editor", self.owner_auth)
        resp = self.client.delete(f"/app/auth/workspaces/{self.ws}/members/{self.bob.id}", **self.owner_auth)
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(self._members(self.bob_auth).status_code, 403)

        self._add("bob@test.com", "viewer", self.owner_auth)
        resp = self.client.delete(f"/app/auth/workspaces/{self.ws}/members/{self.bob.id}", **self.bob_auth)
        self.assertEqual(resp.status_code, 204)

    def test_non_admin_cannot_remove_others(self):
        self._add("bob@test.com", "editor", self.owner_auth)
        resp = self.client.delete(f"/app/auth/workspaces/{self.ws}/members/{self.owner.id}", **self.bob_auth)
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(Membership.objects.filter(workspace_id=self.ws, user=self.owner).exists())

    def test_invalid_role_rejected(self):
        self.assertEqual(self._add("bob@test.com", "superuser", self.owner_auth).status_code, 400)

    def test_workspace_creation_is_capped(self):
        with self.settings(MAX_WORKSPACES_PER_USER=2):  # owner already administers 2 (personal + Payments)
            resp = self.client.post(
                "/app/auth/workspaces", {"name": "One too many"},
                content_type="application/json", **self.owner_auth,
            )
        self.assertEqual(resp.status_code, 400)

    def test_list_workspaces_shows_role_per_workspace(self):
        self._add("bob@test.com", "viewer", self.owner_auth)
        roles = {w["id"]: w["role"] for w in self.client.get("/app/auth/workspaces", **self.bob_auth).json()}
        self.assertEqual(roles[self.ws], "viewer")
        self.assertEqual(len(roles), 2)
