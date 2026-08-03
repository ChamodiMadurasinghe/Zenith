"""Smoke-test cheque save + backfill deposit_timetable for seed cheques."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from db import repositories as repo
from db.connection import query, transaction


def main():
    inv_rows = query(
        """SELECT invoices_id, total_amount, dealer_id FROM invoices
           WHERE is_invoice_verified = 1 AND cheque_id IS NULL LIMIT 1"""
    )
    if not inv_rows:
        print("No free verified invoice for smoke test")
        return
    inv = inv_rows[0]
    print("test invoice:", dict(inv))

    cheques = [
        {
            "user_bank_acc_id": 1,
            "cheque_no": "TEST-SAVE-001",
            "cheque_date": "2026-10-01",
            "amount_in_words": "Test Only",
            "amount_in_numerals": float(inv["total_amount"]),
            "predicted_clearance_date": "2026-10-02",
        }
    ]
    invoice_map = {
        0: [
            {
                "invoices_id": inv["invoices_id"],
                "amount": float(inv["total_amount"]),
                "part_index": 1,
                "part_count": 1,
            }
        ]
    }

    try:
        repo.save_cheques(cheques, invoice_map)
    except Exception as exc:
        print("SAVE FAILED:", type(exc).__name__, exc)
        # still inspect partial state
        chs = query("SELECT * FROM cheque WHERE cheque_no = ?", ("TEST-SAVE-001",))
        print("partial cheque rows:", [dict(c) for c in chs])
        if chs:
            with transaction() as conn:
                cid = chs[0]["cheque_id"]
                conn.execute("DELETE FROM deposit_timetable WHERE cheque_id = ?", (cid,))
                conn.execute("DELETE FROM cheque_invoice_allocation WHERE cheque_id = ?", (cid,))
                conn.execute(
                    "UPDATE invoices SET cheque_id = NULL WHERE invoices_id = ?",
                    (inv["invoices_id"],),
                )
                conn.execute("DELETE FROM cheque WHERE cheque_id = ?", (cid,))
            print("partial cleanup done")
        return

    ch = query("SELECT * FROM cheque WHERE cheque_no = ?", ("TEST-SAVE-001",))[0]
    print("saved cheque:", dict(ch))
    alloc = query(
        "SELECT * FROM cheque_invoice_allocation WHERE cheque_id = ?",
        (ch["cheque_id"],),
    )
    print("allocation:", [dict(a) for a in alloc])
    tt = query(
        "SELECT * FROM deposit_timetable WHERE cheque_id = ?",
        (ch["cheque_id"],),
    )
    print("timetable:", [dict(t) for t in tt])
    linked = query(
        "SELECT invoices_id, cheque_id FROM invoices WHERE invoices_id = ?",
        (inv["invoices_id"],),
    )[0]
    print("invoice link:", dict(linked))

    with transaction() as conn:
        conn.execute("DELETE FROM deposit_timetable WHERE cheque_id = ?", (ch["cheque_id"],))
        conn.execute(
            "DELETE FROM cheque_invoice_allocation WHERE cheque_id = ?",
            (ch["cheque_id"],),
        )
        conn.execute(
            "UPDATE invoices SET cheque_id = NULL WHERE invoices_id = ?",
            (inv["invoices_id"],),
        )
        conn.execute("DELETE FROM cheque WHERE cheque_id = ?", (ch["cheque_id"],))
    print("cleanup done")

    # Backfill timetable for existing written cheques
    for row in query("SELECT cheque_id FROM cheque"):
        invrow = query(
            "SELECT dealer_id FROM invoices WHERE cheque_id = ? LIMIT 1",
            (row["cheque_id"],),
        )
        dealer_id = invrow[0]["dealer_id"] if invrow else None
        try:
            repo.sync_timetable_from_cheque(row["cheque_id"], dealer_id)
            print("synced timetable for cheque", row["cheque_id"])
        except Exception as exc:
            print("sync FAILED for", row["cheque_id"], ":", exc)

    print(
        "timetable rows now:",
        query("SELECT COUNT(*) AS n FROM deposit_timetable")[0]["n"],
    )
    for t in query(
        "SELECT cheque_id, stated_date, total_amount, target_funding_date, days_gained, status FROM deposit_timetable"
    ):
        print(dict(t))


if __name__ == "__main__":
    main()
