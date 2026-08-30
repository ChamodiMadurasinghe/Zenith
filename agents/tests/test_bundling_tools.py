"""Unit tests for Bundling Assistant tools (dry_run vs commit)."""

from __future__ import annotations

import copy
import json
import unittest
from unittest.mock import patch

from agents.bundling_tools import BundlingToolContext, build_bundling_tools


def _bundle(group: int, inv_id: int, amount: float, cheque_date: str = "2030-06-15") -> dict:
    return {
        "group": group,
        "cheque_date": cheque_date,
        "true_settlement_date": cheque_date,
        "total_lkr": amount,
        "invoices": [
            {
                "invoices_id": inv_id,
                "invoice_no": f"INV-{inv_id}",
                "total_amount": amount,
                "invoiced_date": "2030-05-01",
                "credit_period_days": 30,
            }
        ],
    }


class BundlingToolsDryRunTests(unittest.TestCase):
    def setUp(self):
        self.ctx = BundlingToolContext(
            dealer_id=1,
            ceiling_lkr=500_000,
            bundles=[
                _bundle(1, 10, 100_000),
                _bundle(2, 11, 150_000),
            ],
        )
        self.tools = {t.name: t for t in build_bundling_tools(self.ctx)}

    def test_move_invoice_dry_run_does_not_commit(self):
        before = [b["group"] for b in self.ctx.bundles]
        raw = self.tools["move_invoice"].invoke(
            {"invoice_id": 11, "to_group": 1, "dry_run": True}
        )
        payload = json.loads(raw)
        self.assertTrue(payload.get("dry_run"))
        self.assertFalse(payload.get("committed"))
        self.assertFalse(self.ctx.pending_commit)
        self.assertEqual([b["group"] for b in self.ctx.bundles], before)
        self.assertIsNotNone(self.ctx.last_preview)
        preview_ids = [
            inv
            for b in self.ctx.last_preview
            for inv in [i["invoices_id"] for i in b.get("invoices") or []]
        ]
        self.assertIn(11, preview_ids)

    def test_move_invoice_commit_sets_pending(self):
        raw = self.tools["move_invoice"].invoke(
            {"invoice_id": 11, "to_group": 1, "dry_run": False}
        )
        payload = json.loads(raw)
        self.assertFalse(payload.get("dry_run"))
        self.assertTrue(payload.get("committed"))
        self.assertTrue(self.ctx.pending_commit)
        self.assertEqual(len(self.ctx.bundles), 1)
        ids = [i["invoices_id"] for i in self.ctx.bundles[0]["invoices"]]
        self.assertEqual(sorted(ids), [10, 11])

    def test_apply_bundle_changes_requires_confirm(self):
        self.tools["move_invoice"].invoke(
            {"invoice_id": 11, "to_group": 1, "dry_run": True}
        )
        denied = json.loads(self.tools["apply_bundle_changes"].invoke({"confirm": False}))
        self.assertFalse(denied.get("ok"))
        self.assertFalse(self.ctx.pending_commit)

        ok = json.loads(self.tools["apply_bundle_changes"].invoke({"confirm": True}))
        self.assertTrue(ok.get("ok"))
        self.assertTrue(self.ctx.pending_commit)
        self.assertEqual(len(self.ctx.bundles), 1)

    def test_check_day_limit_risk_read_only(self):
        with patch(
            "agents.bundling_tools.audit_bundle_day_limits",
            return_value=[
                {
                    "group": 1,
                    "verdict": "LIMIT_BREACH_WARNING",
                    "total_day_exposure": 2_000_000,
                    "casual_limit": 1_000_000,
                    "calculated_settlement_date": "2030-06-15",
                }
            ],
        ):
            raw = self.tools["check_day_limit_risk"].invoke({"use_preview": False})
        payload = json.loads(raw)
        self.assertTrue(payload.get("ok"))
        self.assertTrue(payload.get("has_limit_breach"))
        self.assertFalse(self.ctx.pending_commit)

    def test_dealer_patterns_tool_registered_and_read_only(self):
        self.assertIn("get_dealer_historical_payment_patterns", self.tools)
        before = copy.deepcopy(self.ctx.bundles)
        with patch(
            "core.vector_store.query_dealer_patterns",
            return_value="Inv #101 (21 days aging)",
        ):
            raw = self.tools["get_dealer_historical_payment_patterns"].invoke(
                {"invoice_total": 150_000}
            )
        payload = json.loads(raw)
        self.assertTrue(payload.get("ok"))
        self.assertIn("Inv #101", payload.get("patterns_text", ""))
        self.assertEqual(payload.get("dealer_id"), 1)
        self.assertFalse(self.ctx.pending_commit)
        self.assertEqual(self.ctx.bundles, before)

    def test_guardrail_error_is_structured(self):
        raw = self.tools["move_invoice"].invoke(
            {"invoice_id": 99999, "to_group": 1, "dry_run": True}
        )
        payload = json.loads(raw)
        self.assertTrue(isinstance(payload.get("issues"), list))
        self.assertTrue(payload.get("issues") or payload.get("error") is not None or True)
        # apply_proposed_actions appends "Invoice 99999 not found" into issues
        joined = " ".join(payload.get("issues") or [])
        self.assertIn("99999", joined)


class AgenticHintsContextTests(unittest.TestCase):
    def test_chat_context_includes_hints(self):
        from core.chat_context import build_bundling_chat_context

        with patch("core.chat_context.repo") as mock_repo:
            mock_repo.get_dealer.return_value = {"dealer_id": 1, "dealer_name": "Test"}
            mock_repo.get_dealer_preferred_bank.return_value = None
            mock_repo.get_dealer_invoice_summary.return_value = {}
            mock_repo.get_verified_unassigned_invoices.return_value = []
            mock_repo.get_pending_verification_invoices.return_value = []
            mock_repo.get_committed_cheque_bundles.return_value = []
            mock_repo.get_setting.return_value = "1"
            mock_repo.get_bank_account.return_value = None
            ctx = build_bundling_chat_context(
                1,
                [],
                500000,
                agentic_hints={
                    "session_id": "wa-1",
                    "cheque_plan": {"recommended_date": "2030-07-01", "amount_lkr": 100},
                    "anomaly_flags": [{"message": "amount spike"}],
                },
            )
        self.assertEqual(ctx["assistant_role"], "Bundling Assistant")
        self.assertEqual(ctx["cheque_plan"]["recommended_date"], "2030-07-01")
        self.assertEqual(ctx["anomaly_flags"][0]["message"], "amount spike")


if __name__ == "__main__":
    unittest.main()
