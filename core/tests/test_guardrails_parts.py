import unittest
from unittest.mock import patch

from core.guardrails import collect_bundle_issues
from core.invoice_parts import apply_part_fields


def _part(invoice_id: int, amount: float, index: int, count: int, original: float = 600000.0):
    return apply_part_fields(
        {"invoices_id": invoice_id, "invoice_no": "INV-A", "total_amount": original},
        amount=amount,
        part_index=index,
        part_count=count,
        original=original,
    )


def _bundle(group: int, invoices: list) -> dict:
    return {
        "group": group,
        "cheque_date": "2026-12-01",
        "invoices": invoices,
        "total_lkr": sum(float(i["total_amount"]) for i in invoices),
    }


class TestGuardrailSplitParts(unittest.TestCase):
    def _issues(self, bundles, ceiling=500000):
        with patch("core.guardrails.audit_bundle_day_limits", return_value=[]):
            with patch("core.guardrails.repo.paying_account_id_for_dealer", return_value=1):
                return collect_bundle_issues(
                    {"bundles": bundles},
                    dealer_id=1,
                    ceiling_lkr=ceiling,
                    allow_exceed_ceiling=True,
                )

    def test_complete_three_parts_pass(self):
        bundles = [
            _bundle(1, [_part(10, 200000, 1, 3)]),
            _bundle(2, [_part(10, 200000, 2, 3)]),
            _bundle(3, [_part(10, 200000, 3, 3)]),
        ]
        issues = self._issues(bundles)
        self.assertFalse(
            any("parts" in (i or "").lower() or "incomplete" in (i or "").lower() for i in issues),
            issues,
        )

    def test_missing_part_fails(self):
        bundles = [
            _bundle(1, [_part(10, 200000, 1, 3)]),
            _bundle(2, [_part(10, 200000, 2, 3)]),
        ]
        issues = self._issues(bundles)
        self.assertTrue(any("expected 3 parts" in (i or "").lower() for i in issues), issues)

    def test_wrong_part_count_fails(self):
        bundles = [
            _bundle(1, [_part(10, 200000, 1, 2)]),
            _bundle(2, [_part(10, 200000, 2, 2)]),
            _bundle(3, [_part(10, 200000, 2, 2)]),
        ]
        issues = self._issues(bundles)
        self.assertTrue(
            any(
                "incomplete" in (i or "").lower()
                or "appears in both" in (i or "").lower()
                or "expected" in (i or "").lower()
                for i in issues
            ),
            issues,
        )


if __name__ == "__main__":
    unittest.main()
