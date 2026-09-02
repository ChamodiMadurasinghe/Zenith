import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from db.repositories import (
    CITS_CHEQUE_LENGTH_MM,
    CITS_CHEQUE_WIDTH_MM,
    get_account_cheque_setup,
    get_account_printer_calibration,
    get_printer_settings,
    save_account_cheque_setup,
    save_account_printer_calibration,
    upsert_printer_settings,
    validate_cheque_dimensions,
    validate_printer_offsets,
)


class TestChequeDimensionsRepository(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.conn = sqlite3.connect(self.tmp.name)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(
            """
            CREATE TABLE bank_cheque_templates (
                bank_code VARCHAR(20) PRIMARY KEY,
                bank_name VARCHAR(100) NOT NULL,
                cheque_width_mm REAL NOT NULL DEFAULT 177.8,
                cheque_height_mm REAL NOT NULL DEFAULT 88.9,
                date_x REAL NOT NULL,
                date_y REAL NOT NULL,
                date_letter_spacing REAL DEFAULT 3.5,
                payee_x REAL NOT NULL,
                payee_y REAL NOT NULL,
                amount_words_x REAL NOT NULL,
                amount_words_y REAL NOT NULL,
                amount_words_max_width REAL DEFAULT 110.0,
                amount_figures_x REAL NOT NULL,
                amount_figures_y REAL NOT NULL,
                crossing_x REAL DEFAULT 15.0,
                crossing_y REAL DEFAULT 75.0
            );
            CREATE TABLE shop_printer_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_bank_acc_id INTEGER,
                bank_code VARCHAR(20) NOT NULL,
                offset_x_mm REAL DEFAULT 0.0,
                offset_y_mm REAL DEFAULT 0.0,
                feed_orientation TEXT DEFAULT 'VERTICAL',
                cheque_width_mm REAL,
                cheque_height_mm REAL,
                is_active INTEGER DEFAULT 1,
                UNIQUE(user_bank_acc_id, bank_code)
            );
            INSERT INTO bank_cheque_templates
                (bank_code, bank_name, date_x, date_y, payee_x, payee_y,
                 amount_words_x, amount_words_y, amount_figures_x, amount_figures_y)
            VALUES ('COMB', 'Commercial Bank', 135, 75, 25, 56, 25, 43, 135, 43);
            """
        )
        self.conn.commit()

        def query_one(sql, params=()):
            cur = self.conn.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row else None

        def execute(sql, params=()):
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur.lastrowid

        self.query_one_patcher = patch("db.repositories.query_one", side_effect=query_one)
        self.execute_patcher = patch("db.repositories.execute", side_effect=execute)
        self.query_one_patcher.start()
        self.execute_patcher.start()

    def tearDown(self):
        self.query_one_patcher.stop()
        self.execute_patcher.stop()
        self.conn.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_validate_cheque_dimensions_ok(self):
        self.assertIsNone(validate_cheque_dimensions(177.8, 88.9))

    def test_validate_cheque_length_out_of_range(self):
        self.assertEqual(validate_cheque_dimensions(140, 88.9), "flash_cheque_length_out_of_range")

    def test_validate_cheque_width_out_of_range(self):
        self.assertEqual(validate_cheque_dimensions(177.8, 50), "flash_cheque_width_out_of_range")

    def test_save_and_load_account_dimensions(self):
        err = save_account_cheque_setup(5, "Commercial Bank of Ceylon", 180.0, 90.0)
        self.assertIsNone(err)
        settings = get_printer_settings(5, "COMB")
        self.assertEqual(settings["cheque_width_mm"], 180.0)
        self.assertEqual(settings["cheque_height_mm"], 90.0)

    def test_get_account_cheque_setup_defaults(self):
        setup = get_account_cheque_setup(None, "Commercial Bank of Ceylon")
        self.assertEqual(setup["length_mm"], CITS_CHEQUE_LENGTH_MM)
        self.assertEqual(setup["width_mm"], CITS_CHEQUE_WIDTH_MM)
        self.assertTrue(setup["use_standard_cheque_size"])

    def test_get_account_cheque_setup_custom(self):
        upsert_printer_settings(
            "COMB",
            user_bank_acc_id=7,
            cheque_width_mm=181.0,
            cheque_height_mm=91.0,
        )
        setup = get_account_cheque_setup(7, "Commercial Bank of Ceylon")
        self.assertEqual(setup["length_mm"], 181.0)
        self.assertEqual(setup["width_mm"], 91.0)
        self.assertFalse(setup["use_standard_cheque_size"])

    def test_account_override_bank_default(self):
        upsert_printer_settings("COMB", user_bank_acc_id=None, offset_x_mm=1.0)
        upsert_printer_settings("COMB", user_bank_acc_id=5, offset_x_mm=3.0)
        bank_default = get_printer_settings(None, "COMB")
        account = get_printer_settings(5, "COMB")
        self.assertEqual(bank_default["offset_x_mm"], 1.0)
        self.assertEqual(account["offset_x_mm"], 3.0)

    def test_defaults_when_no_settings(self):
        settings = get_printer_settings(99, "COMB")
        self.assertEqual(settings["feed_orientation"], "VERTICAL")
        self.assertEqual(settings["offset_x_mm"], 0.0)

    def test_validate_printer_offsets_ok(self):
        self.assertIsNone(validate_printer_offsets(2.0, -1.0))

    def test_validate_printer_offsets_out_of_range(self):
        self.assertEqual(validate_printer_offsets(25, 0), "flash_printer_offsets_out_of_range")

    def test_save_and_load_printer_calibration(self):
        err = save_account_printer_calibration(5, "COMB", 2.0, -1.5, "HORIZONTAL")
        self.assertIsNone(err)
        cal = get_account_printer_calibration(5, "Commercial Bank of Ceylon")
        self.assertEqual(cal["offset_x_mm"], 2.0)
        self.assertEqual(cal["offset_y_mm"], -1.5)
        self.assertEqual(cal["feed_orientation"], "HORIZONTAL")

    def test_save_calibration_preserves_dimensions(self):
        save_account_cheque_setup(5, "Commercial Bank of Ceylon", 180.0, 90.0, bank_code="COMB")
        save_account_printer_calibration(5, "COMB", 1.0, 0.5)
        settings = get_printer_settings(5, "COMB")
        self.assertEqual(settings["cheque_width_mm"], 180.0)
        self.assertEqual(settings["offset_x_mm"], 1.0)


if __name__ == "__main__":
    unittest.main()
