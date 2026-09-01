import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from config import Config
from core.ingestion_pipeline import run_whatsapp_image_pipeline
from db import repositories as repo


class TestIngestionPipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.queue = self.root / "queue"
        self.upload = self.root / "upload"
        self.queue.mkdir()
        self.upload.mkdir()
        self.image = self.queue / "test.jpg"
        self.image.write_bytes(b"fake-image")

        self.queue_patch = patch.object(Config, "inbound_queue_dir", lambda: self.queue)
        self.upload_patch = patch.object(Config, "UPLOAD_FOLDER", self.upload)
        self.fake_patch = patch.object(Config, "use_fake_ai", lambda: True)
        self.queue_patch.start()
        self.upload_patch.start()
        self.fake_patch.start()

        repo.ensure_whatsapp_allowed_senders_schema()
        repo.ensure_inbound_messages_schema()
        repo.ensure_unprocessed_media_schema()
        if not repo.is_sender_allowed("+94771234567"):
            repo.add_allowed_sender("+94771234567", "Test Supplier")

    def tearDown(self):
        self.queue_patch.stop()
        self.upload_patch.stop()
        self.fake_patch.stop()
        self.tmp.cleanup()

    @patch("core.ingestion_pipeline._save_pipeline_pending_invoice", return_value=42)
    @patch("agents.anomaly.check_invoice_anomalies", return_value=[])
    def test_happy_path_processed(self, _mock_anomaly, _mock_save):
        wa_id = f"msg-{uuid.uuid4().hex}"
        result = run_whatsapp_image_pipeline(
            wa_msg_id=wa_id,
            sender_phone="+94771234567",
            image_path=str(self.image),
            received_at="2026-08-30T10:00:00Z",
        )
        self.assertEqual(result.status, "processed")
        self.assertEqual(result.http_status, 200)
        self.assertEqual(result.invoice_id, 42)

    def test_ignored_sender(self):
        result = run_whatsapp_image_pipeline(
            wa_msg_id=f"msg-{uuid.uuid4().hex}",
            sender_phone="+94770000000",
            image_path=str(self.image),
        )
        self.assertEqual(result.status, "ignored_sender")
        self.assertEqual(result.http_status, 200)

    @patch("agents.document_classifier.classify_document")
    def test_rejected_non_invoice(self, mock_classify):
        mock_classify.return_value = {
            "is_invoice": False,
            "document_type": "photo",
            "confidence": 0.9,
            "reason": "family photo",
        }
        result = run_whatsapp_image_pipeline(
            wa_msg_id=f"msg-{uuid.uuid4().hex}",
            sender_phone="+94771234567",
            image_path=str(self.image),
        )
        self.assertEqual(result.status, "rejected_non_invoice")
        self.assertIsNotNone(result.log_id)

    @patch("core.ingestion_pipeline._save_pipeline_pending_invoice", return_value=42)
    @patch("agents.anomaly.check_invoice_anomalies", return_value=[])
    def test_idempotent_duplicate(self, _a, _mock_save):
        wa_id = f"msg-dup-{uuid.uuid4().hex}"
        first = run_whatsapp_image_pipeline(
            wa_msg_id=wa_id,
            sender_phone="+94771234567",
            image_path=str(self.image),
        )
        second = run_whatsapp_image_pipeline(
            wa_msg_id=wa_id,
            sender_phone="+94771234567",
            image_path=str(self.image),
        )
        self.assertEqual(first.status, "processed", first.message)
        self.assertTrue(second.duplicate)


if __name__ == "__main__":
    unittest.main()
