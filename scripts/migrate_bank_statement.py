"""One-off migration: add bank_statement_mail_config / bank_statement_verifications
to an existing database. Safe to re-run.

Usage:
    python scripts/migrate_bank_statement.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db.connection import get_connection

DDL = """
CREATE TABLE IF NOT EXISTS bank_statement_mail_config (
    config_id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_bank_acc_id               INTEGER NOT NULL UNIQUE,
    business_email                 TEXT    NOT NULL,
    business_email_app_password    TEXT    NOT NULL,
    bank_email                     TEXT    NOT NULL,
    imap_host                      TEXT    NOT NULL DEFAULT 'imap.gmail.com',
    imap_port                      INTEGER NOT NULL DEFAULT 993,
    updated_at                     TEXT    DEFAULT (datetime('now')),
    FOREIGN KEY (user_bank_acc_id) REFERENCES user_bank_account(user_bank_acc_id)
);

CREATE TABLE IF NOT EXISTS bank_statement_verifications (
    verification_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_bank_acc_id       INTEGER NOT NULL,
    statement_email_date   TEXT,
    statement_subject      TEXT,
    message_id             TEXT,
    statement_balance      REAL,
    system_balance         REAL,
    balance_matches        INTEGER NOT NULL DEFAULT 0,
    cashed_cheques_json    TEXT,
    pending_cheques_json   TEXT,
    discrepancies_json     TEXT,
    is_test                INTEGER NOT NULL DEFAULT 0,
    created_at             TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_bank_acc_id) REFERENCES user_bank_account(user_bank_acc_id)
);

CREATE INDEX IF NOT EXISTS idx_bank_statement_verifications_account
    ON bank_statement_verifications(user_bank_acc_id, created_at);
"""


def migrate():
    conn = get_connection()
    try:
        conn.executescript(DDL)
        conn.commit()
        print("bank_statement_mail_config / bank_statement_verifications are ready.")
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
