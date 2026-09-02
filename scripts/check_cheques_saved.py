"""Check whether committed cheques are stored correctly."""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from db import repositories as repo
from db.connection import get_connection


def main():
    db = ROOT / "database" / "invoice_cheque.db"
    print("DB:", db, "exists=", db.exists())
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    tables = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )]
    print("tables:", ", ".join(tables))

    for t in ("cheque_invoice_allocation", "deposit_timetable", "analyst_reports"):
        if t in tables:
            n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"{t}: {n} rows")
        else:
            print(f"{t}: MISSING")

    print("\n=== cheque rows (verification_status=1 = written) ===")
    rows = cur.execute(
        """SELECT cheque_id, cheque_no, cheque_date, amount_in_numerals,
                  verification_status, predicted_clearance_date, user_bank_acc_id,
                  cheque_print_date
           FROM cheque ORDER BY cheque_id"""
    ).fetchall()
    for r in rows:
        print(dict(r))

    metrics = repo.get_analytics_metrics()
    print("\n=== analytics metrics (UI source) ===")
    print(metrics)

    print("\n=== invoice <-> cheque links ===")
    linked = cur.execute(
        """SELECT i.invoices_id, i.invoice_no, i.cheque_id, i.total_amount,
                  c.cheque_no, c.amount_in_numerals
           FROM invoices i
           LEFT JOIN cheque c ON c.cheque_id = i.cheque_id
           WHERE i.cheque_id IS NOT NULL
           ORDER BY i.invoices_id"""
    ).fetchall()
    for r in linked:
        print(dict(r))

    if "cheque_invoice_allocation" in tables:
        print("\n=== allocations ===")
        for r in cur.execute("SELECT * FROM cheque_invoice_allocation"):
            print(dict(r))

    if "deposit_timetable" in tables:
        print("\n=== deposit_timetable ===")
        for r in cur.execute("SELECT * FROM deposit_timetable"):
            print(dict(r))

    # Integrity checks
    issues = []
    total = sum(float(r["amount_in_numerals"]) for r in rows if r["verification_status"] == 1)
    if abs(total - float(metrics["committed_cheques_total_lkr"])) > 0.01:
        issues.append("metrics total mismatch vs cheque table")
    if int(metrics["committed_cheques_count"]) != sum(1 for r in rows if r["verification_status"] == 1):
        issues.append("metrics count mismatch vs cheque table")

    for r in linked:
        if r["cheque_id"] and not r["cheque_no"]:
            issues.append(f"invoice {r['invoice_no']} points to missing cheque_id={r['cheque_id']}")

    # Seed fingerprint
    seed_nos = {"000145", "000146", "000089"}
    actual_nos = {r["cheque_no"] for r in rows}
    if actual_nos == seed_nos:
        print("\nNOTE: All 3 cheques match seed.sql sample data — no app-committed cheques found yet.")
    elif seed_nos.issubset(actual_nos):
        print("\nNOTE: Seed cheques still present; additional committed cheques also exist.")
    else:
        print("\nNOTE: Cheque set differs from seed (app commits likely present).")

    print("\n=== integrity ===")
    if issues:
        print("ISSUES:")
        for i in issues:
            print(" -", i)
    else:
        print("OK: Cheques written count/total match DB; invoice links resolve.")

    conn.close()


if __name__ == "__main__":
    main()
