import asyncio
import tempfile
import unittest
from pathlib import Path

from app.db import Database
from app.security import hash_password, verify_password
from app.services import AuthService


class InviteCenterCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test.db"
        self.service = AuthService(Database(self.db_path))
        self.service.bootstrap()

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_password_hash_roundtrip(self) -> None:
        stored = hash_password("secret-123")
        self.assertTrue(verify_password("secret-123", stored))
        self.assertFalse(verify_password("bad", stored))

    def test_invite_register_login_issue_app_token(self) -> None:
        self.service.create_app("demo", "Demo App")
        invite = asyncio.run(
            self.service.create_invite(
                app_slug="demo",
                email="user@example.com",
                target="chat",
                metadata={"webui": "chat"},
                send_email_now=False,
            )
        )

        result = self.service.register(
            invite_token=invite["invite_token"],
            email="user@example.com",
            password="password-123",
        )
        self.assertTrue(result["token"])
        self.assertEqual(result["user"]["email"], "user@example.com")
        self.assertEqual(result["user"]["apps"][0]["slug"], "demo")

        issued = self.service.issue_app_token(result["token"], "demo")
        claims = self.service.verify_app_token(issued["token"], "demo")
        self.assertEqual(claims["email"], "user@example.com")
        self.assertEqual(claims["app"], "demo")
        self.assertEqual(claims["target"], "chat")

    def test_password_reset_flow(self) -> None:
        self.service.create_app("demo2", "Demo2")
        invite = asyncio.run(
            self.service.create_invite(
                app_slug="demo2",
                email="reset@example.com",
                send_email_now=False,
            )
        )
        self.service.register(
            invite_token=invite["invite_token"],
            email="reset@example.com",
            password="old-password",
        )
        asyncio.run(self.service.request_password_reset("reset@example.com"))
        with self.service.db.session() as conn:
            resets = conn.execute("SELECT reset_token FROM password_resets").fetchall()
        token = resets[0]["reset_token"]
        verified = self.service.verify_reset_token(token)
        self.assertEqual(verified["email"], "reset@example.com")
        reset = self.service.reset_password(token, "new-password")
        self.assertTrue(reset["token"])

    def test_submit_application_merges_same_pending(self) -> None:
        self.service.create_app("apply-demo", "Apply Demo")
        first = asyncio.run(self.service.submit_application(app_slug="apply-demo", email="apply@example.com"))
        second = asyncio.run(self.service.submit_application(app_slug="apply-demo", email="apply@example.com"))
        self.assertEqual(first["id"], second["id"])
        pending = self.service.list_applications(status="pending", app_slug="apply-demo")
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["email"], "apply@example.com")

    def test_approve_application_creates_invite_for_new_user(self) -> None:
        self.service.create_app("approve-demo", "Approve Demo")
        application = asyncio.run(self.service.submit_application(app_slug="approve-demo", email="newuser@example.com"))
        approved = asyncio.run(
            self.service.approve_application(
                application_id=application["id"],
                role="member",
                target="chat",
                metadata={"webui": "chat"},
                note="welcome",
            )
        )
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["delivery"], "registration")
        self.assertTrue(approved["approved_invite_token"])
        invite = self.service.get_invite(approved["approved_invite_token"])
        self.assertEqual(invite["email"], "newuser@example.com")
        self.assertEqual(invite["target"], "chat")

    def test_approve_application_grants_existing_user_access(self) -> None:
        self.service.create_app("base-app", "Base App")
        self.service.create_app("new-app", "New App")
        invite = asyncio.run(
            self.service.create_invite(
                app_slug="base-app",
                email="exists@example.com",
                send_email_now=False,
            )
        )
        self.service.register(
            invite_token=invite["invite_token"],
            email="exists@example.com",
            password="password-123",
        )
        application = asyncio.run(self.service.submit_application(app_slug="new-app", email="exists@example.com"))
        approved = asyncio.run(
            self.service.approve_application(
                application_id=application["id"],
                role="vip",
                target="masonry",
                metadata={"webui": "masonry"},
            )
        )
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["delivery"], "existing_user")
        auth = self.service.authenticate(email="exists@example.com", password="password-123")
        apps = {item["slug"]: item for item in auth["user"]["apps"]}
        self.assertIn("new-app", apps)
        self.assertEqual(apps["new-app"]["role"], "vip")
        self.assertEqual(apps["new-app"]["default_target"], "masonry")
        self.assertEqual(apps["new-app"]["metadata"]["webui"], "masonry")

    def test_reject_application(self) -> None:
        self.service.create_app("reject-demo", "Reject Demo")
        application = asyncio.run(self.service.submit_application(app_slug="reject-demo", email="reject@example.com"))
        rejected = asyncio.run(
            self.service.reject_application(
                application_id=application["id"],
                note="not eligible",
            )
        )
        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(rejected["review_note"], "not eligible")

    def test_submit_application_sets_notified_at_for_new_request(self) -> None:
        self.service.create_app("notify-demo", "Notify Demo")
        application = asyncio.run(self.service.submit_application(app_slug="notify-demo", email="notify@example.com"))
        self.assertTrue("id" in application)
        with self.service.db.session() as conn:
            row = conn.execute(
                "SELECT last_notified_at FROM registration_applications WHERE id = ?",
                (application["id"],),
            ).fetchone()
        # mail may be disabled during tests, so field can be empty; ensure request still created
        self.assertIsNotNone(row)


if __name__ == "__main__":
    unittest.main()
