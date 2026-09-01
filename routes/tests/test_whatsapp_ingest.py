import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import create_app
from config import Config
from core.ingestion_pipeline import PipelineResult


class TestWhatsappIngestApi(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        self.tmp = tempfile.TemporaryDirectory()
        self.queue = Path(self.tmp.name)
        self.image = self.queue / "img.jpg"
        self.image.write_bytes(b"test")

    def tearDown(self):
        self.tmp.cleanup()

    @patch.object(Config, "whatsapp_bridge_secret", lambda: "test-secret")
    @patch.object(Config, "inbound_queue_dir")
    @patch("routes.whatsapp_settings.run_whatsapp_image_pipeline")
    def test_ingest_success(self, mock_pipeline, mock_queue_dir):
        mock_queue_dir.return_value = self.queue
        mock_pipeline.return_value = PipelineResult(
            status="processed", http_status=200, invoice_id=7
        )
        resp = self.client.post(
            "/api/invoices/ingest",
            json={
                "whatsapp_message_id": "wa-1",
                "sender_phone": "+94771234567",
                "timestamp": "2026-08-30T10:00:00Z",
                "image_path": str(self.image),
            },
            headers={"X-Zenith-Bridge-Token": "test-secret"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "processed")
        self.assertEqual(data["invoice_id"], 7)

    @patch.object(Config, "whatsapp_bridge_secret", lambda: "test-secret")
    def test_ingest_unauthorized(self):
        resp = self.client.post(
            "/api/invoices/ingest",
            json={"whatsapp_message_id": "wa-1", "sender_phone": "+94", "image_path": "/x"},
            headers={"X-Zenith-Bridge-Token": "wrong"},
        )
        self.assertEqual(resp.status_code, 401)

    @patch.object(Config, "whatsapp_bridge_secret", lambda: "test-secret")
    @patch.object(Config, "inbound_queue_dir")
    def test_ingest_path_traversal(self, mock_queue_dir):
        mock_queue_dir.return_value = self.queue
        resp = self.client.post(
            "/api/invoices/ingest",
            json={
                "whatsapp_message_id": "wa-2",
                "sender_phone": "+94771234567",
                "image_path": "C:/Windows/system.ini",
            },
            headers={"X-Zenith-Bridge-Token": "test-secret"},
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
