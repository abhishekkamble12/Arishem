"""
Tests — Google sign-in. Offline: Google's token verification is faked, so no
test needs a network call or a real client id.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from .models import Membership, unique_username

User = get_user_model()
CLIENT_ID = "test-client-id.apps.googleusercontent.com"


def _idinfo(email, verified=True):
    return {"email": email, "email_verified": verified, "aud": CLIENT_ID}


@patch("app.auth_social_views.GOOGLE_CLIENT_ID", CLIENT_ID)
class GoogleLoginTests(TestCase):

    def setUp(self):
        self.client = Client()

    def _login(self, idinfo, token="any-token"):
        with patch("app.auth_social_views.id_token.verify_oauth2_token", return_value=idinfo):
            return self.client.post("/app/auth/google", {"token": token},
                                    content_type="application/json")

    def test_first_sign_in_creates_the_account_and_its_workspace(self):
        resp = self._login(_idinfo("newcomer@example.com"))
        self.assertEqual(resp.status_code, 201, resp.content)
        body = resp.json()
        self.assertIn("access", body["tokens"])
        self.assertEqual(body["user"]["email"], "newcomer@example.com")
        # Same deal as a password sign-up: admin of your own workspace, nothing else.
        self.assertEqual(body["user"]["workspaces"][0]["role"], "admin")
        user = User.objects.get(email="newcomer@example.com")
        self.assertEqual(Membership.objects.filter(user=user).count(), 1)

    def test_second_sign_in_reuses_the_account(self):
        self._login(_idinfo("repeat@example.com"))
        resp = self._login(_idinfo("repeat@example.com"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(User.objects.filter(email="repeat@example.com").count(), 1)

    def test_a_google_account_cannot_be_signed_into_with_a_password(self):
        self._login(_idinfo("nopassword@example.com"))
        resp = self.client.post("/app/auth/login",
                                {"email": "nopassword@example.com", "password": "Pass1234!"},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 401)

    def test_unverified_google_email_is_refused(self):
        """
        Otherwise someone running a Workspace domain could mint a token for an
        address they do not own and take over the password account on it.
        """
        resp = self._login(_idinfo("victim@example.com", verified=False))
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(User.objects.filter(email="victim@example.com").exists())

    def test_mixed_case_google_email_links_to_the_existing_account(self):
        self.client.post("/app/auth/register",
                         {"email": "person@example.com", "password": "Pass1234!",
                          "password2": "Pass1234!"},
                         content_type="application/json")
        resp = self._login(_idinfo("Person@Example.com"))
        self.assertEqual(resp.status_code, 200, "should link, not create a second account")
        self.assertEqual(User.objects.filter(email__iexact="person@example.com").count(), 1)

    def test_a_rejected_token_is_401_and_creates_nothing(self):
        with patch("app.auth_social_views.id_token.verify_oauth2_token",
                   side_effect=ValueError("Token has wrong audience")):
            resp = self.client.post("/app/auth/google", {"token": "forged"},
                                    content_type="application/json")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["error"], "Invalid Google token")
        self.assertEqual(User.objects.count(), 0)

    def test_missing_token_is_400(self):
        resp = self.client.post("/app/auth/google", {}, content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_disabled_account_cannot_sign_in(self):
        self._login(_idinfo("banned@example.com"))
        User.objects.filter(email="banned@example.com").update(is_active=False)
        resp = self._login(_idinfo("banned@example.com"))
        self.assertEqual(resp.status_code, 403)


class GoogleNotConfiguredTests(TestCase):

    @patch("app.auth_social_views.GOOGLE_CLIENT_ID", "")
    def test_without_a_client_id_the_endpoint_refuses_rather_than_verifying(self):
        """
        Verifying against an empty audience would accept a token minted for any
        Google app, so an unconfigured server must not try.
        """
        resp = Client().post("/app/auth/google", {"token": "whatever"},
                             content_type="application/json")
        self.assertEqual(resp.status_code, 503)


class UniqueUsernameTests(TestCase):

    def test_same_local_part_on_different_domains_does_not_collide(self):
        """This raised IntegrityError (a 500) on the second signup."""
        User.objects.create(email="a@one.com", username=unique_username("a@one.com"))
        second = unique_username("a@two.com")
        self.assertEqual(second, "a2")
        User.objects.create(email="a@two.com", username=second)

    def test_registration_survives_a_colliding_local_part(self):
        c = Client()
        for email in ("dup@one.com", "dup@two.com", "dup@three.com"):
            resp = c.post("/app/auth/register",
                          {"email": email, "password": "Pass1234!", "password2": "Pass1234!"},
                          content_type="application/json")
            self.assertEqual(resp.status_code, 201, f"{email}: {resp.content}")
        self.assertEqual(User.objects.filter(email__endswith=".com").count(), 3)

    def test_unusable_local_parts_fall_back_to_something_valid(self):
        self.assertEqual(unique_username("...@example.com"), "user")
        self.assertEqual(unique_username("a+b.c@example.com"), "a_b.c")
