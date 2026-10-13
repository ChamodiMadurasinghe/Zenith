import os
import unittest
from unittest.mock import patch

from app import create_app
from config import Config
from db import repositories as repo
from db.connection import execute


class TestOnboarding(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        self.prev = repo.get_setting("onboarding_status", "")
        os.environ["ZENITH_SHOW_ONBOARDING"] = "true"

    def tearDown(self):
        if self.prev:
            repo.set_setting("onboarding_status", self.prev)
        else:
            execute("DELETE FROM app_settings WHERE setting_key = ?", ("onboarding_status",))
        os.environ.pop("ZENITH_SHOW_ONBOARDING", None)

    def _login(self):
        with self.client.session_transaction() as sess:
            sess["user_id"] = Config.USER_ID

    def test_skip_all_stops_redirect(self):
        repo.set_setting("onboarding_status", "pending")
        self._login()
        resp = self.client.get("/", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/setup", resp.headers["Location"])
        resp = self.client.post("/setup", data={"step": "welcome", "action": "skip_all"})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(repo.get_setting("onboarding_status"), "skipped")
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)

    def test_gemini_skip_enables_demo_reading(self):
        repo.set_setting("onboarding_status", "in_progress")
        self._login()
        with patch("routes.onboarding.update_keys") as mocked:
            resp = self.client.post("/setup", data={"step": "gemini", "action": "skip"})
        self.assertEqual(resp.status_code, 302)
        mocked.assert_called_once_with({"USE_FAKE_AI": "true"})

    def test_help_explains_keys_are_optional(self):
        resp = self.client.get("/help/setup")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_data(as_text=True)
        self.assertIn("Gemini", body)
        self.assertIn("Not required", body)
        self.assertIn("Google Drive", body)

    def test_health_includes_version(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["version"], Config.app_version())
        self.assertTrue(resp.get_json()["ok"])

    def test_completed_onboarding_does_not_redirect(self):
        repo.set_setting("onboarding_status", "completed")
        self._login()
        resp = self.client.get("/", follow_redirects=False)
        self.assertEqual(resp.status_code, 200)
