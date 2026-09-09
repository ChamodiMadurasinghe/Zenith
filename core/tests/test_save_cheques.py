import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from db import repositories as repo
from db.connection import query, query_one


_SCHEMA = """
CREATE TABLE user (
    user_id INTEGER PRIMARY KEY,
    user_name TEXT NOT NULL,
    email TEXT NOT NULL,
    password_hash TEXT NOT NULL
);
CREATE TABLE user_bank_account (
    user_bank_acc_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    account_name TEXT NOT NULL,
    bank_name TEXT NOT NULL,
    available_balance REAL NOT NULL DEFAULT 0,
    overdraft_limit REAL NOT NULL DEFAULT 0
);
CREATE TABLE dealers (
    dealer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    dealer_name TEXT NOT NULL,
    preferred_dealer_bank_acc_id INTEGER,
    default_user_bank_acc_id INTEGER
);
CREATE TABLE dealers_bank_account (
    dealer_bank_acc_id INTEGER PRIMARY KEY AUTOINCREMENT,
    dealer_id INTEGER NOT NULL,
    account_name TEXT NOT NULL,
    bank_name TEXT NOT NULL
);
CREATE TABLE cheque (
    cheque_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_bank_acc_id INTEGER NOT NULL,
    cheque_no TEXT NOT NULL,
    cheque_date TEXT NOT NULL,
    amount_in_words TEXT,
    amount_in_numerals REAL NOT NULL,
    verification_status INTEGER NOT NULL DEFAULT 0,
    predicted_clearance_date TEXT,
    cheque_print_date TEXT DEFAULT (datetime('now'))
);
CREATE TABLE invoices (
    invoices_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    dealer_id INTEGER NOT NULL,
    cheque_id INTEGER,
    invoice_no TEXT NOT NULL,
    invoiced_date TEXT NOT NULL,
    credit_period_days INTEGER NOT NULL DEFAULT 30,
    total_amount REAL NOT NULL,
    is_invoice_verified INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE cheque_invoice_allocation (
    allocation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    cheque_id INTEGER NOT NULL,
    invoices_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    part_index INTEGER NOT NULL DEFAULT 1,
    part_count INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE deposit_timetable (
    timetable_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_bank_acc_id INTEGER NOT NULL,
    cheque_id INTEGER,
    dealer_id INTEGER,
    stated_date TEXT NOT NULL,
    true_settlement_date TEXT,
    target_funding_date TEXT,
    total_amount REAL NOT NULL,
    days_gained INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending'
);
CREATE TABLE cbsl_bank_holidays (
    holiday_date TEXT PRIMARY KEY,
    description TEXT
);
"""


class TestSaveChequesThreeWay(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.path = Path(self.tmp.name)
        conn = sqlite3.connect(self.path)
        conn.executescript(_SCHEMA)
        conn.execute(
            "INSERT INTO user (user_id, user_name, email, password_hash) VALUES (1, 't', 't@t.lk', 'x')"
        )
        conn.execute(
            """INSERT INTO user_bank_account (user_bank_acc_id, user_id, account_name, bank_name)
               VALUES (1, 1, 'Main', 'Commercial Bank')"""
        )
        conn.execute("INSERT INTO dealers (dealer_id, dealer_name) VALUES (4, 'Future Tech')")
        conn.execute(
            """INSERT INTO invoices
               (invoices_id, user_id, dealer_id, invoice_no, invoiced_date, total_amount, is_invoice_verified)
               VALUES (100, 1, 4, 'INV-SPLIT-3', '2026-08-01', 600000, 1)"""
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

    def test_three_way_split_saves_allocations_and_timetable(self):
        cheques = []
        invoice_map = {}
        for i, amount in enumerate((200000.0, 200000.0, 200000.0)):
            cheques.append(
                {
                    "user_bank_acc_id": 1,
                    "cheque_no": f"QA-CH-{i + 1}",
                    "cheque_date": "2026-12-01",
                    "amount_in_words": "Two Hundred Thousand",
                    "amount_in_numerals": amount,
                    "predicted_clearance_date": "2026-12-02",
                }
            )
            invoice_map[i] = [
                {
                    "invoices_id": 100,
                    "amount": amount,
                    "part_index": i + 1,
                    "part_count": 3,
                }
            ]

        repo.save_cheques(cheques, invoice_map)

        ch_rows = query("SELECT * FROM cheque ORDER BY cheque_id")
        self.assertEqual(len(ch_rows), 3)
        self.assertTrue(all(int(c["verification_status"]) == 1 for c in ch_rows))

        alloc = query(
            "SELECT * FROM cheque_invoice_allocation WHERE invoices_id = 100 ORDER BY part_index"
        )
        self.assertEqual(len(alloc), 3)
        self.assertEqual([a["part_index"] for a in alloc], [1, 2, 3])
        self.assertTrue(all(int(a["part_count"]) == 3 for a in alloc))
        self.assertAlmostEqual(sum(float(a["amount"]) for a in alloc), 600000.0)

        inv = query_one("SELECT cheque_id, total_amount FROM invoices WHERE invoices_id = 100")
        self.assertEqual(inv["cheque_id"], ch_rows[0]["cheque_id"])
        self.assertAlmostEqual(float(inv["total_amount"]), 600000.0)

        tt = query("SELECT * FROM deposit_timetable ORDER BY cheque_id")
        self.assertEqual(len(tt), 3)
        self.assertTrue(all(t["status"] == "pending" for t in tt))
        self.assertAlmostEqual(sum(float(t["total_amount"]) for t in tt), 600000.0)


if __name__ == "__main__":
    unittest.main()
