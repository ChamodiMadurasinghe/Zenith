"""Tests for dealer payment pattern document builder."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from core.dealer_patterns import build_dealer_pattern_document


def _cheque(
    cheque_id: int,
    invoices: list[dict],
    *,
    acc_id: int = 1,
    clearance: str = "2026-04-15",
) -> dict:
    return {
        "cheque_id": cheque_id,
        "user_bank_acc_id": acc_id,
        "verification_status": 1,
        "clearance_date": clearance,
        "invoices": invoices,
    }


def _inv(
    inv_id: int,
    invoice_no: str,
    invoiced_date: str = "2026-03-01",
    *,
    part_index: int = 1,
    part_count: int = 1,
    total_amount: float = 100_000,
) -> dict:
    return {
        "invoices_id": inv_id,
        "invoice_no": invoice_no,
        "invoiced_date": invoiced_date,
        "part_index": part_index,
        "part_count": part_count,
        "total_amount": total_amount,
    }


class DealerPatternsTests(unittest.TestCase):
    @patch("core.dealer_patterns.repo.get_dealer")
    @patch("core.dealer_patterns.repo.get_dealer_committed_payment_history")
    def test_unbundled_only_no_average(self, mock_history, mock_dealer):
        mock_dealer.return_value = {"dealer_name": "ABD Traders"}
        mock_history.return_value = [
            _cheque(1, [_inv(1, "101", "2026-03-01")], clearance="2026-03-22"),
            _cheque(2, [_inv(2, "104", "2026-03-20")], clearance="2026-04-03"),
        ]
        doc = build_dealer_pattern_document(1)
        self.assertIn("paid_individually", doc)
        self.assertIn("Inv #101 (21 days aging)", doc)
        self.assertIn("Inv #104 (14 days aging)", doc)
        self.assertNotIn("Bundled Invoices Average Aging", doc)

    @patch("core.dealer_patterns.repo.get_dealer")
    @patch("core.dealer_patterns.repo.get_bank_account")
    @patch("core.dealer_patterns.repo.get_dealer_committed_payment_history")
    def test_bundled_includes_average(self, mock_history, mock_acc, mock_dealer):
        mock_dealer.return_value = {"dealer_name": "Tech World"}
        mock_acc.return_value = {"bank_name": "Commercial Bank"}
        mock_history.return_value = [
            _cheque(
                1,
                [
                    _inv(1, "201", "2026-02-01"),
                    _inv(2, "202", "2026-02-10"),
                ],
                clearance="2026-03-15",
            ),
        ]
        doc = build_dealer_pattern_document(3)
        self.assertIn("frequently_bundled", doc)
        self.assertIn("Bundled Invoices Average Aging", doc)
        self.assertIn("multi-invoice cheques", doc)

    @patch("core.dealer_patterns.repo.get_dealer")
    @patch("core.dealer_patterns.repo.get_bank_account")
    @patch("core.dealer_patterns.repo.get_dealer_committed_payment_history")
    def test_mixed_history(self, mock_history, mock_acc, mock_dealer):
        mock_dealer.return_value = {"dealer_name": "Mixed Co"}
        mock_acc.return_value = {"bank_name": "HNB"}
        mock_history.return_value = [
            _cheque(1, [_inv(1, "301"), _inv(2, "302")], clearance="2026-05-01"),
            _cheque(2, [_inv(3, "303")], clearance="2026-05-10"),
        ]
        doc = build_dealer_pattern_document(5)
        self.assertIn("mixed", doc)
        self.assertIn("Bundled Invoices Average Aging", doc)
        self.assertIn("Inv #303", doc)

    @patch("core.dealer_patterns.repo.get_dealer")
    @patch("core.dealer_patterns.repo.get_bank_account")
    @patch("core.dealer_patterns.repo.get_dealer_committed_payment_history")
    def test_split_parts_listed_individually(self, mock_history, mock_acc, mock_dealer):
        mock_dealer.return_value = {"dealer_name": "Big Bills Ltd"}
        mock_acc.return_value = {"bank_name": "Commercial Bank"}
        mock_history.return_value = [
            _cheque(
                1,
                [_inv(1, "501", total_amount=600_000, part_index=1, part_count=2)],
                clearance="2026-06-01",
            ),
            _cheque(
                2,
                [_inv(1, "501", total_amount=600_000, part_index=2, part_count=2)],
                clearance="2026-06-08",
            ),
            _cheque(
                3,
                [_inv(2, "502", total_amount=700_000, part_index=1, part_count=2)],
                clearance="2026-07-01",
            ),
            _cheque(
                4,
                [_inv(2, "502", total_amount=700_000, part_index=2, part_count=2)],
                clearance="2026-07-08",
            ),
        ]
        doc = build_dealer_pattern_document(6)
        self.assertIn("part 1/2", doc)
        self.assertIn("part 2/2", doc)
        self.assertIn("Payment Pattern:", doc)

    @patch("core.dealer_patterns.repo.get_dealer")
    @patch("core.dealer_patterns.repo.get_bank_account")
    @patch("core.dealer_patterns.repo.get_dealer_committed_payment_history")
    def test_preferred_account(self, mock_history, mock_acc, mock_dealer):
        mock_dealer.return_value = {"dealer_name": "Account Test"}
        mock_acc.return_value = {"bank_name": "Commercial Bank"}
        mock_history.return_value = [
            _cheque(1, [_inv(1, "601")], acc_id=1),
            _cheque(2, [_inv(2, "602")], acc_id=1),
            _cheque(3, [_inv(3, "603")], acc_id=2),
        ]
        doc = build_dealer_pattern_document(7)
        self.assertIn("Commercial Bank", doc)
        self.assertIn("2 out of 3", doc)


if __name__ == "__main__":
    unittest.main()
