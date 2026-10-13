import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class TestProductionInit(unittest.TestCase):
    def test_production_seed_has_no_demo_data(self):
        from scripts.init_db import init_db, migrate_existing_db

        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "shop.db"
            env = {
                "DATABASE_PATH": str(db),
                "ZENITH_DESKTOP": "false",
                "ZENITH_PRODUCTION_INIT": "true",
                "APP_PASSWORD": "test-pass-123",
            }
            with patch.dict(os.environ, env, clear=False):
                with patch("scripts.init_db._sync_cbsl_holidays"):
                    init_db(force_recreate=True, production=True)
                    migrate_existing_db()
            conn = sqlite3.connect(db)
            try:
                dealers = [row[0] for row in conn.execute("SELECT dealer_name FROM dealers")]
                invoices = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
                status = conn.execute(
                    "SELECT setting_value FROM app_settings WHERE setting_key = 'onboarding_status'"
                ).fetchone()[0]
            finally:
                conn.close()
        self.assertEqual(dealers, ["Pending Supplier"])
        self.assertEqual(invoices, 0)
        self.assertEqual(status, "pending")
