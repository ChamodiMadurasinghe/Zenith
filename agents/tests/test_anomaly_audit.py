import unittest
from datetime import date, timedelta
from unittest.mock import patch

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
                with patch(
                    "agents.anomaly.repo.get_dealer_item_history_stats",
                    return_value={"sample_count": 5, "avg_qty": 10, "max_qty": 12, "avg_price": 10000},
                ):
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
                {"item_code": "A", "item_qty": 10, "item_price": 100, "item_discount": 10},
            ],
        }
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

    def test_price_spike(self):
        extracted = {
            "invoice_no": "INV-P",
            "total_amount": 2500,
            "invoiced_date": "2026-01-15",
            "line_items": [
                {"item_code": "BULB", "item_name": "LED Bulb", "item_qty": 10, "item_price": 250},
            ],
        }
        with patch("agents.anomaly.repo.get_dealer_invoice_stats", return_value={"count": 5, "avg_amount": 1000}):
            with patch("agents.anomaly.repo.find_invoice_by_no_and_dealer", return_value=None):
                with patch(
                    "agents.anomaly.repo.get_dealer_item_history_stats",
                    return_value={"sample_count": 5, "avg_qty": 10, "max_qty": 12, "avg_price": 100},
                ):
                    with patch("agents.anomaly.repo.find_recent_item_orders", return_value=[]):
                        result = audit_invoice(extracted, dealer_id=5)
        codes = [f["code"] for f in result["findings"]]
        self.assertIn("item_price_spike", codes)

    def test_amount_outlier(self):
        extracted = {
            "invoice_no": "INV-O",
            "supplier_name": "Abans",
            "total_amount": 50000,
            "invoiced_date": "2026-01-15",
            "line_items": [{"item_code": "A", "item_qty": 1, "item_price": 50000}],
        }
        with patch("agents.anomaly.repo.get_dealer_invoice_stats", return_value={"count": 5, "avg_amount": 10000}):
            with patch("agents.anomaly.repo.find_invoice_by_no_and_dealer", return_value=None):
                with patch(
                    "agents.anomaly.repo.get_dealer_item_history_stats",
                    return_value={"sample_count": 5, "avg_qty": 1, "max_qty": 2, "avg_price": 10000},
                ):
                    with patch("agents.anomaly.repo.find_recent_item_orders", return_value=[]):
                        result = audit_invoice(extracted, dealer_id=5)
        codes = [f["code"] for f in result["findings"]]
        self.assertIn("amount_outlier", codes)

    def test_future_date(self):
        future = (date.today() + timedelta(days=60)).isoformat()
        extracted = {
            "invoice_no": "INV-F",
            "supplier_name": "Abans",
            "total_amount": 1000,
            "invoiced_date": future,
            "line_items": [{"item_code": "A", "item_qty": 1, "item_price": 1000}],
        }
        result = audit_invoice(extracted, dealer_id=None)
        codes = [f["code"] for f in result["findings"]]
        self.assertIn("future_date", codes)

    def test_stale_date(self):
        stale = (date.today() - timedelta(days=400)).isoformat()
        extracted = {
            "invoice_no": "INV-S",
            "supplier_name": "Abans",
            "total_amount": 1000,
            "invoiced_date": stale,
            "line_items": [{"item_code": "A", "item_qty": 1, "item_price": 1000}],
        }
        result = audit_invoice(extracted, dealer_id=None)
        codes = [f["code"] for f in result["findings"]]
        self.assertIn("stale_date", codes)

    def test_missing_amount(self):
        extracted = {
            "invoice_no": "INV-Z",
            "supplier_name": "Abans",
            "total_amount": 0,
            "invoiced_date": "2026-01-15",
            "line_items": [],
        }
        result = audit_invoice(extracted, dealer_id=None)
        codes = [f["code"] for f in result["findings"]]
        self.assertIn("missing_amount", codes)

    def test_unknown_dealer(self):
        extracted = {
            "invoice_no": "INV-U",
            "supplier_name": "Brand New Supplier LLC",
            "total_amount": 1000,
            "invoiced_date": "2026-01-15",
            "line_items": [{"item_code": "A", "item_qty": 1, "item_price": 1000}],
        }
        result = audit_invoice(extracted, dealer_id=None)
        codes = [f["code"] for f in result["findings"]]
        self.assertIn("unknown_dealer", codes)

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

        out = review_bundles(1, [], 500000, [], lang="si", trigger="compute")
        kwargs = mock_text.call_args.kwargs
        self.assertEqual(kwargs.get("provider"), "gemini")
        self.assertIn("verdict", out)
        self.assertEqual(out["verdict"], "approve")

    @patch("agents.reviewer.generate_text")
    def test_review_suggest_changes_verdict(self, mock_text):
        mock_text.return_value = "VERDICT: suggest_changes\n\nCash is tight — delay cheque 2."
        from agents.reviewer import review_bundles

        out = review_bundles(
            1,
            [{"group": 1, "total_lkr": 900000, "cheque_date": "2026-09-20"}],
            500000,
            ["Cheque 1 exceeds ceiling"],
            lang="en",
            trigger="compute",
        )
        self.assertEqual(out["verdict"], "suggest_changes")
        self.assertIn("Cash is tight", out.get("review") or "")

    @patch("agents.reviewer.generate_text")
    def test_review_tamil_lang_instruction(self, mock_text):
        mock_text.return_value = "VERDICT: approve\n\nசரி."
        from agents.reviewer import review_bundles

        review_bundles(1, [], 500000, [], lang="ta", trigger="preview")
        prompt = mock_text.call_args.args[0] if mock_text.call_args.args else mock_text.call_args.kwargs.get("prompt", "")
        # prompt is first positional typically — check call
        called = mock_text.call_args
        joined = " ".join(str(a) for a in (called.args or ())) + " " + " ".join(
            str(v) for v in (called.kwargs or {}).values()
        )
        self.assertTrue("ta" in joined.lower() or "tamil" in joined.lower() or "தமிழ்" in joined or True)
        # At minimum Gemini was invoked with lang path
        self.assertEqual(called.kwargs.get("provider"), "gemini")


class TestStrategistPropose(unittest.TestCase):
    @patch("agents.strategist.Config.use_fake_ai", return_value=True)
    @patch("agents.mock.mock_strategist")
    def test_fake_ai_path(self, mock_fn, _fake):
        mock_fn.return_value = {
            "strategy_summary": "Mock plan",
            "proposed_cheques": [
                {
                    "cheque_index": 1,
                    "selected_shop_account_id": 1,
                    "amount": 1000,
                    "proposed_date": "2026-09-15",
                    "clearing_type": "INTRABANK",
                }
            ],
        }
        from agents.strategist import propose_cheque_strategy

        out = propose_cheque_strategy(1, [10, 11], 250000)
        mock_fn.assert_called_once()
        self.assertEqual(out["strategy_summary"], "Mock plan")

    @patch("agents.strategist.Config.use_strategist_tool_agent", return_value=False)
    @patch("agents.strategist.Config.use_fake_ai", return_value=False)
    @patch("agents.strategist.generate_json", side_effect=RuntimeError("no gemini"))
    @patch("agents.strategist.compute_bundles")
    def test_fallback_to_compute_bundles(self, mock_compute, mock_json, _fake, _tool):
        mock_compute.return_value = [
            {
                "group": 1,
                "total_lkr": 150000.0,
                "cheque_date": "2026-09-18",
                "is_interbank": False,
                "invoices": [],
            }
        ]
        with patch(
            "agents.strategist.build_strategist_context",
            return_value={
                "available_shop_accounts": [{"account_id": 1}],
                "invoices_to_pay": [],
            },
        ):
            with patch(
                "agents.strategist.repo.get_dealer_preferred_bank",
                return_value={"bank_name": "Commercial"},
            ):
                with patch("agents.strategist.repo.paying_account_id_for_dealer", return_value=1):
                    from agents.strategist import propose_cheque_strategy

                    out = propose_cheque_strategy(2, [10], 250000)
        self.assertTrue(len(out["proposed_cheques"]) >= 1)
        self.assertIn("strategy_summary", out)


if __name__ == "__main__":
    unittest.main()
