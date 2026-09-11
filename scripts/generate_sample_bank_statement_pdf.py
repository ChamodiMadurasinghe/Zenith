"""
Generates a sample bank-statement PDF using the real account and cheque data
currently sitting in the database — so you have something realistic to email
yourself and run through the "Verify" button (scenario 7 in the manual test
checklist), instead of only ever testing against the generic fixture text in
`sample_statement_text()`.

This does NOT change anything in the database — it only reads it. The PDF is
written to docs/agent_test_samples/.

Usage:
    python scripts/generate_sample_bank_statement_pdf.py [account_id]

If account_id is omitted, it uses the first bank account found. One of that
account's *pending* cheques (the earliest by stated_date) is shown as
"cleared" on the statement — a realistic scenario where the bank has cleared
a cheque before Zenith's own records were updated — so that running Verify
against this PDF produces a genuine matched cheque and a genuine balance
discrepancy to look at, rather than everything trivially matching.
"""

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from db.connection import query, query_one

OUT_DIR = ROOT / "docs" / "agent_test_samples"


def pick_account(account_id: int | None) -> dict:
    if account_id:
        acc = query_one("SELECT * FROM user_bank_account WHERE user_bank_acc_id = ?", (account_id,))
    else:
        acc = query_one("SELECT * FROM user_bank_account LIMIT 1")
    if not acc:
        raise SystemExit("No bank account found — add one in the app first.")
    return acc


def pending_cheques(account_id: int) -> list:
    return query(
        """SELECT dt.total_amount, dt.stated_date, c.cheque_no
           FROM deposit_timetable dt
           LEFT JOIN cheque c ON c.cheque_id = dt.cheque_id
           WHERE dt.user_bank_acc_id = ? AND dt.status = 'pending'
           ORDER BY dt.stated_date""",
        (account_id,),
    )


def expected_income(account_id: int) -> dict | None:
    """A deposit the business is expecting but hasn't recorded as received
    yet — a realistic 'income' line for the statement: the bank shows it
    landed, Zenith doesn't know that yet."""
    return query_one(
        """SELECT amount, planned_date, notes FROM planned_deposits
           WHERE user_bank_acc_id = ? AND status = 'planned'
           ORDER BY planned_date LIMIT 1""",
        (account_id,),
    )


def build_statement(account: dict, pending: list, income: dict | None) -> dict:
    """Picks the earliest pending cheque to show as cleared, an expected
    deposit to show as received, and works out a closing balance consistent
    with both — so the statement has a realistic mix of a debit and a
    credit, not just cheques."""
    today = date.today()
    period_start = today.replace(day=1)
    period_end = today

    cleared_cheque = pending[0] if pending else None
    still_pending = pending[1:] if pending else []

    balance = float(account["available_balance"])
    if cleared_cheque:
        # The bank has already taken this cheque out of the account; Zenith's
        # own balance hasn't been updated to reflect that yet — that gap is
        # exactly what "Verify" should catch.
        balance -= float(cleared_cheque["total_amount"])
    if income:
        # The bank shows this deposit landed; Zenith still has it as merely
        # "planned", not received — another gap Verify should surface.
        balance += float(income["amount"])

    return {
        "period_start": period_start,
        "period_end": period_end,
        "cleared_cheque": cleared_cheque,
        "still_pending": still_pending,
        "income": income,
        "closing_balance": balance,
    }


def render_pdf(account: dict, statement: dict, out_path: Path):
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("BankTitle", parent=styles["Title"], fontSize=16)
    normal = styles["Normal"]

    doc = SimpleDocTemplate(str(out_path), pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
    story = []

    bank_name = account.get("bank_name") or "Your Bank"
    story.append(Paragraph(f"{bank_name.upper()}", title_style))
    story.append(Paragraph("Monthly Statement of Account", styles["Heading2"]))
    story.append(Spacer(1, 6))

    period = f"{statement['period_start'].strftime('%d-%b-%Y').upper()} to {statement['period_end'].strftime('%d-%b-%Y').upper()}"
    info_lines = [
        f"Account Name: {account.get('account_name', '')}",
        f"Branch: {account.get('branch_name') or '-'}",
        f"Statement Period: {period}",
    ]
    for line in info_lines:
        story.append(Paragraph(line, normal))
    story.append(Spacer(1, 12))

    rows = [["Date", "Description", "Amount (Rs.)"]]
    if statement["cleared_cheque"]:
        c = statement["cleared_cheque"]
        cleared_date = statement["period_start"] + timedelta(days=4)
        rows.append(
            [
                cleared_date.strftime("%d-%b-%Y").upper(),
                f"Cheque No {c['cheque_no']} cleared",
                "-{:,.2f}".format(c["total_amount"]),
            ]
        )
    if statement["income"]:
        inc = statement["income"]
        income_date = statement["period_start"] + timedelta(days=9)
        description = "Deposit received"
        if inc.get("notes"):
            description = f"Deposit received — {inc['notes']}"
        rows.append(
            [
                income_date.strftime("%d-%b-%Y").upper(),
                description,
                "+{:,.2f}".format(inc["amount"]),
            ]
        )
    if len(rows) == 1:
        rows.append(["-", "No transactions this period", "-"])

    table = Table(rows, colWidths=[80, 260, 100])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1b3a5c")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ALIGN", (2, 0), (2, -1), "RIGHT"),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 16))

    story.append(
        Paragraph(f"<b>Closing Balance&nbsp;&nbsp;&nbsp;&nbsp;Rs. {statement['closing_balance']:,.2f}</b>", normal)
    )
    story.append(Spacer(1, 16))
    story.append(
        Paragraph(
            "This is a sample statement generated from data already in Zenith, for testing "
            "the monthly statement verification feature. It is not a real bank document.",
            styles["Italic"],
        )
    )

    doc.build(story)


def main():
    account_id = int(sys.argv[1]) if len(sys.argv) > 1 else None
    account = pick_account(account_id)
    pending = pending_cheques(account["user_bank_acc_id"])
    income = expected_income(account["user_bank_acc_id"])
    statement = build_statement(account, pending, income)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"sample_bank_statement_account_{account['user_bank_acc_id']}.pdf"
    render_pdf(account, statement, out_path)

    print(f"Wrote {out_path}")
    if statement["cleared_cheque"]:
        print(
            f"  Shown as cleared: cheque {statement['cleared_cheque']['cheque_no']} "
            f"for Rs. {statement['cleared_cheque']['total_amount']:,.2f}"
        )
    else:
        print("  No pending cheques on this account — statement has no cleared cheque line.")
    if statement["income"]:
        print(
            f"  Shown as income:  Rs. {statement['income']['amount']:,.2f} "
            f"({statement['income'].get('notes') or 'deposit received'})"
        )
    else:
        print("  No planned deposits on this account — statement has no income line.")
    print(f"  Closing balance on statement: Rs. {statement['closing_balance']:,.2f}")
    print(f"  Zenith's current balance:     Rs. {account['available_balance']:,.2f}")
    print(
        "\nTo test scenario 7 for real: email yourself this PDF from the address you set "
        "as 'Bank email' in the app, with a subject like 'Your Monthly Statement of "
        "Account', then click Verify."
    )


if __name__ == "__main__":
    main()
