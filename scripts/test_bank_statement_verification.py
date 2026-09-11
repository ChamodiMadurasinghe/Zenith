"""
Quick manual test for the monthly statement verification feature —
no Flask server, no real mailbox, no bank statement email required.

Runs the whole pipeline (sample statement text -> parse -> compare against
whatever's in the database for the given account -> print the result) the
same way the "Test with sample data" button in the Bank Balance tab does.

Usage:
    python scripts/test_bank_statement_verification.py [account_id]

If account_id is omitted, it uses the first bank account found.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.bank_statement_mail import parse_statement_text, run_verification, sample_statement_text
from db.connection import query_one


def pick_account_id() -> int | None:
    row = query_one("SELECT user_bank_acc_id FROM user_bank_account LIMIT 1")
    return row["user_bank_acc_id"] if row else None


def main():
    print("1) Parsing the built-in sample statement text on its own:")
    parsed = parse_statement_text(sample_statement_text())
    print("   Cashed cheques found:", parsed["cashed_cheques"])
    print("   Closing balance found:", parsed["closing_balance"])

    account_id = int(sys.argv[1]) if len(sys.argv) > 1 else pick_account_id()
    if account_id is None:
        print("\nNo bank account exists in the database yet — add one first, "
              "then re-run this script with its account id.")
        return

    print(f"\n2) Running the full verification pipeline against account {account_id} "
          f"(is_test=True, nothing real is contacted):")
    result = run_verification(account_id, is_test=True)
    if "error" in result:
        print("   Error:", result["error"])
        return

    print("   Statement balance: ", result["statement_balance"])
    print("   System balance:    ", result["system_balance"])
    print("   Balances match:    ", result["balance_matches"])
    print("   Matched cashed cheques:  ", result["matched_cashed"])
    print("   Unmatched cashed cheques:", result["unmatched_cashed"])
    print("   Still pending in system: ", result["still_pending"])
    print("   Discrepancies:           ", result["discrepancies"])
    print("\nSaved to bank_statement_verifications — it'll also show up on the "
          "Bank Balance tab for this account (with the 'Test run' badge).")


if __name__ == "__main__":
    main()
