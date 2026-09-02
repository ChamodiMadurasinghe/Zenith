"""Tests for strategist date optimizer and interbank account options."""

import unittest
from datetime import date
from unittest.mock import patch

from core.strategist_dates import interbank_account_options, suggest_float_cheque_date


class TestStrategistDates(unittest.TestCase):
    def test_interbank_option_detection(self):
        with patch("core.strategist_dates.repo.get_dealer_preferred_bank", return_value={"bank_name": "Commercial Bank"}):
            with patch(
                "core.strategist_dates.repo.get_bank_accounts",
                return_value=[
                    {"user_bank_acc_id": 1, "bank_name": "Commercial Bank", "available_balance": 100, "overdraft_limit": 0},
                    {"user_bank_acc_id": 2, "bank_name": "Sampath Bank", "available_balance": 200, "overdraft_limit": 0},
                ],
            ):
                opts = interbank_account_options(5)
        by_id = {o["account_id"]: o for o in opts}
        self.assertEqual(by_id[1]["clearing_type"], "INTRABANK")
        self.assertEqual(by_id[2]["clearing_type"], "INTERBANK")

    def test_suggest_float_picks_date_in_window(self):
        invoice = {
            "invoiced_date": "2026-09-01",
            "credit_period_days": 30,
        }
        dealer = {"casual_days": 0, "impossible_days": ""}
        holidays = set()
        with patch("core.strategist_dates.repo.get_holidays", return_value=holidays):
            result = suggest_float_cheque_date(
                invoice,
                dealer,
                holidays,
                merchant_bank_name="Sampath Bank",
                dealer_bank_name="Commercial Bank",
                prefer_interbank=True,
            )
        self.assertIn("proposed_date", result)
        self.assertTrue(result.get("is_interbank"))


class TestEnrichBundlePayingAccount(unittest.TestCase):
    def test_uses_bundle_paying_account_for_interbank(self):
        from core.bundling import enrich_bundle_liquidity

        bundle = {"cheque_date": "2026-09-15", "paying_account_id": 2, "clearing_type": "INTERBANK"}
        with patch("core.bundling.repo.get_dealer_preferred_bank", return_value={"bank_name": "Commercial Bank"}):
            with patch(
                "core.bundling.repo.get_bank_account",
                return_value={"bank_name": "Sampath Bank", "user_bank_acc_id": 2},
            ):
                with patch("core.bundling.repo.get_holidays", return_value=set()):
                    out = enrich_bundle_liquidity(bundle, dealer_id=1, holidays=set())
        self.assertTrue(out.get("is_interbank"))


if __name__ == "__main__":
    unittest.main()
