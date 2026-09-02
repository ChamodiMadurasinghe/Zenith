"""Add demo extras to an existing DB (safe to re-run). Does not wipe data."""

import os
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

DB_PATH = ROOT / os.getenv("DATABASE_PATH", "database/invoice_cheque.db")


def seed_whatsapp_inbox():
    conn = sqlite3.connect(DB_PATH)
    try:
        count = conn.execute("SELECT COUNT(*) FROM whatsapp_inbox").fetchone()[0]
        if count >= 2:
            print(f"  WhatsApp inbox: already has {count} item(s), skipping")
            return 0
        samples = [
            ("+94771234567", "storage/invoices/demo_whatsapp_a.jpg"),
            ("+94777654321", "storage/invoices/demo_whatsapp_b.jpg"),
        ]
        added = 0
        for phone, path in samples:
            exists = conn.execute(
                "SELECT 1 FROM whatsapp_inbox WHERE location_path = ?", (path,)
            ).fetchone()
            if exists:
                continue
            conn.execute(
                """INSERT INTO whatsapp_inbox (user_id, sender_phone, location_path, status)
                   VALUES (1, ?, ?, 'pending')""",
                (phone, path),
            )
            added += 1
        conn.commit()
        print(f"  WhatsApp inbox: added {added} pending photo(s)")
        return added
    finally:
        conn.close()


def main():
    print(f"Seeding demo extras into {DB_PATH} ...")
    seed_whatsapp_inbox()
    print("Done.")


if __name__ == "__main__":
    main()
