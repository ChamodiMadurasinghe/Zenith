import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from db import repositories as repo


class TestValidateBankCeiling(unittest.TestCase):
    def test_missing_ceiling_is_valid(self):
        err = repo.validate_bank_account_input(
            {"account_name": "Main", "bank_name": "Commercial Bank", "overdraft_limit": 0}
        )
        self.assertIsNone(err)

    def test_zero_ceiling_invalid(self):
        err = repo.validate_bank_account_input(
            {
                "account_name": "Main",
                "bank_name": "Commercial Bank",
                "ceiling_lkr": 0,
            }
        )
        self.assertEqual(err, "flash_ceiling_invalid")

    def test_negative_ceiling_invalid(self):
        err = repo.validate_bank_account_input(
            {
                "account_name": "Main",
                "bank_name": "Commercial Bank",
                "ceiling_lkr": -1,
            }
        )
        self.assertEqual(err, "flash_ceiling_invalid")

    def test_non_numeric_ceiling_invalid(self):
        err = repo.validate_bank_account_input(
            {
                "account_name": "Main",
                "bank_name": "Commercial Bank",
                "ceiling_lkr": "abc",
            }
        )
        self.assertEqual(err, "flash_ceiling_invalid")

    def test_positive_ceiling_ok(self):
        err = repo.validate_bank_account_input(
            {
                "account_name": "Main",
                "bank_name": "Commercial Bank",
                "ceiling_lkr": 200000,
            }
        )
        self.assertIsNone(err)


class TestEffectiveAndCommitCeiling(unittest.TestCase):
    def test_effective_cap_is_min_of_session_and_account(self):
        with patch.object(repo, "get_bank_account", return_value={"ceiling_lkr": 200000}):
            self.assertEqual(repo.effective_cheque_ceiling(500000, 2), 200000)
            self.assertEqual(repo.effective_cheque_ceiling(100000, 2), 100000)

    def test_commit_rejects_amount_over_account_ceiling(self):
        with patch.object(repo, "get_bank_account", return_value={"ceiling_lkr": 200000}):
            over = repo.amounts_exceeding_account_ceiling([199999, 200000, 300000], 2)
        self.assertEqual(over, [300000.0])

    def test_commit_allows_amount_at_ceiling(self):
        with patch.object(repo, "get_bank_account", return_value={"ceiling_lkr": 200000}):
            over = repo.amounts_exceeding_account_ceiling([200000], 2)
        self.assertEqual(over, [])

    def test_missing_account_uses_default_ceiling(self):
        with patch.object(repo, "get_bank_account", return_value=None):
            self.assertEqual(repo.account_ceiling_lkr(99), repo.DEFAULT_CHEQUE_CEILING_LKR)
            self.assertEqual(
                repo.amounts_exceeding_account_ceiling([500000], 99),
                [],
            )
            self.assertEqual(
                repo.amounts_exceeding_account_ceiling([500001], 99),
                [500001.0],
            )


class TestBankAccountCeilingPersistence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.path = Path(self.tmp.name)
        conn = sqlite3.connect(self.path)
        conn.executescript(
            """
            CREATE TABLE user_bank_account (
                user_bank_acc_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                account_name TEXT NOT NULL,
                nickname TEXT,
                available_balance REAL NOT NULL DEFAULT 0,
                overdraft_limit REAL NOT NULL DEFAULT 0,
                ceiling_lkr REAL NOT NULL DEFAULT 500000,
                branch_name TEXT,
                bank_name TEXT NOT NULL
            );
            """
        )
        conn.commit()
        conn.close()
        self.db_patcher = patch("db.connection.Config.DATABASE_PATH", self.path)
        self.db_patcher.start()

    def tearDown(self):
        self.db_patcher.stop()
        try:
            self.path.unlink(missing_ok=True)
        except PermissionError:
            pass

    def test_create_and_update_store_ceiling(self):
        acc_id = repo.create_bank_account(
            {
                "account_name": "Yohan Hardware",
                "nickname": "Reserve",
                "available_balance": 1000,
                "overdraft_limit": 0,
                "ceiling_lkr": 250000,
                "branch_name": "Fort",
                "bank_name": "Hatton National Bank",
            }
        )
        row = repo.get_bank_account(acc_id)
        self.assertAlmostEqual(float(row["ceiling_lkr"]), 250000)

        repo.update_bank_account(
            acc_id,
            {
                "account_name": "Yohan Hardware",
                "nickname": "Reserve",
                "branch_name": "Fort",
                "bank_name": "Hatton National Bank",
                "overdraft_limit": 0,
                "ceiling_lkr": 200000,
            },
        )
        row = repo.get_bank_account(acc_id)
        self.assertAlmostEqual(float(row["ceiling_lkr"]), 200000)
        self.assertAlmostEqual(repo.account_ceiling_lkr(acc_id), 200000)


if __name__ == "__main__":
    unittest.main()
