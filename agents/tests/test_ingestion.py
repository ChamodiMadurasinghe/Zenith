import unittest
from unittest.mock import patch

from agents.document_classifier import classify_document, is_business_document
from agents.ingestion import extract_invoice
from config import Config


class TestExtractInvoiceFakeAi(unittest.TestCase):
    def test_fake_ai_returns_mock_invoice(self):
        with patch.object(Config, "use_fake_ai", return_value=True):
            with patch("agents.ingestion.generate_with_image") as gen:
                data = extract_invoice("unused.png")
        gen.assert_not_called()
        self.assertEqual(data["invoice_no"], "WA-MOCK-001")
        self.assertEqual(data["supplier_name"], "Mock Supplier Ltd")
        self.assertEqual(data["total_amount"], 125000.0)
        self.assertEqual(data["credit_period_days"], 30)
        self.assertTrue(data["line_items"])

    def test_live_path_calls_gemini(self):
        with patch.object(Config, "use_fake_ai", return_value=False):
            with patch("agents.ingestion.generate_with_image", return_value={"invoice_no": "LIVE-1"}) as gen:
                data = extract_invoice("photo.png")
        gen.assert_called_once()
        self.assertEqual(data["invoice_no"], "LIVE-1")


class TestDocumentClassifierFakeAi(unittest.TestCase):
    def test_fake_ai_accepts_invoice(self):
        with patch.object(Config, "use_fake_ai", return_value=True):
            with patch("agents.document_classifier.generate_with_image") as gen:
                result = classify_document("unused.png")
        gen.assert_not_called()
        self.assertTrue(result["is_invoice"])
        self.assertTrue(is_business_document(result))

    def test_non_invoice_photo_is_rejected(self):
        classification = {
            "is_invoice": False,
            "document_type": "photo",
            "confidence": 0.9,
            "reason": "family photo",
        }
        self.assertFalse(is_business_document(classification))

    def test_cheque_counts_as_business_document(self):
        self.assertTrue(
            is_business_document(
                {"is_invoice": False, "document_type": "cheque", "confidence": 0.8}
            )
        )


if __name__ == "__main__":
    unittest.main()
