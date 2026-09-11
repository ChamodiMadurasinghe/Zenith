"""
Monthly bank-statement verification.

Every month the bank emails a statement (usually a PDF attachment) to the
business's own mailbox. This module:

  1. Connects to the business email over IMAP, using settings the user
     enters in the Bank Balance tab.
  2. Finds the latest email that (a) actually came from the configured bank
     email address and (b) looks like the *monthly statement* — day-to-day
     transaction alerts ("cheque cleared", "your account has been
     credited", OTP mails, etc.) are deliberately skipped.
  3. Extracts the statement text (the PDF attachment if there is one,
     otherwise the email body) and pulls out the cashed cheques and the
     closing balance.
  4. Compares that against what Zenith already has on record — the
     system's pending cheques and current balance — and returns a
     verification report that the Bank Balance tab displays.

Design note: this file is intentionally self-contained. It reads/writes the
database directly through `db.connection` instead of going through
`db/repositories.py`, and it is wired into the app through its own
blueprint (`routes/bank_statement.py`). Nothing in Person One's
`db/repositories.py`, `core/cash_flow.py`, or `routes/cash_flow.py` is
touched or imported for writing.

Before this works with a real mailbox:
  - The "app password" field needs a Gmail *app password* (or your
    provider's equivalent) — not the normal account password.
  - CHEQUE_LINE_RE / BALANCE_RE below are written to match a fairly generic
    LK bank e-statement layout. Once you have a real sample statement from
    your bank, check it parses correctly with `parse_statement_text()` and
    adjust the two regexes if your bank's wording differs.
"""

import email
import imaplib
import io
import json
import re
from datetime import datetime
from email.header import decode_header

from db.connection import execute, query, query_one

# --- keywords used to recognise a monthly statement vs. a transaction alert ---
STATEMENT_KEYWORDS = [
    "monthly statement",
    "e-statement",
    "estatement",
    "account statement",
    "statement of account",
    "your statement",
]
TRANSACTION_KEYWORDS = [
    "credited",
    "debited",
    "cheque cleared",
    "cheque clearance",
    "credit alert",
    "debit alert",
    "otp",
    "one time password",
    "transaction alert",
    "payment received",
    "payment made",
]

# Matches lines like "Cheque No 000123 cleared ... Rs. 45,000.00"
CHEQUE_LINE_RE = re.compile(
    r"(?:cheque|chq)[^\d]{0,15}(?P<no>\d{5,8})[^\d]{0,40}"
    r"(?:rs\.?|lkr)?\s*(?P<amount>[\d,]+\.\d{2})",
    re.IGNORECASE,
)
# Matches "Closing Balance ... Rs. 215,340.50" (also "available"/"current balance")
BALANCE_RE = re.compile(
    r"(?:closing|available|current)\s+balance[^\d\-]{0,20}"
    r"(?:rs\.?|lkr)?\s*(?P<amount>-?[\d,]+\.\d{2})",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Settings: business email + bank email
# ---------------------------------------------------------------------------

def get_mail_config(account_id: int) -> dict | None:
    """Business/bank email settings for one bank account, or None if unset."""
    return query_one(
        "SELECT * FROM bank_statement_mail_config WHERE user_bank_acc_id = ?",
        (account_id,),
    )


def save_mail_config(
    account_id: int,
    business_email: str,
    business_app_password: str,
    bank_email: str,
    imap_host: str = "imap.gmail.com",
    imap_port: int = 993,
) -> int:
    """Create or update the mail settings for a bank account. Returns the row id."""
    existing = get_mail_config(account_id)
    if existing:
        # Keep the existing app password if the user left the field blank
        # (so they don't have to re-type it every time they change bank_email).
        password_to_store = business_app_password or existing["business_email_app_password"]
        execute(
            """UPDATE bank_statement_mail_config
               SET business_email = ?, business_email_app_password = ?, bank_email = ?,
                   imap_host = ?, imap_port = ?, updated_at = datetime('now')
               WHERE user_bank_acc_id = ?""",
            (business_email, password_to_store, bank_email, imap_host, imap_port, account_id),
        )
        return existing["config_id"]
    return execute(
        """INSERT INTO bank_statement_mail_config
           (user_bank_acc_id, business_email, business_email_app_password,
            bank_email, imap_host, imap_port)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (account_id, business_email, business_app_password, bank_email, imap_host, imap_port),
    )


# ---------------------------------------------------------------------------
# Mail reading
# ---------------------------------------------------------------------------

def _decode(value: str) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    out = []
    for text, enc in parts:
        if isinstance(text, bytes):
            out.append(text.decode(enc or "utf-8", errors="ignore"))
        else:
            out.append(text)
    return "".join(out)


def is_monthly_statement_email(subject: str, sender: str, bank_email: str) -> bool:
    """
    True only for the monthly statement itself — never for a day-to-day
    transaction alert, even if it also came from the bank.
    """
    subject_l = (subject or "").lower()
    sender_l = (sender or "").lower()
    if bank_email and bank_email.strip().lower() not in sender_l:
        return False
    if any(k in subject_l for k in TRANSACTION_KEYWORDS):
        return False
    return any(k in subject_l for k in STATEMENT_KEYWORDS)


def _pdf_to_text(pdf_bytes: bytes) -> str:
    if not pdf_bytes:
        return ""
    try:
        import pdfplumber
    except ImportError:
        # pdfplumber isn't installed — fall back to no attachment text.
        # (see requirements.txt: `pip install pdfplumber`)
        return ""
    text_parts = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text_parts.append(page.extract_text() or "")
    return "\n".join(text_parts)


def _extract_statement_text(msg) -> str:
    """Prefer a PDF attachment; fall back to the plain-text email body."""
    body_text = ""
    for part in msg.walk():
        disposition = str(part.get("Content-Disposition") or "")
        filename = part.get_filename() or ""

        if "attachment" in disposition and filename.lower().endswith(".pdf"):
            pdf_text = _pdf_to_text(part.get_payload(decode=True))
            if pdf_text:
                return pdf_text
        elif part.get_content_type() == "text/plain" and not body_text:
            payload = part.get_payload(decode=True)
            if payload:
                body_text = payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
    return body_text


def fetch_latest_statement_email(config: dict) -> dict | None:
    """
    Connects to the business mailbox and returns the latest *monthly
    statement* email from the configured bank address, or None if none is
    found. Never returns a transaction/alert email, even if one matches
    the sender.
    """
    conn = imaplib.IMAP4_SSL(config["imap_host"], int(config["imap_port"]))
    try:
        conn.login(config["business_email"], config["business_email_app_password"])
        conn.select("INBOX")
        # Only search mail FROM the bank's address — the rest of the inbox
        # (invoices, WhatsApp notices, etc.) is never touched.
        typ, data = conn.search(None, "FROM", f'"{config["bank_email"]}"')
        if typ != "OK" or not data or not data[0]:
            return None

        ids = data[0].split()
        for msg_id in reversed(ids[-30:]):  # newest first, last 30 from that sender
            typ, msg_data = conn.fetch(msg_id, "(RFC822)")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            subject = _decode(msg.get("Subject", ""))
            sender = _decode(msg.get("From", ""))
            if not is_monthly_statement_email(subject, sender, config["bank_email"]):
                continue  # skip transaction alerts / anything else from the bank
            return {
                "message_id": msg.get("Message-ID") or msg_id.decode(),
                "subject": subject,
                "sender": sender,
                "date": _decode(msg.get("Date", "")),
                "text": _extract_statement_text(msg),
            }
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass
        try:
            conn.logout()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_statement_text(text: str) -> dict:
    """
    Pulls cashed-cheque lines and the closing balance out of statement text.
    Heuristic and regex-based — see the module docstring about tuning
    CHEQUE_LINE_RE / BALANCE_RE once you have a real statement to test with.
    """
    text = text or ""
    cheques = []
    seen_no = set()
    for match in CHEQUE_LINE_RE.finditer(text):
        no = match.group("no")
        if no in seen_no:
            continue
        seen_no.add(no)
        cheques.append({"cheque_no": no, "amount": float(match.group("amount").replace(",", ""))})

    balance = None
    bal_match = BALANCE_RE.search(text)
    if bal_match:
        balance = float(bal_match.group("amount").replace(",", ""))

    return {"cashed_cheques": cheques, "closing_balance": balance}


# ---------------------------------------------------------------------------
# Comparison against Zenith's own records
# ---------------------------------------------------------------------------

def _system_pending_cheques(account_id: int) -> list:
    """Cheques Zenith still considers 'to be cashed' for this account."""
    return query(
        """SELECT dt.cheque_id, c.cheque_no, dt.total_amount, dt.stated_date
           FROM deposit_timetable dt
           LEFT JOIN cheque c ON c.cheque_id = dt.cheque_id
           WHERE dt.user_bank_acc_id = ? AND dt.status = 'pending'
           ORDER BY dt.stated_date""",
        (account_id,),
    )


def _system_balance(account_id: int) -> float | None:
    row = query_one(
        "SELECT available_balance FROM user_bank_account WHERE user_bank_acc_id = ?",
        (account_id,),
    )
    return row["available_balance"] if row else None


def _compare(account_id: int, parsed: dict) -> dict:
    pending = _system_pending_cheques(account_id)
    pending_nos = {p["cheque_no"] for p in pending if p["cheque_no"]}

    matched_cashed, unmatched_cashed = [], []
    for c in parsed["cashed_cheques"]:
        if c["cheque_no"] in pending_nos:
            matched_cashed.append({**c, "matched_system_pending": True})
        else:
            unmatched_cashed.append({**c, "matched_system_pending": False})

    cashed_nos = {c["cheque_no"] for c in parsed["cashed_cheques"]}
    still_pending = [p for p in pending if p["cheque_no"] not in cashed_nos]

    system_balance = _system_balance(account_id)
    statement_balance = parsed["closing_balance"]
    balance_matches = (
        statement_balance is not None
        and system_balance is not None
        and abs(statement_balance - system_balance) < 1.0
    )

    discrepancies = []
    if statement_balance is not None and not balance_matches:
        discrepancies.append(
            "System shows Rs. {:,.2f} but the statement shows Rs. {:,.2f}.".format(
                system_balance or 0, statement_balance
            )
        )
    for c in unmatched_cashed:
        discrepancies.append(
            "Cheque {} appears cashed on the statement but isn't in Zenith's "
            "pending list — check it was recorded.".format(c["cheque_no"])
        )

    return {
        "matched_cashed": matched_cashed,
        "unmatched_cashed": unmatched_cashed,
        "still_pending": still_pending,
        "system_balance": system_balance,
        "statement_balance": statement_balance,
        "balance_matches": balance_matches,
        "discrepancies": discrepancies,
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def sample_statement_text() -> str:
    """
    Fixture statement text used by the 'Test' button and the standalone test
    script, so the whole pipeline (parse -> compare -> save) can be
    exercised without a real mailbox or a real statement email.
    """
    return """
    SAMPLE BANK PLC -- Monthly Statement of Account
    Statement Period: 01-AUG-2026 to 31-AUG-2026

    Date        Description                              Amount (Rs.)
    05-AUG-2026 Cheque No 000123 cleared                    45,000.00
    12-AUG-2026 Cheque No 000456 cleared                    12,500.00
    20-AUG-2026 Cheque 000789 paid                          30,000.00

    Closing Balance                                        215,340.50
    """


def run_verification(account_id: int, is_test: bool = False) -> dict:
    """
    Full pipeline for the 'Verify' (or 'Test') button: fetch the latest
    monthly statement (or use the fixture, in test mode), parse it, compare
    it against Zenith's records, save the result, and return it.

    Returns {"error": "no_mail_config" | "no_statement_found"} if it
    couldn't run — the route turns that into a flash message.
    """
    if is_test:
        statement = {
            "message_id": "test-{}".format(datetime.now().isoformat()),
            "subject": "Monthly Statement of Account (test run)",
            "sender": "sample-bank@example.com",
            "date": datetime.now().isoformat(),
            "text": sample_statement_text(),
        }
    else:
        config = get_mail_config(account_id)
        if not config:
            return {"error": "no_mail_config"}
        statement = fetch_latest_statement_email(config)
        if not statement:
            return {"error": "no_statement_found"}

    parsed = parse_statement_text(statement["text"])
    comparison = _compare(account_id, parsed)

    result = {
        "is_test": is_test,
        "message_id": statement["message_id"],
        "subject": statement["subject"],
        "statement_date": statement["date"],
        **comparison,
    }

    execute(
        """INSERT INTO bank_statement_verifications
           (user_bank_acc_id, statement_email_date, statement_subject, message_id,
            statement_balance, system_balance, balance_matches,
            cashed_cheques_json, pending_cheques_json, discrepancies_json, is_test)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            account_id,
            statement["date"],
            statement["subject"],
            statement["message_id"],
            comparison["statement_balance"],
            comparison["system_balance"],
            1 if comparison["balance_matches"] else 0,
            json.dumps(comparison["matched_cashed"] + comparison["unmatched_cashed"]),
            json.dumps(comparison["still_pending"], default=str),
            json.dumps(comparison["discrepancies"]),
            1 if is_test else 0,
        ),
    )
    return result


def latest_verification(account_id: int) -> dict | None:
    """Most recent saved verification (test or real) for the balance tab to display."""
    row = query_one(
        """SELECT * FROM bank_statement_verifications
           WHERE user_bank_acc_id = ? ORDER BY created_at DESC LIMIT 1""",
        (account_id,),
    )
    if not row:
        return None
    cashed = json.loads(row["cashed_cheques_json"] or "[]")
    return {
        "is_test": bool(row["is_test"]),
        "subject": row["statement_subject"],
        "statement_date": row["statement_email_date"],
        "statement_balance": row["statement_balance"],
        "system_balance": row["system_balance"],
        "balance_matches": bool(row["balance_matches"]),
        "matched_cashed": [c for c in cashed if c.get("matched_system_pending")],
        "unmatched_cashed": [c for c in cashed if not c.get("matched_system_pending")],
        "still_pending": json.loads(row["pending_cheques_json"] or "[]"),
        "discrepancies": json.loads(row["discrepancies_json"] or "[]"),
        "created_at": row["created_at"],
    }
