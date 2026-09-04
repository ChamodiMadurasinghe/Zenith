import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from db import repositories as repo


class TestDeleteInvoiceAndDealer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.conn = sqlite3.connect(self.tmp.name)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(
            """
            CREATE TABLE dealers (
                dealer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                dealer_name TEXT NOT NULL,
                preferred_dealer_bank_acc_id INTEGER
            );
            CREATE TABLE dealers_bank_account (
                dealer_bank_acc_id INTEGER PRIMARY KEY AUTOINCREMENT,
                dealer_id INTEGER NOT NULL,
                account_name TEXT NOT NULL,
                bank_name TEXT NOT NULL,
                FOREIGN KEY (dealer_id) REFERENCES dealers(dealer_id)
            );
            CREATE TABLE invoices (
                invoices_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                dealer_id INTEGER NOT NULL,
                cheque_id INTEGER,
                invoice_no TEXT NOT NULL,
                invoiced_date TEXT NOT NULL DEFAULT '2026-01-01',
                credit_period_days INTEGER NOT NULL DEFAULT 30,
                total_amount REAL NOT NULL DEFAULT 0,
                is_invoice_verified INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (dealer_id) REFERENCES dealers(dealer_id)
            );
            CREATE TABLE item (
                item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoices_id INTEGER NOT NULL,
                item_code TEXT NOT NULL DEFAULT 'X',
                item_name TEXT NOT NULL DEFAULT 'Item',
                item_qty INTEGER NOT NULL DEFAULT 1,
                item_price REAL NOT NULL DEFAULT 0,
                FOREIGN KEY (invoices_id) REFERENCES invoices(invoices_id)
            );
            CREATE TABLE cheque_invoice_allocation (
                allocation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                cheque_id INTEGER NOT NULL,
                invoices_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                part_index INTEGER NOT NULL DEFAULT 1,
                part_count INTEGER NOT NULL DEFAULT 1
            );
            INSERT INTO dealers (dealer_name) VALUES ('Acme'), ('Pending Supplier');
            INSERT INTO invoices (user_id, dealer_id, cheque_id, invoice_no, total_amount)
                VALUES (1, 1, NULL, 'INV-1', 100);
            INSERT INTO item (invoices_id) VALUES (1);
            INSERT INTO invoices (user_id, dealer_id, cheque_id, invoice_no, total_amount)
                VALUES (1, 1, 9, 'INV-PAID', 200);
            """
        )
        self.conn.commit()

        def query(sql, params=()):
            cur = self.conn.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]

        def query_one(sql, params=()):
            rows = query(sql, params)
            return rows[0] if rows else None

        def execute(sql, params=()):
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur.lastrowid

        class Tx:
            def __enter__(inner):
                return self.conn

            def __exit__(inner, exc_type, exc, tb):
                if exc_type:
                    self.conn.rollback()
                    return False
                self.conn.commit()
                return False

        self.patches = [
            patch("db.repositories.query", side_effect=query),
            patch("db.repositories.query_one", side_effect=query_one),
            patch("db.repositories.execute", side_effect=execute),
            patch("db.repositories.transaction", side_effect=Tx),
            patch("db.repositories.Config.USER_ID", 1),
            patch("db.repositories.ensure_invoice_delivery_date_column", lambda: None),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.conn.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_delete_unassigned_invoice(self):
        self.assertIsNone(repo.delete_invoice(1))
        self.assertIsNone(repo.get_invoice(1))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM item").fetchone()[0], 0)

    def test_block_invoice_on_cheque(self):
        self.assertEqual(repo.delete_invoice(2), "flash_cannot_remove_invoice_on_cheque")
        self.assertIsNotNone(repo.get_invoice(2))

    def test_block_dealer_with_cheques(self):
        self.assertEqual(repo.delete_dealer(1), "flash_cannot_remove_supplier_with_cheques")

    def test_delete_dealer_without_cheques(self):
        self.conn.execute("DELETE FROM invoices WHERE invoices_id = 2")
        self.conn.commit()
        self.assertIsNone(repo.delete_dealer(1))
        self.assertIsNone(repo.get_dealer(1))

    def test_block_pending_supplier(self):
        self.assertEqual(repo.delete_dealer(2), "flash_cannot_remove_pending_supplier")


if __name__ == "__main__":
    unittest.main()
