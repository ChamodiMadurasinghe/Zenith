import unittest
from unittest.mock import patch

from agents.strategist import proposed_cheques_to_bundles, _bundles_to_strategy


class TestStrategistMapping(unittest.TestCase):
    def test_bundles_to_strategy_shape(self):
        bundles = [
            {
                "group": 1,
                "total_lkr": 100000.0,
                "cheque_date": "2026-09-15",
                "is_interbank": True,
                "invoices": [],
            }
        ]
        with patch("agents.strategist.repo.get_dealer_preferred_bank", return_value={"bank_name": "Commercial"}):
            with patch("agents.strategist.repo.paying_account_id_for_dealer", return_value=1):
                result = _bundles_to_strategy(bundles, dealer_id=2, ceiling_lkr=250000)
        self.assertIn("strategy_summary", result)
        self.assertEqual(len(result["proposed_cheques"]), 1)
        self.assertEqual(result["proposed_cheques"][0]["clearing_type"], "INTERBANK")

    @patch("agents.strategist._invoice_rows")
    @patch("agents.strategist.recalculate_all_bundles")
    def test_proposed_cheques_to_bundles(self, mock_recalc, mock_rows):
        mock_rows.return_value = [
            {
                "invoices_id": 10,
                "invoice_no": "INV-A",
                "total_amount": 200000.0,
                "invoiced_date": "2026-08-01",
                "credit_period_days": 30,
            }
        ]
        mock_recalc.side_effect = lambda bundles, dealer_id: bundles
        proposed = [
            {
                "cheque_index": 1,
                "selected_shop_account_id": 1,
                "payee_bank": "Commercial",
                "amount": 100000.0,
                "proposed_date": "2026-09-10",
                "clearing_type": "INTERBANK",
                "strategic_reasoning": "Split for float.",
            },
            {
                "cheque_index": 2,
                "selected_shop_account_id": 1,
                "payee_bank": "Commercial",
                "amount": 100000.0,
                "proposed_date": "2026-09-20",
                "clearing_type": "INTERBANK",
                "strategic_reasoning": "Second half.",
            },
        ]
        bundles = proposed_cheques_to_bundles(2, proposed, [10])
        self.assertEqual(len(bundles), 2)
        self.assertEqual(bundles[0]["group"], 1)
        self.assertEqual(bundles[0]["clearing_type"], "INTERBANK")


if __name__ == "__main__":
    unittest.main()
