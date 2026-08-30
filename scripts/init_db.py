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
    """CREATE TABLE IF NOT EXISTS whatsapp_inbox (
        inbox_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        sender_phone TEXT,
        location_path TEXT NOT NULL,
        received_at TEXT DEFAULT (datetime('now')),
        status TEXT NOT NULL DEFAULT 'pending',
        invoice_id INTEGER,
        FOREIGN KEY (user_id) REFERENCES user(user_id),
        FOREIGN KEY (invoice_id) REFERENCES invoices(invoices_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_whatsapp_inbox_status ON whatsapp_inbox(status)",
    "CREATE INDEX IF NOT EXISTS idx_whatsapp_inbox_user ON whatsapp_inbox(user_id)",
    """CREATE TABLE IF NOT EXISTS alert_log (
        alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel TEXT NOT NULL,
        recipient TEXT NOT NULL,
        message TEXT NOT NULL,
        sent_at TEXT DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_alert_log_sent_at ON alert_log(sent_at)",
    """CREATE TABLE IF NOT EXISTS app_settings (
        setting_key TEXT PRIMARY KEY,
        setting_value TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS bank_deposits (
        deposit_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_bank_acc_id INTEGER NOT NULL,
        deposit_date TEXT NOT NULL,
        amount REAL NOT NULL,
        note TEXT,
        FOREIGN KEY (user_bank_acc_id) REFERENCES user_bank_account(user_bank_acc_id)
    )""",
    """CREATE TABLE IF NOT EXISTS planned_deposits (
        planned_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_bank_acc_id INTEGER NOT NULL,
        planned_date TEXT NOT NULL,
        amount REAL NOT NULL,
        reason TEXT,
        FOREIGN KEY (user_bank_acc_id) REFERENCES user_bank_account(user_bank_acc_id)
    )""",
    """CREATE TABLE IF NOT EXISTS analyst_reports (
        report_id INTEGER PRIMARY KEY AUTOINCREMENT,
        dealer_id INTEGER,
        report_md TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (dealer_id) REFERENCES dealers(dealer_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_bank_deposits_date ON bank_deposits(deposit_date)",
    "CREATE INDEX IF NOT EXISTS idx_planned_deposits_date ON planned_deposits(planned_date)",
    # Unique invoice_no per dealer+user (fails quietly if duplicates already exist)
    """CREATE UNIQUE INDEX IF NOT EXISTS idx_invoices_user_dealer_invoice_no
       ON invoices(user_id, dealer_id, invoice_no)""",
    """CREATE TABLE IF NOT EXISTS cheque_invoice_allocation (
        allocation_id INTEGER PRIMARY KEY AUTOINCREMENT,
        cheque_id INTEGER NOT NULL,
        invoices_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        part_index INTEGER NOT NULL DEFAULT 1,
        part_count INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY (cheque_id) REFERENCES cheque(cheque_id),
        FOREIGN KEY (invoices_id) REFERENCES invoices(invoices_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_cheque_alloc_cheque ON cheque_invoice_allocation(cheque_id)",
    "CREATE INDEX IF NOT EXISTS idx_cheque_alloc_invoice ON cheque_invoice_allocation(invoices_id)",
    "ALTER TABLE invoices ADD COLUMN delivery_date TEXT",
    "ALTER TABLE user_bank_account ADD COLUMN overdraft_limit REAL NOT NULL DEFAULT 0",
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
    # Ensure default bank setting exists for cash-flow / bundling
    conn.execute(
        """INSERT OR IGNORE INTO app_settings (setting_key, setting_value)
           VALUES ('default_bank_acc_id', '1')"""
    )
    # If legacy `password` column DB was half-migrated, sync hash from APP_PASSWORD
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(user)").fetchall()}
        if "password_hash" not in cols and "password" in cols:
            conn.execute("ALTER TABLE user ADD COLUMN password_hash TEXT")
        password = os.getenv("APP_PASSWORD", "change-me-on-first-setup")
        conn.execute(
            "UPDATE user SET password_hash = ? WHERE user_id = 1",
            (generate_password_hash(password),),
        )
    except sqlite3.OperationalError:
        pass
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

    # Ensure seed/committed cheques have allocation + cash-flow timetable rows
    try:
        from db import repositories as repo
        from db.connection import query, execute

        missing = query(
            """SELECT i.invoices_id, i.cheque_id, i.total_amount
               FROM invoices i
               WHERE i.cheque_id IS NOT NULL
                 AND NOT EXISTS (
                   SELECT 1 FROM cheque_invoice_allocation a
                   WHERE a.cheque_id = i.cheque_id AND a.invoices_id = i.invoices_id
                 )"""
        )
        for row in missing:
            execute(
                """INSERT INTO cheque_invoice_allocation
                   (cheque_id, invoices_id, amount, part_index, part_count)
                   VALUES (?, ?, ?, 1, 1)""",
                (row["cheque_id"], row["invoices_id"], row["total_amount"]),
            )
        for row in query("SELECT cheque_id FROM cheque"):
            inv = query(
                "SELECT dealer_id FROM invoices WHERE cheque_id = ? LIMIT 1",
                (row["cheque_id"],),
            )
            repo.sync_timetable_from_cheque(
                row["cheque_id"], inv[0]["dealer_id"] if inv else None
            )
        print("Cheque allocations + deposit timetable synced")
    except Exception as exc:
        print(f"Warning: could not sync cheque timetable ({exc})")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Initialize or migrate Zenith database")
    parser.add_argument("--migrate", action="store_true", help="Migrate existing DB without dropping")
    args = parser.parse_args()
    init_db(force_recreate=not args.migrate)
