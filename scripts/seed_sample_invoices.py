"""Insert sample verified invoices (no cheques) for each dealer.

Dates: current calendar week (Mon–Sun).
Credit period: random 30–60 days per invoice.
"""

import os
import random
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

_raw_db = os.getenv("DATABASE_PATH", "database/invoice_cheque.db").strip()
_db = Path(_raw_db)
DB_PATH = _db if _db.is_absolute() else ROOT / _db

DEALER_PREFIX = {
    1: "ABD",
    2: "XS",
    3: "TW",
    4: "FT",
    5: "SS",
    6: "IPC",
}

PRODUCTS = [
    ("MOUSE-LOGI-001", "Wireless Mouse", 2500, 4500),
    ("KBD-MECH-002", "Mechanical Keyboard", 5500, 12000),
    ("MON-DELL-003", "24in Monitor", 28000, 55000),
    ("SSD-SAM-004", "1TB SSD", 12000, 22000),
    ("RAM-KIN-005", "16GB RAM Kit", 6500, 14000),
    ("PSU-COR-006", "750W PSU", 15000, 28000),
    ("GPU-RTX-007", "Graphics Card", 85000, 195000),
    ("CPU-INT-008", "Processor", 42000, 98000),
    ("CASE-NZXT-009", "PC Case", 9000, 18000),
    ("COOL-CM-010", "CPU Cooler", 4500, 11000),
    ("HDD-WD-011", "2TB HDD", 8000, 15000),
    ("WEBCAM-012", "HD Webcam", 3500, 7500),
]


def week_dates(anchor: date | None = None) -> list[date]:
    anchor = anchor or date.today()
    monday = anchor - timedelta(days=anchor.weekday())
    return [monday + timedelta(days=i) for i in range(7)]


def seed_invoices(per_dealer: int = 10, rng: random.Random | None = None):
    rng = rng or random.Random(42)
    week = week_dates()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        dealers = conn.execute("SELECT dealer_id, dealer_name FROM dealers ORDER BY dealer_id").fetchall()
        if not dealers:
            print("No dealers found.")
            return 0

        max_inv = conn.execute("SELECT COALESCE(MAX(invoices_id), 0) FROM invoices").fetchone()[0]
        inserted = 0

        for dealer in dealers:
            dealer_id = dealer["dealer_id"]
            prefix = DEALER_PREFIX.get(dealer_id, "INV")
            existing = conn.execute(
                """SELECT COUNT(*) FROM invoices
                   WHERE dealer_id = ? AND cheque_id IS NULL AND is_invoice_verified = 1""",
                (dealer_id,),
            ).fetchone()[0]
            need = max(0, per_dealer - existing)
            if need == 0:
                print(f"  {dealer['dealer_name']}: already has {existing} ready invoice(s), skipping")
                continue

            for n in range(1, need + 1):
                max_inv += 1
                inv_date = rng.choice(week)
                credit_days = rng.randint(30, 60)
                seq = existing + n
                invoice_no = f"INV-{prefix}-2026-{seq:03d}"

                dup = conn.execute(
                    "SELECT 1 FROM invoices WHERE invoice_no = ?", (invoice_no,)
                ).fetchone()
                if dup:
                    invoice_no = f"INV-{prefix}-2026-W{inv_date.isocalendar()[1]:02d}-{seq:03d}"

                num_items = rng.randint(1, 3)
                chosen = rng.sample(PRODUCTS, num_items)
                items = []
                total = 0.0
                for code, name, lo, hi in chosen:
                    qty = rng.randint(1, 8)
                    price = round(rng.uniform(lo, hi), 2)
                    discount = round(rng.choice([0, 0, 0, 500, 1000, 2500]), 2)
                    line = max(qty * price - discount, 0)
                    total += line
                    items.append((code, name, qty, price, discount))

                total = round(total, 2)
                cursor = conn.execute(
                    """INSERT INTO invoices
                       (user_id, dealer_id, cheque_id, invoice_no, invoiced_date,
                        credit_period_days, total_amount, location_path, is_invoice_verified)
                       VALUES (1, ?, NULL, ?, ?, ?, ?, ?, 1)""",
                    (
                        dealer_id,
                        invoice_no,
                        inv_date.isoformat(),
                        credit_days,
                        total,
                        f"storage/invoices/sample_{invoice_no.lower()}.jpg",
                    ),
                )
                invoice_id = cursor.lastrowid
                for code, name, qty, price, discount in items:
                    conn.execute(
                        """INSERT INTO item
                           (invoices_id, item_code, item_name, item_qty, item_price, item_discount)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (invoice_id, code, name, qty, price, discount),
                    )
                inserted += 1

            print(f"  {dealer['dealer_name']}: added {need} invoice(s)")

        conn.commit()
        return inserted
    finally:
        conn.close()


if __name__ == "__main__":
    week = week_dates()
    print(f"Seeding sample invoices for week {week[0]} to {week[-1]} ...")
    count = seed_invoices(per_dealer=10)
    print(f"Done. Inserted {count} invoice(s) into {DB_PATH}")
