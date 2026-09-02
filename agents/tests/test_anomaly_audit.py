import unittest
from unittest.mock import MagicMock, patch

from agents.anomaly import (
    audit_invoice,
    build_agent2_chat_messages,
    check_invoice_anomalies,
)


class TestAuditInvoice(unittest.TestCase):
    def test_cold_start_insufficient_data_no_findings(self):
        extracted = {
            "invoice_no": "INV-1",
            "supplier_name": "Abans",
            "total_amount": 10000,
            "invoiced_date": "2026-01-15",
            "line_items": [{"item_code": "A", "item_name": "X", "item_qty": 1, "item_price": 10000}],
        }
        with patch("agents.anomaly.repo.get_dealer_invoice_stats", return_value={"count": 1, "avg_amount": 5000}):
            with patch("agents.anomaly.repo.get_dealer_item_history_stats", return_value={"sample_count": 0}):
                result = audit_invoice(extracted, dealer_id=5)
        self.assertEqual(result["status"], "INSUFFICIENT_DATA")
        self.assertIn("chat_messages", result)
        self.assertTrue(len(result["chat_messages"]) >= 1)

    def test_good_to_go_no_flags(self):
        extracted = {
            "invoice_no": "INV-2",
            "supplier_name": "Abans",
            "total_amount": 10000,
            "invoiced_date": "2026-01-15",
            "line_items": [{"item_code": "A", "item_name": "X", "item_qty": 1, "item_price": 10000, "item_discount": 0}],
        }
        with patch("agents.anomaly.repo.get_dealer_invoice_stats", return_value={"count": 5, "avg_amount": 12000}):
            with patch("agents.anomaly.repo.find_invoice_by_no_and_dealer", return_value=None):
                with patch("agents.anomaly.repo.get_dealer_item_history_stats", return_value={"sample_count": 5, "avg_qty": 10, "max_qty": 12, "avg_price": 10000}):
                    with patch("agents.anomaly.repo.find_recent_item_orders", return_value=[]):
                        result = audit_invoice(extracted, dealer_id=5)
        self.assertEqual(result["status"], "GOOD_TO_GO")
        self.assertEqual(result["findings"], [])

    def test_duplicate_issue_detected(self):
        extracted = {
            "invoice_no": "DUP-1",
            "supplier_name": "Abans",
            "total_amount": 10000,
            "invoiced_date": "2026-01-15",
            "line_items": [],
        }
        with patch("agents.anomaly.repo.get_dealer_invoice_stats", return_value={"count": 5, "avg_amount": 10000}):
            with patch("agents.anomaly.repo.find_invoice_by_no_and_dealer", return_value={"invoices_id": 99}):
                result = audit_invoice(extracted, dealer_id=5)
        self.assertEqual(result["status"], "ISSUE_DETECTED")
        self.assertEqual(result["risk_level"], "HIGH")

    def test_math_mismatch(self):
        extracted = {
            "invoice_no": "INV-M",
            "total_amount": 1000,
            "invoiced_date": "2026-01-15",
            "line_items": [
                {"item_code": "A", "item_qty": 2, "item_price": 400, "item_discount": 0},
            ],
        }
        result = audit_invoice(extracted, dealer_id=None)
        codes = [f["code"] for f in result["findings"]]
        self.assertIn("math_mismatch", codes)
        self.assertEqual(result["status"], "ISSUE_DETECTED")

    def test_possible_missing_discount(self):
        extracted = {
            "invoice_no": "INV-D",
            "total_amount": 1000,
            "invoiced_date": "2026-01-15",
            "line_items": [
                {"item_code": "A", "item_qty": 10, "item_price": 100, "item_discount": 0},
            ],
        }
        # Header matches pre-discount; with 10% discount lines would be 900
        extracted["line_items"][0]["item_discount"] = 10
        result = audit_invoice(extracted, dealer_id=None)
        codes = [f["code"] for f in result["findings"]]
        self.assertIn("possible_missing_discount", codes)

    def test_qty_unusual_toffee_example(self):
        extracted = {
            "invoice_no": "INV-T",
            "total_amount": 2000,
            "invoiced_date": "2026-01-15",
            "line_items": [
                {"item_code": "TOFFEE-01", "item_name": "Toffees", "item_qty": 20, "item_price": 100},
            ],
        }
        with patch("agents.anomaly.repo.get_dealer_invoice_stats", return_value={"count": 8, "avg_amount": 1000}):
            with patch("agents.anomaly.repo.find_invoice_by_no_and_dealer", return_value=None):
                with patch(
                    "agents.anomaly.repo.get_dealer_item_history_stats",
                    return_value={
                        "sample_count": 8,
                        "avg_qty": 10,
                        "max_qty": 12,
                        "avg_price": 100,
                    },
                ):
                    with patch("agents.anomaly.repo.find_recent_item_orders", return_value=[]):
                        result = audit_invoice(extracted, dealer_id=5)
        codes = [f["code"] for f in result["findings"]]
        self.assertIn("qty_unusual", codes)
        self.assertTrue(any("20" in m["content"] for m in result["chat_messages"] if "10" in m["content"]))

    def test_reorder_within_30_days(self):
        extracted = {
            "invoice_no": "INV-R",
            "total_amount": 500,
            "invoiced_date": "2026-01-15",
            "line_items": [
                {"item_code": "SKU1", "item_name": "Wire", "item_qty": 5, "item_price": 100},
            ],
        }
        with patch("agents.anomaly.repo.get_dealer_invoice_stats", return_value={"count": 5, "avg_amount": 500}):
            with patch("agents.anomaly.repo.find_invoice_by_no_and_dealer", return_value=None):
                with patch(
                    "agents.anomaly.repo.get_dealer_item_history_stats",
                    return_value={"sample_count": 3, "avg_qty": 5, "max_qty": 6, "avg_price": 100},
                ):
                    with patch(
                        "agents.anomaly.repo.find_recent_item_orders",
                        return_value=[{"invoice_no": "INV-OLD", "invoiced_date": "2026-01-01"}],
                    ):
                        result = audit_invoice(extracted, dealer_id=5)
        codes = [f["code"] for f in result["findings"]]
        self.assertIn("item_reordered_soon", codes)

    def test_chat_messages_on_issues(self):
        audit = {
            "status": "ISSUE_DETECTED",
            "findings": [
                {
                    "code": "qty_unusual",
                    "message": "test",
                    "needs_confirmation": True,
                    "chat_line": "Please confirm qty.",
                }
            ],
        }
        msgs = build_agent2_chat_messages(audit)
        self.assertTrue(len(msgs) >= 2)
        self.assertEqual(msgs[0]["role"], "agent2")

    def test_check_invoice_anomalies_adapter(self):
        extracted = {
            "invoice_no": "X",
            "total_amount": 100,
            "invoiced_date": "2026-01-15",
            "line_items": [{"item_code": "A", "item_qty": 1, "item_price": 100}],
        }
        with patch("agents.anomaly.repo.get_dealer_invoice_stats", return_value={"count": 0}):
            flags = check_invoice_anomalies(extracted, None)
        self.assertIsInstance(flags, list)


class TestReviewerGemini(unittest.TestCase):
    @patch("agents.reviewer.generate_text")
    def test_review_uses_gemini_and_lang(self, mock_text):
        mock_text.return_value = "VERDICT: approve\n\nSimple explanation here."
        from agents.reviewer import review_bundles

        review_bundles(1, [], 500000, [], lang="si", trigger="compute")
        kwargs = mock_text.call_args.kwargs
        self.assertEqual(kwargs.get("provider"), "gemini")


if __name__ == "__main__":
    unittest.main()
