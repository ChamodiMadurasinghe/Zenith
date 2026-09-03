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

    @patch.object(Config, "whatsapp_provider", lambda: "meta")
    @patch.object(Config, "meta_app_secret", lambda: "")
    @patch("whatsapp_agent.is_approved_sender", return_value=False)
    def test_meta_post_unauthorized_returns_ignored_json(self, _mock_allowed):
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "94770000000",
                                        "id": "wamid.test",
                                        "type": "image",
                                        "image": {"id": "media-1"},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ],
        }
        resp = self.client.post(
            "/webhook/whatsapp",
            json=payload,
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get("status"), "ignored")
        self.assertEqual(data.get("reason"), "unauthorized_number")

    @patch.object(Config, "whatsapp_provider", lambda: "meta")
    @patch.object(Config, "meta_app_secret", lambda: "")
    @patch("whatsapp_agent.is_approved_sender", return_value=True)
    @patch(
        "whatsapp_agent.queue_agent1_from_whatsapp_media",
        return_value="queued",
    )
    @patch("whatsapp_agent._reply")
    def test_meta_post_image_queues_agent1_inbox(self, mock_reply, mock_queue, _allowed):
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "94771112222",
                                        "id": "wamid.ok",
                                        "type": "image",
                                        "image": {"id": "media-abc"},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ],
        }
        resp = self.client.post(
            "/webhook/whatsapp",
            json=payload,
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        mock_queue.assert_called_once()
        kwargs = mock_queue.call_args
        self.assertEqual(kwargs.kwargs.get("media_id") or kwargs[1].get("media_id"), "media-abc")
        mock_reply.assert_called()


if __name__ == "__main__":
    unittest.main()
