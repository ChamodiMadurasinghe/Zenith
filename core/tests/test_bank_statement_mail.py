import unittest
from unittest.mock import patch

from core.bank_statement_mail import (
    is_monthly_statement_email,
    parse_statement_text,
    sample_statement_text,
    _compare,
)


class TestIsMonthlyStatementEmail(unittest.TestCase):
    BANK_EMAIL = "statements@samplebank.lk"

    def test_matches_monthly_statement_from_bank(self):
        self.assertTrue(
            is_monthly_statement_email(
                "Your Monthly Statement of Account", "Sample Bank <statements@samplebank.lk>", self.BANK_EMAIL
            )
        )

    def test_ignores_transaction_alert_from_same_bank(self):
        self.assertFalse(
            is_monthly_statement_email(
                "Cheque Cleared Notification", "Sample Bank <statements@samplebank.lk>", self.BANK_EMAIL
            )
        )

    def test_ignores_credit_alert(self):
        self.assertFalse(
            is_monthly_statement_email(
                "Credit Alert", "Sample Bank <statements@samplebank.lk>", self.BANK_EMAIL
            )
        )

    def test_ignores_statement_looking_email_from_wrong_sender(self):
        self.assertFalse(
            is_monthly_statement_email(
                "Your Monthly Statement of Account", "Not The Bank <someone@else.com>", self.BANK_EMAIL
            )
        )

    def test_ignores_unrelated_subject(self):
        self.assertFalse(
            is_monthly_statement_email(
                "Your invoice is ready", "Sample Bank <statements@samplebank.lk>", self.BANK_EMAIL
            )
        )


class TestParseStatementText(unittest.TestCase):
    def test_parses_sample_statement(self):
        result = parse_statement_text(sample_statement_text())
        cheque_nos = {c["cheque_no"] for c in result["cashed_cheques"]}
        self.assertEqual(cheque_nos, {"000123", "000456", "000789"})
        self.assertEqual(result["closing_balance"], 215340.50)

    def test_no_matches_returns_empty(self):
        result = parse_statement_text("Nothing relevant here.")
        self.assertEqual(result["cashed_cheques"], [])
        self.assertIsNone(result["closing_balance"])

    def test_deduplicates_repeated_cheque_number(self):
        text = (
            "Cheque No 000111 cleared Rs. 1,000.00\n"
            "Cheque No 000111 cleared Rs. 1,000.00\n"
        )
        result = parse_statement_text(text)
        self.assertEqual(len(result["cashed_cheques"]), 1)


class TestCompare(unittest.TestCase):
    @patch("core.bank_statement_mail._system_balance", return_value=215340.50)
    @patch(
        "core.bank_statement_mail._system_pending_cheques",
        return_value=[
            {"cheque_id": 1, "cheque_no": "000123", "total_amount": 45000.0, "stated_date": "2026-08-01"},
            {"cheque_id": 2, "cheque_no": "000999", "total_amount": 9000.0, "stated_date": "2026-08-10"},
        ],
    )
    def test_matched_and_unmatched_and_balance_ok(self, _mock_pending, _mock_balance):
        parsed = {
            "cashed_cheques": [{"cheque_no": "000123", "amount": 45000.0}],
            "closing_balance": 215340.50,
        }
        result = _compare(account_id=1, parsed=parsed)
        self.assertEqual(len(result["matched_cashed"]), 1)
        self.assertEqual(result["unmatched_cashed"], [])
        self.assertEqual(len(result["still_pending"]), 1)
        self.assertEqual(result["still_pending"][0]["cheque_no"], "000999")
        self.assertTrue(result["balance_matches"])
        self.assertEqual(result["discrepancies"], [])

    @patch("core.bank_statement_mail._system_balance", return_value=200000.0)
    @patch("core.bank_statement_mail._system_pending_cheques", return_value=[])
    def test_unmatched_cheque_and_balance_mismatch_flagged(self, _mock_pending, _mock_balance):
        parsed = {
            "cashed_cheques": [{"cheque_no": "000555", "amount": 5000.0}],
            "closing_balance": 195000.0,
        }
        result = _compare(account_id=1, parsed=parsed)
        self.assertEqual(len(result["unmatched_cashed"]), 1)
        self.assertFalse(result["balance_matches"])
        self.assertEqual(len(result["discrepancies"]), 2)  # balance + unmatched cheque


if __name__ == "__main__":
    unittest.main()
