import unittest
from unittest.mock import patch

from app import create_app
from config import Config
from db import repositories as repo


class TestWhatsappInboxRoutes(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    @patch("routes.ingestion.repo.mark_whatsapp_inbox_extracted")
    @patch("routes.ingestion.extract_image_to_pending_invoice", return_value=99)
    def test_extract_whatsapp_inbox(self, mock_extract, mock_mark):
        inbox_id = repo.save_whatsapp_inbox("+94771234567", "storage/invoices/test-inbox.jpg")
        item = repo.get_whatsapp_inbox_item(inbox_id)
        self.assertEqual(item.get("status"), "pending")
        with self.client.session_transaction() as sess:
            sess["user_id"] = Config.USER_ID
        resp = self.client.post(
            f"/whatsapp-inbox/{inbox_id}/extract",
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/invoice/99/verify", resp.location or "")
        mock_extract.assert_called_once()
        mock_mark.assert_called_once_with(inbox_id, 99)

    def test_dismiss_whatsapp_inbox(self):
        inbox_id = repo.save_whatsapp_inbox("+94771234567", "storage/invoices/x.jpg")
        with self.client.session_transaction() as sess:
            sess["user_id"] = Config.USER_ID
        resp = self.client.post(f"/whatsapp-inbox/{inbox_id}/dismiss", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        item = repo.get_whatsapp_inbox_item(inbox_id)
        self.assertEqual(item.get("status"), "dismissed")


if __name__ == "__main__":
    unittest.main()
