import unittest
from unittest.mock import patch

from app import create_app
from config import Config


class TestWhatsappWebhook(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    @patch.object(Config, "meta_verify_token", lambda: "test-verify")
    def test_webhook_verify_success(self):
        resp = self.client.get(
            "/webhook/whatsapp",
            query_string={
                "hub.mode": "subscribe",
                "hub.verify_token": "test-verify",
                "hub.challenge": "challenge-123",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data.decode(), "challenge-123")

    @patch.object(Config, "meta_verify_token", lambda: "test-verify")
    def test_webhook_verify_failure(self):
        resp = self.client.get(
            "/webhook/whatsapp",
            query_string={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong",
                "hub.challenge": "challenge-123",
            },
        )
        self.assertEqual(resp.status_code, 403)

    @patch.object(Config, "whatsapp_provider", lambda: "meta")
    @patch.object(Config, "meta_app_secret", lambda: "")
    def test_webhook_health(self):
        resp = self.client.get("/webhook/whatsapp/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("intake_version"), "inbox-v2")
        self.assertFalse(data.get("gemini_on_whatsapp_receive"))


if __name__ == "__main__":
    unittest.main()
