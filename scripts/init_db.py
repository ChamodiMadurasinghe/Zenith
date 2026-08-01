"""Drop and recreate the SQLite database from schema + seed."""

import os
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

DB_PATH = ROOT / os.getenv("DATABASE_PATH", "database/invoice_cheque.db")
SCHEMA = ROOT / "database" / "schema.sql"
SEED = ROOT / "database" / "seed.sql"


MIGRATIONS = [
    "ALTER TABLE dealers ADD COLUMN preferred_dealer_bank_acc_id INTEGER REFERENCES dealers_bank_account(dealer_bank_acc_id)",
    """CREATE TABLE IF NOT EXISTS deposit_timetable (
        timetable_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_bank_acc_id INTEGER NOT NULL,
        cheque_id INTEGER,
        dealer_id INTEGER,
        stated_date TEXT NOT NULL,
        true_settlement_date TEXT,
        target_funding_date TEXT,
        total_amount REAL NOT NULL,
        days_gained INTEGER DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'pending',
        FOREIGN KEY (user_bank_acc_id) REFERENCES user_bank_account(user_bank_acc_id),
        FOREIGN KEY (cheque_id) REFERENCES cheque(cheque_id),
        FOREIGN KEY (dealer_id) REFERENCES dealers(dealer_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_deposit_timetable_account ON deposit_timetable(user_bank_acc_id)",
    "CREATE INDEX IF NOT EXISTS idx_deposit_timetable_status ON deposit_timetable(status)",
    "CREATE INDEX IF NOT EXISTS idx_deposit_timetable_stated ON deposit_timetable(stated_date)",
    "ALTER TABLE dealers ADD COLUMN default_user_bank_acc_id INTEGER REFERENCES user_bank_account(user_bank_acc_id)",
    """CREATE TABLE IF NOT EXISTS bundle_drafts (
        dealer_id INTEGER PRIMARY KEY,
        ceiling_lkr REAL NOT NULL,
        bundles_json TEXT NOT NULL,
        validation_issues_json TEXT,
        allow_exceed_ceiling INTEGER NOT NULL DEFAULT 0,
        chat_history_json TEXT,
        updated_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (dealer_id) REFERENCES dealers(dealer_id)
    )""",
    "ALTER TABLE invoices ADD COLUMN pending_dealer_json TEXT",
    """CREATE TABLE IF NOT EXISTS whatsapp_sessions (
        phone TEXT PRIMARY KEY,
        state TEXT NOT NULL,
        context_json TEXT,
        updated_at TEXT DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_whatsapp_sessions_updated ON whatsapp_sessions(updated_at)",
    """CREATE TABLE IF NOT EXISTS alert_log (
        alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel TEXT NOT NULL,
        recipient TEXT NOT NULL,
        message TEXT NOT NULL,
        sent_at TEXT DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_alert_log_sent_at ON alert_log(sent_at)",
]


def _sync_cbsl_holidays():
    """Best-effort CBSL holiday sync after fresh DB create."""
    try:
        from scripts.sync_cbsl_holidays import sync_years

        print("Syncing CBSL bank holidays (2025-2027)...")
        sync_years([2025, 2026, 2027], dry_run=False)
    except Exception as e:
        print(f"Warning: CBSL holiday sync failed ({e}). Run: python scripts/sync_cbsl_holidays.py")


def migrate_db(conn: sqlite3.Connection):
    """Apply incremental migrations to an existing database."""
    for sql in MIGRATIONS:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass
    rows = conn.execute(
        "SELECT dealer_id, dealer_bank_acc_id FROM dealers_bank_account ORDER BY dealer_id"
    ).fetchall()
    for dealer_id, bank_acc_id in rows:
        conn.execute(
            """UPDATE dealers SET preferred_dealer_bank_acc_id = ?
               WHERE dealer_id = ? AND preferred_dealer_bank_acc_id IS NULL""",
            (bank_acc_id, dealer_id),
        )
    pending = conn.execute(
        "SELECT dealer_id FROM dealers WHERE dealer_name = ?",
        ("Pending Supplier",),
    ).fetchone()
    if not pending:
        conn.execute(
            """INSERT INTO dealers (dealer_name, dealer_email, dealer_telno, dealer_address,
               dealer_strictness, casual_days, impossible_days)
               VALUES ('Pending Supplier', NULL, NULL, NULL, 'Medium', 3, 'Sunday')"""
        )
    conn.commit()


def init_db(force_recreate: bool = True):
    if force_recreate and DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    try:
        if force_recreate or not DB_PATH.exists():
            conn.executescript(SCHEMA.read_text(encoding="utf-8"))
            conn.executescript(SEED.read_text(encoding="utf-8"))
            password = os.getenv("APP_PASSWORD", "change-me-on-first-setup")
            conn.execute(
                "UPDATE user SET password_hash = ? WHERE user_id = 1",
                (generate_password_hash(password),),
            )
            conn.commit()
            print(f"Database created at {DB_PATH}")
            print("Login password set from APP_PASSWORD in .env")
            from scripts.seed_sample_invoices import seed_invoices

            added = seed_invoices(per_dealer=10)
            print(f"Sample invoices seeded: {added} added")
            _sync_cbsl_holidays()
        else:
            migrate_db(conn)
            print(f"Database migrated at {DB_PATH}")
    finally:
        conn.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Initialize or migrate Zenith database")
    parser.add_argument("--migrate", action="store_true", help="Migrate existing DB without dropping")
    args = parser.parse_args()
    init_db(force_recreate=not args.migrate)
