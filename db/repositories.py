import json
import sqlite3
from datetime import date, datetime, timedelta

from config import Config
from core.date_presets import (
    PRESET_ALL,
    PRESET_CUSTOM,
    WEEK_MONTH_PRESETS,
    preset_date_strings,
)
from core.ingestion_helpers import PENDING_SUPPLIER_NAME, normalize_line_item
from db.connection import execute, query, query_one, transaction


def get_user():
    return query_one("SELECT * FROM user WHERE user_id = ?", (Config.USER_ID,))


def get_setting(key: str, default: str = "") -> str:
    row = query_one("SELECT setting_value FROM app_settings WHERE setting_key = ?", (key,))
    return row["setting_value"] if row else default


def set_setting(key: str, value: str):
    execute(
        """INSERT INTO app_settings (setting_key, setting_value) VALUES (?, ?)
           ON CONFLICT(setting_key) DO UPDATE SET setting_value = excluded.setting_value""",
        (key, str(value)),
    )


MERCHANT_WHATSAPP_PHONE_KEY = "merchant_whatsapp_phone"


def get_merchant_whatsapp_phone() -> str:
    """Shop owner WhatsApp for alerts; app_settings overrides .env."""
    from core.whatsapp_utils import normalize_whatsapp_phone

    stored = get_setting(MERCHANT_WHATSAPP_PHONE_KEY, "").strip()
    if stored:
        return normalize_whatsapp_phone(stored)
    env_phone = _env_merchant_whatsapp_phone()
    return normalize_whatsapp_phone(env_phone) if env_phone else ""


def _env_merchant_whatsapp_phone() -> str:
    import os

    return os.getenv("MERCHANT_WHATSAPP_PHONE", "").strip()


def save_merchant_whatsapp_phone(phone: str) -> str:
    from core.whatsapp_utils import normalize_whatsapp_phone

    normalized = normalize_whatsapp_phone(phone)
    if not normalized or not normalized.startswith("+"):
        raise ValueError("invalid phone")
    set_setting(MERCHANT_WHATSAPP_PHONE_KEY, normalized)
    return normalized


def clear_merchant_whatsapp_phone():
    execute("DELETE FROM app_settings WHERE setting_key = ?", (MERCHANT_WHATSAPP_PHONE_KEY,))


def get_bank_accounts():
    rows = query(
        "SELECT * FROM user_bank_account WHERE user_id = ? ORDER BY user_bank_acc_id",
        (Config.USER_ID,),
    )
    for row in rows:
        row.setdefault("overdraft_limit", 0)
    return rows


def get_bank_account(acc_id: int):
    row = query_one(
        "SELECT * FROM user_bank_account WHERE user_bank_acc_id = ? AND user_id = ?",
        (acc_id, Config.USER_ID),
    )
    if row is not None:
        row.setdefault("overdraft_limit", 0)
    return row


def _overdraft_limit_from(data: dict) -> float:
    try:
        value = float(data.get("overdraft_limit") or 0)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, value)


def create_bank_account(data: dict) -> int:
    return execute(
        """INSERT INTO user_bank_account
           (user_id, account_name, nickname, available_balance, overdraft_limit, branch_name, bank_name)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            Config.USER_ID,
            (data.get("account_name") or "").strip(),
            (data.get("nickname") or data.get("account_name") or "").strip() or None,
            float(data.get("available_balance") or 0),
            _overdraft_limit_from(data),
            (data.get("branch_name") or "").strip() or None,
            (data.get("bank_name") or "").strip(),
        ),
    )


def update_bank_account(acc_id: int, data: dict):
    execute(
        """UPDATE user_bank_account
           SET account_name = ?, nickname = ?, branch_name = ?, bank_name = ?, overdraft_limit = ?
           WHERE user_bank_acc_id = ? AND user_id = ?""",
        (
            (data.get("account_name") or "").strip(),
            (data.get("nickname") or data.get("account_name") or "").strip() or None,
            (data.get("branch_name") or "").strip() or None,
            (data.get("bank_name") or "").strip(),
            _overdraft_limit_from(data),
            acc_id,
            Config.USER_ID,
        ),
    )


def update_balance(acc_id: int, balance: float):
    execute(
        "UPDATE user_bank_account SET available_balance = ? WHERE user_bank_acc_id = ? AND user_id = ?",
        (balance, acc_id, Config.USER_ID),
    )


def paying_account_id_for_dealer(dealer_id: int | None = None) -> int:
    """Merchant account used when paying this dealer (else app default)."""
    if dealer_id:
        dealer = get_dealer(dealer_id)
        if dealer and dealer.get("default_user_bank_acc_id"):
            acc = get_bank_account(int(dealer["default_user_bank_acc_id"]))
            if acc:
                return int(acc["user_bank_acc_id"])
    return int(get_setting("default_bank_acc_id", "1"))


def validate_bank_account_input(data: dict) -> str | None:
    if not (data.get("account_name") or "").strip():
        return "flash_bank_account_name_required"
    if not (data.get("bank_name") or "").strip() and not (data.get("bank_code") or "").strip():
        return "flash_bank_name_required"
    bank_code = (data.get("bank_code") or "").strip()
    if bank_code and not bank_name_for_code(bank_code):
        return "flash_bank_name_required"
    try:
        overdraft = float(data.get("overdraft_limit") or 0)
    except (TypeError, ValueError):
        return "flash_overdraft_invalid"
    if overdraft < 0:
        return "flash_overdraft_invalid"
    return None


def get_dealers():
    return query("SELECT * FROM dealers ORDER BY dealer_name")


def find_dealer_by_name_exact(name: str, exclude_dealer_id: int | None = None):
    """Exact name match (case-insensitive). Used to block/reuse duplicate dealers."""
    normalized = (name or "").strip().lower()
    if not normalized:
        return None
    for d in get_dealers():
        if exclude_dealer_id is not None and int(d["dealer_id"]) == int(exclude_dealer_id):
            continue
        if d["dealer_name"].strip().lower() == PENDING_SUPPLIER_NAME.lower():
            continue
        if d["dealer_name"].strip().lower() == normalized:
            return d
    return None


def find_dealer_by_name(name: str):
    """Prefer exact match, then substring (OCR fuzzy). Skip Pending Supplier."""
    exact = find_dealer_by_name_exact(name)
    if exact:
        return exact
    dealers = get_dealers()
    normalized = (name or "").strip().lower()
    if not normalized:
        return None
    for d in dealers:
        if d["dealer_name"].strip().lower() == PENDING_SUPPLIER_NAME.lower():
            continue
        if normalized in d["dealer_name"].strip().lower():
            return d
    return None


def get_pending_supplier_dealer_id() -> int:
    row = query_one(
        "SELECT dealer_id FROM dealers WHERE dealer_name = ?",
        (PENDING_SUPPLIER_NAME,),
    )
    if not row:
        raise RuntimeError(
            f"Dealer '{PENDING_SUPPLIER_NAME}' not found. Run: python scripts/init_db.py --migrate"
        )
    return int(row["dealer_id"])


def get_dealer(dealer_id: int):
    return query_one("SELECT * FROM dealers WHERE dealer_id = ?", (dealer_id,))


def create_dealer(data: dict) -> int:
    return execute(
        """INSERT INTO dealers (dealer_name, dealer_email, dealer_telno, dealer_address,
           dealer_strictness, casual_days, impossible_days, default_user_bank_acc_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data["dealer_name"],
            data.get("dealer_email"),
            data.get("dealer_telno"),
            data.get("dealer_address"),
            data.get("dealer_strictness", "Medium"),
            int(data.get("casual_days", 3)),
            data.get("impossible_days", "Sunday"),
            data.get("default_user_bank_acc_id"),
        ),
    )


def update_dealer(dealer_id: int, data: dict):
    execute(
        """UPDATE dealers SET dealer_name = ?, dealer_email = ?, dealer_telno = ?,
           dealer_address = ?, dealer_strictness = ?, casual_days = ?, impossible_days = ?,
           default_user_bank_acc_id = ?
           WHERE dealer_id = ?""",
        (
            data["dealer_name"],
            data.get("dealer_email"),
            data.get("dealer_telno"),
            data.get("dealer_address"),
            data.get("dealer_strictness", "Medium"),
            int(data.get("casual_days", 3)),
            data.get("impossible_days", "Sunday"),
            data.get("default_user_bank_acc_id"),
            dealer_id,
        ),
    )


def _null_invoice_refs(conn, invoice_id: int):
    for sql in (
        "UPDATE whatsapp_inbox SET invoice_id = NULL WHERE invoice_id = ?",
        "UPDATE inbound_messages SET invoice_id = NULL WHERE invoice_id = ?",
    ):
        try:
            conn.execute(sql, (invoice_id,))
        except sqlite3.OperationalError:
            pass


def invoice_is_on_cheque(invoice_id: int) -> bool:
    row = query_one(
        """SELECT invoices_id FROM invoices
           WHERE invoices_id = ? AND user_id = ? AND cheque_id IS NOT NULL""",
        (invoice_id, Config.USER_ID),
    )
    if row:
        return True
    alloc = query_one(
        "SELECT allocation_id FROM cheque_invoice_allocation WHERE invoices_id = ?",
        (invoice_id,),
    )
    return bool(alloc)


def dealer_has_cheques(dealer_id: int) -> bool:
    row = query_one(
        """SELECT i.invoices_id FROM invoices i
           WHERE i.dealer_id = ? AND i.user_id = ?
             AND (i.cheque_id IS NOT NULL
                  OR EXISTS (
                      SELECT 1 FROM cheque_invoice_allocation a
                      WHERE a.invoices_id = i.invoices_id
                  ))
           LIMIT 1""",
        (dealer_id, Config.USER_ID),
    )
    return bool(row)


def delete_invoice(invoice_id: int) -> str | None:
    """Remove an invoice that is not on a cheque. Returns an i18n error key or None."""
    invoice = get_invoice(invoice_id)
    if not invoice:
        return "flash_invoice_not_found"
    if invoice.get("user_id") is not None and int(invoice["user_id"]) != int(Config.USER_ID):
        return "flash_invoice_not_found"
    if invoice_is_on_cheque(invoice_id):
        return "flash_cannot_remove_invoice_on_cheque"
    with transaction() as conn:
        _null_invoice_refs(conn, invoice_id)
        conn.execute("DELETE FROM cheque_invoice_allocation WHERE invoices_id = ?", (invoice_id,))
        conn.execute("DELETE FROM item WHERE invoices_id = ?", (invoice_id,))
        conn.execute(
            "DELETE FROM invoices WHERE invoices_id = ? AND user_id = ?",
            (invoice_id, Config.USER_ID),
        )
    return None


def delete_dealer(dealer_id: int) -> str | None:
    """Remove a supplier and invoices that are not on a cheque. Returns an i18n error key or None."""
    dealer = get_dealer(dealer_id)
    if not dealer:
        return "flash_dealer_not_found"
    if (dealer.get("dealer_name") or "").strip().lower() == PENDING_SUPPLIER_NAME.lower():
        return "flash_cannot_remove_pending_supplier"
    if dealer_has_cheques(dealer_id):
        return "flash_cannot_remove_supplier_with_cheques"
    invoices = query(
        "SELECT invoices_id FROM invoices WHERE dealer_id = ? AND user_id = ?",
        (dealer_id, Config.USER_ID),
    )
    invoice_ids = [int(row["invoices_id"]) for row in invoices]
    with transaction() as conn:
        for invoice_id in invoice_ids:
            _null_invoice_refs(conn, invoice_id)
            conn.execute("DELETE FROM cheque_invoice_allocation WHERE invoices_id = ?", (invoice_id,))
            conn.execute("DELETE FROM item WHERE invoices_id = ?", (invoice_id,))
        if invoice_ids:
            conn.execute(
                f"DELETE FROM invoices WHERE dealer_id = ? AND user_id = ? AND invoices_id IN ({','.join('?' * len(invoice_ids))})",
                (dealer_id, Config.USER_ID, *invoice_ids),
            )
        try:
            conn.execute("DELETE FROM bundle_drafts WHERE dealer_id = ?", (dealer_id,))
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("DELETE FROM deposit_timetable WHERE dealer_id = ?", (dealer_id,))
        except sqlite3.OperationalError:
            pass
        conn.execute(
            "UPDATE dealers SET preferred_dealer_bank_acc_id = NULL WHERE dealer_id = ?",
            (dealer_id,),
        )
        conn.execute("DELETE FROM dealers_bank_account WHERE dealer_id = ?", (dealer_id,))
        conn.execute("DELETE FROM dealers WHERE dealer_id = ?", (dealer_id,))
    return None


def validate_dealer_bank_input(data: dict) -> str | None:
    """Return error key for i18n flash, or None if valid."""
    if not (data.get("account_name") or "").strip():
        return "flash_dealer_bank_required"
    if not (data.get("bank_name") or "").strip():
        return "flash_dealer_bank_required"
    acc_id = data.get("default_user_bank_acc_id")
    if not acc_id:
        return "flash_select_paying_account"
    if not get_bank_account(int(acc_id)):
        return "flash_select_paying_account"
    return None


def upsert_dealer_bank_account(dealer_id: int, data: dict) -> bool:
    bank_name = (data.get("bank_name") or "").strip()
    if not bank_name:
        return False
    account_name = (data.get("account_name") or "").strip()
    if not account_name:
        return False
    branch_name = (data.get("branch_name") or "").strip() or None
    existing = get_dealer_preferred_bank(dealer_id)
    if existing:
        execute(
            """UPDATE dealers_bank_account SET account_name = ?, branch_name = ?, bank_name = ?
               WHERE dealer_bank_acc_id = ?""",
            (account_name, branch_name, bank_name, existing["dealer_bank_acc_id"]),
        )
        return True
    bank_id = execute(
        """INSERT INTO dealers_bank_account (dealer_id, account_name, branch_name, bank_name)
           VALUES (?, ?, ?, ?)""",
        (dealer_id, account_name, branch_name, bank_name),
    )
    execute(
        "UPDATE dealers SET preferred_dealer_bank_acc_id = ? WHERE dealer_id = ?",
        (bank_id, dealer_id),
    )
    return True


def save_dealer_banking(dealer_id: int, data: dict) -> str | None:
    """Validate and persist supplier + merchant bank links. Returns i18n error key or None."""
    err = validate_dealer_bank_input(data)
    if err:
        return err
    if not upsert_dealer_bank_account(dealer_id, data):
        return "flash_dealer_bank_required"
    execute(
        "UPDATE dealers SET default_user_bank_acc_id = ? WHERE dealer_id = ?",
        (int(data["default_user_bank_acc_id"]), dealer_id),
    )
    return None


def get_recent_invoices(limit=10):
    return query(
        """SELECT i.*, d.dealer_name FROM invoices i
           JOIN dealers d ON d.dealer_id = i.dealer_id
           WHERE i.user_id = ? ORDER BY i.invoices_id DESC LIMIT ?""",
        (Config.USER_ID, limit),
    )


def get_verified_unassigned_invoices(dealer_id: int):
    return query(
        """SELECT * FROM invoices
           WHERE dealer_id = ? AND user_id = ? AND is_invoice_verified = 1 AND cheque_id IS NULL
           ORDER BY invoiced_date""",
        (dealer_id, Config.USER_ID),
    )


def get_pending_verification_invoices(dealer_id: int = None):
    display_name = (
        "COALESCE("
        "NULLIF(json_extract(i.pending_dealer_json, '$.dealer_name'), ''), "
        "d.dealer_name)"
    )
    if dealer_id is not None:
        return query(
            f"""SELECT i.*, d.dealer_name,
                       {display_name} AS display_dealer_name
               FROM invoices i
               JOIN dealers d ON d.dealer_id = i.dealer_id
               WHERE i.dealer_id = ? AND i.user_id = ? AND i.is_invoice_verified = 0
               ORDER BY i.invoiced_date""",
            (dealer_id, Config.USER_ID),
        )
    return query(
        f"""SELECT i.*, d.dealer_name,
                   {display_name} AS display_dealer_name,
                   json_extract(i.pending_dealer_json, '$.source') AS source
           FROM invoices i
           JOIN dealers d ON d.dealer_id = i.dealer_id
           WHERE i.user_id = ? AND i.is_invoice_verified = 0
           ORDER BY i.invoices_id DESC""",
        (Config.USER_ID,),
    )


def get_dealer_invoice_summary(dealer_id: int) -> dict:
    rows = query(
        """SELECT
             SUM(CASE WHEN is_invoice_verified = 1 AND cheque_id IS NULL THEN 1 ELSE 0 END) AS ready,
             SUM(CASE WHEN is_invoice_verified = 0 THEN 1 ELSE 0 END) AS pending_verification,
             SUM(CASE WHEN cheque_id IS NOT NULL THEN 1 ELSE 0 END) AS on_cheque
           FROM invoices WHERE dealer_id = ? AND user_id = ?""",
        (dealer_id, Config.USER_ID),
    )[0]
    return {
        "ready": int(rows["ready"] or 0),
        "pending_verification": int(rows["pending_verification"] or 0),
        "on_cheque": int(rows["on_cheque"] or 0),
    }


def get_all_dealer_summaries() -> dict:
    dealers = get_dealers()
    return {d["dealer_id"]: get_dealer_invoice_summary(d["dealer_id"]) for d in dealers}


def _parse_iso_date(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def invoice_due_date_value(invoice: dict) -> date | None:
    inv_date = _parse_iso_date(invoice.get("invoiced_date"))
    if not inv_date:
        return None
    try:
        days = int(invoice.get("credit_period_days") or 0)
    except (TypeError, ValueError):
        days = 0
    return inv_date + timedelta(days=days)


CHEQUE_VISIBLE_AFTER_CLEARANCE_DAYS = 7


def cheque_clearance_date(ch: dict) -> str | None:
    """Predicted clearance, else deposit_timetable fund-by, else stated cheque date."""
    if ch.get("predicted_clearance_date"):
        return ch["predicted_clearance_date"]
    row = query_one(
        """SELECT target_funding_date FROM deposit_timetable
           WHERE cheque_id = ? ORDER BY timetable_id DESC LIMIT 1""",
        (ch.get("cheque_id"),),
    )
    if row and row.get("target_funding_date"):
        return row["target_funding_date"]
    return ch.get("cheque_date")


def _parse_optional_float(raw) -> float | None:
    text = (str(raw) if raw is not None else "").strip()
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def list_amount_summary(rows: list, amount_key: str = "total_amount") -> dict:
    """Aggregate count / sum / average for the currently visible list rows."""
    total = 0.0
    count = 0
    for row in rows or []:
        try:
            total += float(row.get(amount_key) or 0)
            count += 1
        except (TypeError, ValueError):
            continue
    return {
        "count": count,
        "total": total,
        "average": (total / count) if count else 0.0,
    }


def written_cheque_filters_from_args(args) -> dict:
    """Parse list-page query params. Searching or show_all overrides the 7-day cutoff."""
    cheque_no = (args.get("cheque_no") or "").strip() or None
    period = (args.get("period") or "").strip().lower() or PRESET_CUSTOM
    start_date = (args.get("start_date") or "").strip() or None
    end_date = (args.get("end_date") or "").strip() or None
    if period in WEEK_MONTH_PRESETS:
        start_date, end_date = preset_date_strings(period)
    elif period == PRESET_ALL:
        start_date, end_date = None, None
    min_amount = _parse_optional_float(args.get("min_amount"))
    max_amount = _parse_optional_float(args.get("max_amount"))
    show_all = str(args.get("show_all") or "").strip().lower() in ("1", "true", "on", "yes")
    if period == PRESET_ALL:
        show_all = True
    searching = bool(
        cheque_no
        or start_date
        or end_date
        or show_all
        or min_amount is not None
        or max_amount is not None
        or period in WEEK_MONTH_PRESETS
        or period == PRESET_ALL
    )
    return {
        "include_archived": searching,
        "cheque_no": cheque_no,
        "start_date": start_date,
        "end_date": end_date,
        "min_amount": min_amount,
        "max_amount": max_amount,
        "period": period,
        "show_all": show_all,
    }


def written_cheque_repo_kwargs(filters: dict) -> dict:
    return {
        "include_archived": bool(filters.get("include_archived")),
        "cheque_no": filters.get("cheque_no"),
        "start_date": filters.get("start_date"),
        "end_date": filters.get("end_date"),
        "min_amount": filters.get("min_amount"),
        "max_amount": filters.get("max_amount"),
    }


def filter_written_cheques(
    rows: list,
    *,
    include_archived: bool = False,
    cheque_no: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
) -> list:
    """Hide cheques older than 7 days past clearance unless searching/show-all."""
    needle = (cheque_no or "").strip().lower()
    start = _parse_iso_date(start_date)
    end = _parse_iso_date(end_date)
    apply_cutoff = not (
        include_archived or needle or start or end or min_amount is not None or max_amount is not None
    )
    cutoff = date.today() - timedelta(days=CHEQUE_VISIBLE_AFTER_CLEARANCE_DAYS)
    out = []
    for ch in rows:
        if needle and needle not in str(ch.get("cheque_no") or "").lower():
            continue
        stated = _parse_iso_date(ch.get("cheque_date"))
        if start and (stated is None or stated < start):
            continue
        if end and (stated is None or stated > end):
            continue
        try:
            amount = float(ch.get("amount_in_numerals") if ch.get("amount_in_numerals") is not None else ch.get("amount") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        if min_amount is not None and amount < min_amount:
            continue
        if max_amount is not None and amount > max_amount:
            continue
        if apply_cutoff:
            clearance = _parse_iso_date(
                ch.get("expected_clearance_date")
                or ch.get("predicted_clearance_date")
                or ch.get("cheque_date")
            )
            if clearance is not None and clearance < cutoff:
                continue
        out.append(ch)
    return out


INVOICE_PAYMENT_WITHOUT_CHEQUE = "without_cheque"
INVOICE_PAYMENT_WITH_CHEQUE = "with_cheque"
INVOICE_PAYMENT_ALL = "all"
INVOICE_PAYMENT_STATUSES = frozenset(
    {INVOICE_PAYMENT_WITHOUT_CHEQUE, INVOICE_PAYMENT_WITH_CHEQUE, INVOICE_PAYMENT_ALL}
)


def invoice_filters_from_args(args) -> dict:
    """Parse dealer-invoice list query params. Default shows unpaid (no cheque) only."""
    invoice_no = (args.get("invoice_no") or "").strip() or None
    period = (args.get("period") or "").strip().lower() or PRESET_CUSTOM
    start_date = (args.get("start_date") or "").strip() or None
    end_date = (args.get("end_date") or "").strip() or None
    if period in WEEK_MONTH_PRESETS:
        start_date, end_date = preset_date_strings(period)
    elif period == PRESET_ALL:
        start_date, end_date = None, None
    payment_status = (args.get("payment_status") or "").strip().lower()
    if payment_status not in INVOICE_PAYMENT_STATUSES:
        # Legacy checkbox: include_committed=1 meant show all invoices
        if str(args.get("include_committed") or "").strip().lower() in ("1", "true", "on", "yes"):
            payment_status = INVOICE_PAYMENT_ALL
        else:
            payment_status = INVOICE_PAYMENT_WITHOUT_CHEQUE
    return {
        "invoice_no": invoice_no,
        "start_date": start_date,
        "end_date": end_date,
        "min_amount": _parse_optional_float(args.get("min_amount")),
        "max_amount": _parse_optional_float(args.get("max_amount")),
        "period": period,
        "payment_status": payment_status,
    }


def invoice_repo_kwargs(filters: dict) -> dict:
    return {
        "payment_status": filters.get("payment_status") or INVOICE_PAYMENT_WITHOUT_CHEQUE,
        "invoice_no": filters.get("invoice_no"),
        "date_from": filters.get("start_date"),
        "date_to": filters.get("end_date"),
        "min_amount": filters.get("min_amount"),
        "max_amount": filters.get("max_amount"),
    }


def days_gained_vs_due(invoices: list, clearance_str: str | None) -> int | None:
    """(expected_clearance_date - earliest_invoice_due_date).days"""
    clearance = _parse_iso_date(clearance_str)
    if not clearance or not invoices:
        return None
    dues = [d for d in (invoice_due_date_value(inv) for inv in invoices) if d]
    if not dues:
        return None
    return (clearance - min(dues)).days


def _invoices_for_cheque(cheque_id: int) -> list:
    return query(
        """SELECT i.invoices_id, i.invoice_no, i.invoiced_date, i.delivery_date,
                  i.credit_period_days, i.total_amount, i.dealer_id,
                  a.amount AS allocated_amount, a.part_index, a.part_count
           FROM invoices i
           LEFT JOIN cheque_invoice_allocation a
             ON a.invoices_id = i.invoices_id AND a.cheque_id = ?
           WHERE i.user_id = ?
             AND (
               i.cheque_id = ?
               OR i.invoices_id IN (
                 SELECT invoices_id FROM cheque_invoice_allocation WHERE cheque_id = ?
               )
             )
           ORDER BY i.invoice_no, a.part_index""",
        (cheque_id, Config.USER_ID, cheque_id, cheque_id),
    )


def get_dealer_committed_payment_history(dealer_id: int) -> list[dict]:
    """Committed cheques for pattern analysis (all history, verified only)."""
    bundles = get_committed_cheque_bundles(dealer_id, include_archived=True)
    history: list[dict] = []
    for ch in bundles:
        if int(ch.get("verification_status") or 0) != 1:
            continue
        acc_id = int(ch.get("user_bank_acc_id") or 0)
        acc = get_bank_account(acc_id) if acc_id else None
        clearance = ch.get("expected_clearance_date") or cheque_clearance_date(ch)
        invoices = []
        for inv in ch.get("invoices") or []:
            invoices.append(
                {
                    **inv,
                    "part_index": int(inv.get("part_index") or 1),
                    "part_count": int(inv.get("part_count") or 1),
                    "clearance_date": clearance,
                }
            )
        history.append(
            {
                **ch,
                "user_bank_acc_id": acc_id,
                "bank_name": acc.get("bank_name") if acc else None,
                "account_nickname": acc.get("nickname") if acc else None,
                "clearance_date": clearance,
                "invoices": invoices,
            }
        )
    return history


def get_committed_cheque_bundles(
    dealer_id: int,
    *,
    include_archived: bool = False,
    cheque_no: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
):
    # Prefer invoice.cheque_id; also include allocation links (split parts / partial updates).
    cheques = query(
        """SELECT DISTINCT c.* FROM cheque c
           WHERE c.cheque_id IN (
               SELECT i.cheque_id FROM invoices i
               WHERE i.dealer_id = ? AND i.user_id = ? AND i.cheque_id IS NOT NULL
               UNION
               SELECT a.cheque_id FROM cheque_invoice_allocation a
               JOIN invoices i ON i.invoices_id = a.invoices_id
               WHERE i.dealer_id = ? AND i.user_id = ?
           )
           ORDER BY c.cheque_date DESC""",
        (dealer_id, Config.USER_ID, dealer_id, Config.USER_ID),
    )
    dealer = get_dealer(dealer_id)
    dealer_name = dealer["dealer_name"] if dealer else None
    result = []
    for ch in cheques:
        invoices = _invoices_for_cheque(ch["cheque_id"])
        clearance = cheque_clearance_date(ch)
        result.append(
            {
                **ch,
                "invoices": invoices,
                "dealer_name": dealer_name,
                "expected_clearance_date": clearance,
                "days_gained": days_gained_vs_due(invoices, clearance),
            }
        )
    return filter_written_cheques(
        result,
        include_archived=include_archived,
        cheque_no=cheque_no,
        start_date=start_date,
        end_date=end_date,
        min_amount=min_amount,
        max_amount=max_amount,
    )


def list_account_written_cheques(
    account_id: int,
    *,
    include_archived: bool = False,
    cheque_no: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
) -> list:
    """Committed cheques on an account for history lists (not cash-flow projection)."""
    rows = []
    for ch in get_upcoming_cheques(account_id):
        clearance = cheque_clearance_date(ch)
        rows.append(
            {
                **ch,
                "expected_clearance_date": clearance,
                "amount": float(ch.get("amount_in_numerals") or 0),
            }
        )
    return filter_written_cheques(
        rows,
        include_archived=include_archived,
        cheque_no=cheque_no,
        start_date=start_date,
        end_date=end_date,
        min_amount=min_amount,
        max_amount=max_amount,
    )


def get_cheque_detail(cheque_id: int) -> dict | None:
    """Read-only cheque + payee + linked invoices (and line items). None if missing/unauthorized."""
    from core.amounts import amount_to_words

    ch = query_one(
        """SELECT c.*,
                  uba.nickname AS bank_nickname,
                  uba.account_name AS bank_account_name,
                  uba.bank_name AS paying_bank_name,
                  uba.branch_name AS paying_branch
           FROM cheque c
           JOIN user_bank_account uba ON uba.user_bank_acc_id = c.user_bank_acc_id
           WHERE c.cheque_id = ? AND uba.user_id = ?""",
        (cheque_id, Config.USER_ID),
    )
    if not ch:
        return None

    invoice_rows = _invoices_for_cheque(cheque_id)
    invoices_out = []
    dealer_id = None
    for inv in invoice_rows:
        dealer_id = dealer_id or inv.get("dealer_id")
        items = get_invoice_items(inv["invoices_id"])
        due = invoice_due_date_value(inv)
        allocated = inv.get("allocated_amount")
        invoices_out.append(
            {
                "invoices_id": inv["invoices_id"],
                "invoice_no": inv["invoice_no"],
                "invoiced_date": inv.get("invoiced_date"),
                "due_date": due.isoformat() if due else None,
                "credit_period_days": inv.get("credit_period_days"),
                "total_amount": float(inv.get("total_amount") or 0),
                "allocated_amount": float(allocated if allocated is not None else inv.get("total_amount") or 0),
                "part_index": inv.get("part_index"),
                "part_count": inv.get("part_count"),
                "line_items": [
                    {
                        "item_code": it.get("item_code"),
                        "item_name": it.get("item_name"),
                        "item_qty": it.get("item_qty"),
                        "item_price": it.get("item_price"),
                    }
                    for it in items
                ],
            }
        )

    dealer = get_dealer(dealer_id) if dealer_id else None
    clearance = cheque_clearance_date(ch)
    amount = float(ch.get("amount_in_numerals") or 0)
    return {
        "cheque_id": ch["cheque_id"],
        "cheque_no": ch.get("cheque_no"),
        "cheque_date": ch.get("cheque_date"),
        "expected_clearance_date": clearance,
        "amount": amount,
        "amount_in_words": ch.get("amount_in_words") or amount_to_words(amount),
        "days_gained": days_gained_vs_due(invoice_rows, clearance),
        "bank": {
            "nickname": ch.get("bank_nickname"),
            "account_name": ch.get("bank_account_name"),
            "bank_name": ch.get("paying_bank_name"),
            "branch_name": ch.get("paying_branch"),
        },
        "dealer": {
            "dealer_id": dealer["dealer_id"] if dealer else None,
            "dealer_name": dealer["dealer_name"] if dealer else None,
            "dealer_email": dealer.get("dealer_email") if dealer else None,
            "dealer_telno": dealer.get("dealer_telno") if dealer else None,
            "dealer_address": dealer.get("dealer_address") if dealer else None,
            "casual_days": dealer.get("casual_days") if dealer else None,
            "dealer_strictness": dealer.get("dealer_strictness") if dealer else None,
        },
        "invoices": invoices_out,
    }


def ensure_invoice_delivery_date_column():
    """Add delivery_date on existing DBs without a full migrate."""
    try:
        execute("ALTER TABLE invoices ADD COLUMN delivery_date TEXT")
    except Exception:
        pass


def ensure_item_pricing_columns():
    """Add MRP and line-total columns on existing DBs without a full migrate."""
    for sql in (
        "ALTER TABLE item ADD COLUMN item_mrp REAL NOT NULL DEFAULT 0",
        "ALTER TABLE item ADD COLUMN item_line_total REAL NOT NULL DEFAULT 0",
    ):
        try:
            execute(sql)
        except Exception:
            pass


def _insert_invoice_items(conn, invoice_id: int, items: list):
    for raw in items:
        item = normalize_line_item(raw)
        conn.execute(
            """INSERT INTO item (invoices_id, item_code, item_name, item_qty, item_price,
               item_discount, item_mrp, item_line_total)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                invoice_id,
                item["item_code"],
                item["item_name"],
                item["item_qty"],
                item["item_price"],
                item["item_discount"],
                item["item_mrp"],
                item["item_line_total"],
            ),
        )


def get_dealer_invoices(
    dealer_id: int,
    *,
    payment_status: str = INVOICE_PAYMENT_WITHOUT_CHEQUE,
    invoice_no: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
):
    """Invoices for a dealer with optional archival/search filters.

    payment_status: without_cheque (default), with_cheque, or all.
    Date range uses COALESCE(delivery_date, invoiced_date).
    """
    ensure_invoice_delivery_date_column()
    status = payment_status if payment_status in INVOICE_PAYMENT_STATUSES else INVOICE_PAYMENT_WITHOUT_CHEQUE
    sql = [
        """SELECT invoices_id, invoice_no, total_amount, invoiced_date, delivery_date,
                  credit_period_days, location_path, is_invoice_verified, cheque_id
           FROM invoices
           WHERE dealer_id = ? AND user_id = ?"""
    ]
    params: list = [dealer_id, Config.USER_ID]
    if status == INVOICE_PAYMENT_WITHOUT_CHEQUE:
        sql.append("AND cheque_id IS NULL")
    elif status == INVOICE_PAYMENT_WITH_CHEQUE:
        sql.append("AND cheque_id IS NOT NULL")
    needle = (invoice_no or "").strip()
    if needle:
        sql.append("AND LOWER(invoice_no) LIKE ?")
        params.append(f"%{needle.lower()}%")
    if date_from:
        sql.append("AND COALESCE(delivery_date, invoiced_date) >= ?")
        params.append(date_from)
    if date_to:
        sql.append("AND COALESCE(delivery_date, invoiced_date) <= ?")
        params.append(date_to)
    if min_amount is not None:
        sql.append("AND total_amount >= ?")
        params.append(float(min_amount))
    if max_amount is not None:
        sql.append("AND total_amount <= ?")
        params.append(float(max_amount))
    sql.append("ORDER BY COALESCE(delivery_date, invoiced_date) ASC, invoice_no ASC")
    return query("\n".join(sql), tuple(params))


def update_verified_invoice(invoice_id: int, data: dict, items: list, dealer_id: int):
    ensure_invoice_delivery_date_column()
    ensure_item_pricing_columns()
    with transaction() as conn:
        conn.execute(
            """UPDATE invoices SET dealer_id = ?, invoice_no = ?, invoiced_date = ?,
               delivery_date = ?, credit_period_days = ?, total_amount = ?,
               is_invoice_verified = 1, pending_dealer_json = NULL
               WHERE invoices_id = ? AND user_id = ?""",
            (
                dealer_id,
                data["invoice_no"],
                data["invoiced_date"],
                data.get("delivery_date") or None,
                int(data["credit_period_days"]),
                float(data["total_amount"]),
                invoice_id,
                Config.USER_ID,
            ),
        )
        conn.execute("DELETE FROM item WHERE invoices_id = ?", (invoice_id,))
        _insert_invoice_items(conn, invoice_id, items)


def update_invoice_record(invoice_id: int, data: dict, items: list, dealer_id: int):
    """Update invoice header + line items without changing verification status."""
    ensure_invoice_delivery_date_column()
    ensure_item_pricing_columns()
    with transaction() as conn:
        conn.execute(
            """UPDATE invoices SET dealer_id = ?, invoice_no = ?, invoiced_date = ?,
               delivery_date = ?, credit_period_days = ?, total_amount = ?
               WHERE invoices_id = ? AND user_id = ?""",
            (
                dealer_id,
                data["invoice_no"],
                data["invoiced_date"],
                data.get("delivery_date") or None,
                int(data["credit_period_days"]),
                float(data["total_amount"]),
                invoice_id,
                Config.USER_ID,
            ),
        )
        conn.execute("DELETE FROM item WHERE invoices_id = ?", (invoice_id,))
        _insert_invoice_items(conn, invoice_id, items)


def get_invoice(invoice_id: int):
    ensure_invoice_delivery_date_column()
    return query_one(
        "SELECT i.*, d.dealer_name FROM invoices i JOIN dealers d ON d.dealer_id = i.dealer_id WHERE i.invoices_id = ?",
        (invoice_id,),
    )


def get_invoice_items(invoice_id: int):
    ensure_item_pricing_columns()
    return query("SELECT * FROM item WHERE invoices_id = ?", (invoice_id,))


def find_invoice_by_no_and_dealer(
    invoice_no: str,
    dealer_id: int,
    exclude_invoice_id: int | None = None,
):
    """Same dealer + same invoice_no is a duplicate (per user)."""
    invoice_no = (invoice_no or "").strip()
    if not invoice_no:
        return None
    if exclude_invoice_id is not None:
        return query_one(
            """SELECT invoices_id, invoice_no, total_amount, invoiced_date
               FROM invoices
               WHERE user_id = ? AND dealer_id = ? AND invoice_no = ?
                 AND invoices_id != ?
               ORDER BY invoices_id DESC LIMIT 1""",
            (Config.USER_ID, dealer_id, invoice_no, int(exclude_invoice_id)),
        )
    return query_one(
        """SELECT invoices_id, invoice_no, total_amount, invoiced_date
           FROM invoices
           WHERE user_id = ? AND dealer_id = ? AND invoice_no = ?
           ORDER BY invoices_id DESC LIMIT 1""",
        (Config.USER_ID, dealer_id, invoice_no),
    )


def get_dealer_invoice_stats(dealer_id: int) -> dict:
    row = query_one(
        """SELECT COUNT(*) AS cnt, AVG(total_amount) AS avg_amount
           FROM invoices
           WHERE user_id = ? AND dealer_id = ?""",
        (Config.USER_ID, dealer_id),
    )
    return {
        "count": int((row or {}).get("cnt") or 0),
        "avg_amount": float((row or {}).get("avg_amount") or 0),
    }


def get_dealer_item_price_stats(dealer_id: int, item_code: str) -> dict:
    """Backward-compatible wrapper — use get_dealer_item_history_stats when possible."""
    stats = get_dealer_item_history_stats(dealer_id, item_code=item_code)
    return {
        "sample_count": stats.get("sample_count", 0),
        "avg_price": stats.get("avg_price", 0.0),
        "avg_qty": stats.get("avg_qty", 0.0),
    }


def _normalize_item_name(name: str) -> str:
    return " ".join((name or "").strip().lower().split())


def get_dealer_item_history_stats(
    dealer_id: int,
    *,
    item_code: str | None = None,
    item_name: str | None = None,
) -> dict:
    """Historical qty/price stats for a dealer line item (verified invoices only)."""
    code = (item_code or "").strip()
    name_norm = _normalize_item_name(item_name or "")
    if code:
        row = query_one(
            """SELECT COUNT(*) AS sample_count,
                      AVG(i.item_price) AS avg_price,
                      AVG(i.item_qty) AS avg_qty,
                      MAX(i.item_qty) AS max_qty,
                      MIN(i.item_qty) AS min_qty
               FROM item i
               JOIN invoices inv ON inv.invoices_id = i.invoices_id
               WHERE inv.user_id = ? AND inv.dealer_id = ?
                 AND inv.is_invoice_verified = 1
                 AND i.item_code = ?""",
            (Config.USER_ID, dealer_id, code),
        )
        last = query_one(
            """SELECT inv.invoice_no, inv.invoiced_date
               FROM item i
               JOIN invoices inv ON inv.invoices_id = i.invoices_id
               WHERE inv.user_id = ? AND inv.dealer_id = ?
                 AND inv.is_invoice_verified = 1
                 AND i.item_code = ?
               ORDER BY inv.invoiced_date DESC, inv.invoices_id DESC
               LIMIT 1""",
            (Config.USER_ID, dealer_id, code),
        )
    elif name_norm:
        row = query_one(
            """SELECT COUNT(*) AS sample_count,
                      AVG(i.item_price) AS avg_price,
                      AVG(i.item_qty) AS avg_qty,
                      MAX(i.item_qty) AS max_qty,
                      MIN(i.item_qty) AS min_qty
               FROM item i
               JOIN invoices inv ON inv.invoices_id = i.invoices_id
               WHERE inv.user_id = ? AND inv.dealer_id = ?
                 AND inv.is_invoice_verified = 1
                 AND LOWER(TRIM(i.item_name)) = ?""",
            (Config.USER_ID, dealer_id, name_norm),
        )
        last = query_one(
            """SELECT inv.invoice_no, inv.invoiced_date
               FROM item i
               JOIN invoices inv ON inv.invoices_id = i.invoices_id
               WHERE inv.user_id = ? AND inv.dealer_id = ?
                 AND inv.is_invoice_verified = 1
                 AND LOWER(TRIM(i.item_name)) = ?
               ORDER BY inv.invoiced_date DESC, inv.invoices_id DESC
               LIMIT 1""",
            (Config.USER_ID, dealer_id, name_norm),
        )
    else:
        return {
            "sample_count": 0,
            "avg_price": 0.0,
            "avg_qty": 0.0,
            "max_qty": 0.0,
            "min_qty": 0.0,
            "last_invoice_no": None,
            "last_invoiced_date": None,
        }
    return {
        "sample_count": int((row or {}).get("sample_count") or 0),
        "avg_price": float((row or {}).get("avg_price") or 0),
        "avg_qty": float((row or {}).get("avg_qty") or 0),
        "max_qty": float((row or {}).get("max_qty") or 0),
        "min_qty": float((row or {}).get("min_qty") or 0),
        "last_invoice_no": (last or {}).get("invoice_no"),
        "last_invoiced_date": (last or {}).get("invoiced_date"),
    }


def find_recent_item_orders(
    dealer_id: int,
    *,
    item_code: str | None = None,
    item_name: str | None = None,
    within_days: int = 30,
    exclude_invoice_id: int | None = None,
) -> list[dict]:
    """Verified invoices containing this item within the last N days."""
    from datetime import date, timedelta

    cutoff = (date.today() - timedelta(days=int(within_days))).isoformat()
    code = (item_code or "").strip()
    name_norm = _normalize_item_name(item_name or "")
    params: list = [Config.USER_ID, dealer_id, cutoff]
    exclude_sql = ""
    if exclude_invoice_id is not None:
        exclude_sql = " AND inv.invoices_id != ?"
        params.append(int(exclude_invoice_id))

    if code:
        sql = f"""
            SELECT DISTINCT inv.invoices_id, inv.invoice_no, inv.invoiced_date,
                   i.item_qty, i.item_name, i.item_code
            FROM item i
            JOIN invoices inv ON inv.invoices_id = i.invoices_id
            WHERE inv.user_id = ? AND inv.dealer_id = ?
              AND inv.is_invoice_verified = 1
              AND inv.invoiced_date >= ?
              AND i.item_code = ?
              {exclude_sql}
            ORDER BY inv.invoiced_date DESC
        """
        params = [Config.USER_ID, dealer_id, cutoff, code]
        if exclude_invoice_id is not None:
            params.append(int(exclude_invoice_id))
    elif name_norm:
        sql = f"""
            SELECT DISTINCT inv.invoices_id, inv.invoice_no, inv.invoiced_date,
                   i.item_qty, i.item_name, i.item_code
            FROM item i
            JOIN invoices inv ON inv.invoices_id = i.invoices_id
            WHERE inv.user_id = ? AND inv.dealer_id = ?
              AND inv.is_invoice_verified = 1
              AND inv.invoiced_date >= ?
              AND LOWER(TRIM(i.item_name)) = ?
              {exclude_sql}
            ORDER BY inv.invoiced_date DESC
        """
        params = [Config.USER_ID, dealer_id, cutoff, name_norm]
        if exclude_invoice_id is not None:
            params.append(int(exclude_invoice_id))
    else:
        return []

    return query(sql, tuple(params))


def save_verified_invoice(data: dict, items: list, dealer_id: int) -> int:
    ensure_invoice_delivery_date_column()
    ensure_item_pricing_columns()
    with transaction() as conn:
        cursor = conn.execute(
            """INSERT INTO invoices (user_id, dealer_id, invoice_no, invoiced_date,
               delivery_date, credit_period_days, total_amount, location_path,
               is_invoice_verified)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                Config.USER_ID,
                dealer_id,
                data["invoice_no"],
                data["invoiced_date"],
                data.get("delivery_date") or None,
                int(data["credit_period_days"]),
                float(data["total_amount"]),
                data.get("location_path"),
            ),
        )
        invoice_id = cursor.lastrowid
        _insert_invoice_items(conn, invoice_id, items)
    return invoice_id


def save_pending_invoice(
    data: dict,
    items: list,
    dealer_id: int,
    pending_dealer_json: str | None = None,
) -> int:
    ensure_invoice_delivery_date_column()
    ensure_item_pricing_columns()
    with transaction() as conn:
        cursor = conn.execute(
            """INSERT INTO invoices (user_id, dealer_id, invoice_no, invoiced_date,
               delivery_date, credit_period_days, total_amount, location_path,
               pending_dealer_json, is_invoice_verified)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
            (
                Config.USER_ID,
                dealer_id,
                data["invoice_no"],
                data["invoiced_date"],
                data.get("delivery_date") or None,
                int(data["credit_period_days"]),
                float(data["total_amount"]),
                data.get("location_path"),
                pending_dealer_json,
            ),
        )
        invoice_id = cursor.lastrowid
        _insert_invoice_items(conn, invoice_id, items)
    return invoice_id


def update_invoice_dealer_id(invoice_id: int, dealer_id: int):
    execute(
        "UPDATE invoices SET dealer_id = ? WHERE invoices_id = ? AND user_id = ?",
        (dealer_id, invoice_id, Config.USER_ID),
    )


def ensure_whatsapp_inbox_schema():
    """Create whatsapp_inbox table on existing databases without full migrate."""
    execute(
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
        )"""
    )
    execute("CREATE INDEX IF NOT EXISTS idx_whatsapp_inbox_status ON whatsapp_inbox(status)")
    execute("CREATE INDEX IF NOT EXISTS idx_whatsapp_inbox_user ON whatsapp_inbox(user_id)")
    _migrate_legacy_awaiting_ai_stubs()


def _migrate_legacy_awaiting_ai_stubs():
    """Move older ai_status=awaiting invoice stubs into whatsapp_inbox."""
    stubs = query(
        """SELECT invoices_id, location_path,
                  json_extract(pending_dealer_json, '$.whatsapp_sender') AS sender_phone
           FROM invoices
           WHERE user_id = ? AND is_invoice_verified = 0
             AND json_extract(pending_dealer_json, '$.ai_status') = 'awaiting'""",
        (Config.USER_ID,),
    )
    if not stubs:
        return
    for stub in stubs:
        path = stub.get("location_path")
        if not path:
            continue
        with transaction() as conn:
            conn.execute(
                """INSERT INTO whatsapp_inbox (user_id, sender_phone, location_path, status)
                   VALUES (?, ?, ?, 'pending')""",
                (Config.USER_ID, stub.get("sender_phone"), path),
            )
            conn.execute("DELETE FROM item WHERE invoices_id = ?", (stub["invoices_id"],))
            conn.execute(
                "DELETE FROM invoices WHERE invoices_id = ? AND user_id = ?",
                (stub["invoices_id"], Config.USER_ID),
            )


def save_whatsapp_inbox(sender_phone: str | None, location_path: str) -> int:
    ensure_whatsapp_inbox_schema()
    with transaction() as conn:
        cursor = conn.execute(
            """INSERT INTO whatsapp_inbox (user_id, sender_phone, location_path, status)
               VALUES (?, ?, ?, 'pending')""",
            (Config.USER_ID, sender_phone, location_path),
        )
        return cursor.lastrowid


def get_whatsapp_inbox_pending():
    ensure_whatsapp_inbox_schema()
    return query(
        """SELECT * FROM whatsapp_inbox
           WHERE user_id = ? AND status = 'pending'
           ORDER BY received_at DESC""",
        (Config.USER_ID,),
    )


def get_whatsapp_inbox_item(inbox_id: int):
    ensure_whatsapp_inbox_schema()
    return query_one(
        "SELECT * FROM whatsapp_inbox WHERE inbox_id = ? AND user_id = ?",
        (inbox_id, Config.USER_ID),
    )


def mark_whatsapp_inbox_extracted(inbox_id: int, invoice_id: int):
    execute(
        """UPDATE whatsapp_inbox
           SET status = 'extracted', invoice_id = ?
           WHERE inbox_id = ? AND user_id = ?""",
        (invoice_id, inbox_id, Config.USER_ID),
    )


def dismiss_whatsapp_inbox(inbox_id: int):
    execute(
        """UPDATE whatsapp_inbox SET status = 'dismissed'
           WHERE inbox_id = ? AND user_id = ? AND status = 'pending'""",
        (inbox_id, Config.USER_ID),
    )


def upsert_whatsapp_session(phone: str, state: str, context: dict):
    execute(
        """INSERT OR REPLACE INTO whatsapp_sessions (phone, state, context_json, updated_at)
           VALUES (?, ?, ?, datetime('now'))""",
        (phone, state, json.dumps(context or {})),
    )


def get_whatsapp_session(phone: str) -> dict:
    row = query_one(
        "SELECT phone, state, context_json, updated_at FROM whatsapp_sessions WHERE phone = ?",
        (phone,),
    )
    if not row:
        return {"phone": phone, "state": "idle", "context": {}}
    try:
        context = json.loads(row.get("context_json") or "{}")
    except json.JSONDecodeError:
        context = {}
    return {"phone": phone, "state": row["state"], "context": context}


def clear_whatsapp_session(phone: str):
    execute("DELETE FROM whatsapp_sessions WHERE phone = ?", (phone,))


def get_all_account_ids() -> list[int]:
    return [int(r["user_bank_acc_id"]) for r in get_bank_accounts()]


def save_alert_log(channel: str, recipient: str, message: str):
    execute(
        """INSERT INTO alert_log (channel, recipient, message, sent_at)
           VALUES (?, ?, ?, datetime('now'))""",
        (channel, recipient, message),
    )


def get_holidays():
    return {row["holiday_date"] for row in query("SELECT holiday_date FROM cbsl_bank_holidays")}


def get_holidays_in_range(start: str, end: str) -> list[dict]:
    """Return CBSL holidays in [start, end] with descriptions."""
    rows = query(
        """
        SELECT holiday_date, description
        FROM cbsl_bank_holidays
        WHERE holiday_date >= ? AND holiday_date <= ?
        ORDER BY holiday_date
        """,
        (start, end),
    )
    return [
        {"date": row["holiday_date"], "description": row.get("description") or ""}
        for row in rows
    ]


def get_holiday_count() -> int:
    row = query_one("SELECT COUNT(*) AS n FROM cbsl_bank_holidays")
    return int(row["n"]) if row else 0


def replace_holidays_in_range(start: str, end: str, rows: list[tuple[str, str]]) -> int:
    """Replace all holidays in [start, end] with the given rows. Returns rows inserted."""
    with transaction() as conn:
        conn.execute(
            "DELETE FROM cbsl_bank_holidays WHERE holiday_date >= ? AND holiday_date <= ?",
            (start, end),
        )
        conn.executemany(
            "INSERT OR REPLACE INTO cbsl_bank_holidays (holiday_date, description) VALUES (?, ?)",
            rows,
        )
    return len(rows)


def get_dealer_preferred_bank(dealer_id: int):
    dealer = get_dealer(dealer_id)
    if not dealer or not dealer.get("preferred_dealer_bank_acc_id"):
        row = query_one(
            "SELECT * FROM dealers_bank_account WHERE dealer_id = ? ORDER BY dealer_bank_acc_id LIMIT 1",
            (dealer_id,),
        )
        return row
    return query_one(
        "SELECT * FROM dealers_bank_account WHERE dealer_bank_acc_id = ?",
        (dealer["preferred_dealer_bank_acc_id"],),
    )


def get_dealer_bank_names() -> dict:
    """Map dealer_id -> preferred bank name for interbank checks."""
    result = {}
    for d in get_dealers():
        bank = get_dealer_preferred_bank(d["dealer_id"])
        if bank:
            result[d["dealer_id"]] = bank["bank_name"]
    return result


def get_pending_timetable(account_id: int):
    return query(
        """SELECT * FROM deposit_timetable
           WHERE user_bank_acc_id = ? AND status = 'pending'
           ORDER BY stated_date""",
        (account_id,),
    )


def upsert_deposit_timetable_row(
    account_id: int,
    stated_date: str,
    total_amount: float,
    true_settlement_date: str,
    target_funding_date: str,
    days_gained: int,
    cheque_id: int = None,
    dealer_id: int = None,
):
    existing = None
    if cheque_id:
        existing = query_one(
            "SELECT timetable_id FROM deposit_timetable WHERE cheque_id = ? AND status = 'pending'",
            (cheque_id,),
        )
    if existing:
        execute(
            """UPDATE deposit_timetable SET stated_date = ?, true_settlement_date = ?,
               target_funding_date = ?, total_amount = ?, days_gained = ?, dealer_id = ?
               WHERE timetable_id = ?""",
            (
                stated_date,
                true_settlement_date,
                target_funding_date,
                total_amount,
                days_gained,
                dealer_id,
                existing["timetable_id"],
            ),
        )
        return existing["timetable_id"]
    return execute(
        """INSERT INTO deposit_timetable
           (user_bank_acc_id, cheque_id, dealer_id, stated_date, true_settlement_date,
            target_funding_date, total_amount, days_gained, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
        (
            account_id,
            cheque_id,
            dealer_id,
            stated_date,
            true_settlement_date,
            target_funding_date,
            total_amount,
            days_gained,
        ),
    )


def clear_timetable_row(cheque_id: int):
    execute(
        "UPDATE deposit_timetable SET status = 'cleared' WHERE cheque_id = ?",
        (cheque_id,),
    )


def sync_timetable_from_cheque(cheque_id: int, dealer_id: int = None):
    from core.liquidity_engine import apply_liquidity_dates, is_interbank

    ch = query_one("SELECT * FROM cheque WHERE cheque_id = ?", (cheque_id,))
    if not ch:
        return
    holidays = get_holidays()
    user_acc = get_bank_account(ch["user_bank_acc_id"])
    dealer_bank = get_dealer_preferred_bank(dealer_id) if dealer_id else None
    interbank = is_interbank(
        user_acc["bank_name"] if user_acc else "",
        dealer_bank["bank_name"] if dealer_bank else "",
    )
    dates = apply_liquidity_dates(ch["cheque_date"], holidays, is_interbank=interbank)
    upsert_deposit_timetable_row(
        ch["user_bank_acc_id"],
        ch["cheque_date"],
        ch["amount_in_numerals"],
        dates["true_settlement_date"],
        dates["target_funding_date"],
        dates["days_gained_total"],
        cheque_id=cheque_id,
        dealer_id=dealer_id,
    )


def build_pending_rows_for_account(account_id: int) -> list:
    """Pending timetable rows, falling back to committed cheques if timetable empty."""
    rows = get_pending_timetable(account_id)
    if rows:
        return [
            {
                "stated_date": r["stated_date"],
                "amount": r["total_amount"],
                "cheque_id": r.get("cheque_id"),
                "dealer_id": r.get("dealer_id"),
                "status": r["status"],
            }
            for r in rows
        ]
    pending = []
    for ch in get_upcoming_cheques(account_id):
        dealer_id = None
        inv = query_one(
            "SELECT dealer_id FROM invoices WHERE cheque_id = ? LIMIT 1",
            (ch["cheque_id"],),
        )
        if inv:
            dealer_id = inv["dealer_id"]
        pending.append(
            {
                "stated_date": ch["cheque_date"],
                "amount": ch["amount_in_numerals"],
                "cheque_id": ch["cheque_id"],
                "dealer_id": dealer_id,
                "status": "pending",
            }
        )
    return pending


def build_bank_context(account_id: int) -> dict:
    acc = get_bank_account(account_id)
    return {
        "user_bank_name": acc["bank_name"] if acc else "",
        "dealer_banks": get_dealer_bank_names(),
    }


def get_upcoming_cheques(account_id: int):
    """Committed cheques drawn on this merchant bank account (with payee)."""
    return query(
        """SELECT c.*,
                  (SELECT d.dealer_name
                   FROM invoices i
                   JOIN dealers d ON d.dealer_id = i.dealer_id
                   WHERE i.cheque_id = c.cheque_id
                   LIMIT 1) AS dealer_name
           FROM cheque c
           WHERE c.user_bank_acc_id = ?
             AND c.verification_status = 1
           ORDER BY COALESCE(c.predicted_clearance_date, c.cheque_date), c.cheque_id""",
        (account_id,),
    )


def get_planned_deposits(account_id: int):
    return query(
        "SELECT * FROM planned_deposits WHERE user_bank_acc_id = ? AND status = 'planned' ORDER BY planned_date",
        (account_id,),
    )


def get_bank_deposits(account_id: int, limit: int | None = None):
    sql = """SELECT * FROM bank_deposits
             WHERE user_bank_acc_id = ?
             ORDER BY deposit_date DESC, deposit_id DESC"""
    params: tuple = (account_id,)
    if limit is not None:
        sql += " LIMIT ?"
        params = (account_id, int(limit))
    return query(sql, params)


def record_deposit(account_id: int, deposit_date: str, amount: float, reference: str = ""):
    """Credit available_balance and append a bank_deposits row."""
    if amount <= 0:
        return None
    acc = get_bank_account(account_id)
    if not acc:
        return None
    with transaction() as conn:
        conn.execute(
            """INSERT INTO bank_deposits (user_bank_acc_id, deposit_date, amount, reference)
               VALUES (?, ?, ?, ?)""",
            (account_id, deposit_date, amount, reference or ""),
        )
        conn.execute(
            """UPDATE user_bank_account SET available_balance = available_balance + ?
               WHERE user_bank_acc_id = ? AND user_id = ?""",
            (amount, account_id, Config.USER_ID),
        )
    return True


def add_planned_deposit(account_id: int, planned_date: str, amount: float, notes: str = ""):
    return execute(
        """INSERT INTO planned_deposits (user_bank_acc_id, planned_date, amount, notes)
           VALUES (?, ?, ?, ?)""",
        (account_id, planned_date, amount, notes),
    )


def complete_planned_deposit(planned_id: int):
    planned = query_one("SELECT * FROM planned_deposits WHERE planned_deposit_id = ?", (planned_id,))
    if not planned:
        return None
    with transaction() as conn:
        conn.execute(
            "INSERT INTO bank_deposits (user_bank_acc_id, deposit_date, amount, reference) VALUES (?, ?, ?, ?)",
            (planned["user_bank_acc_id"], planned["planned_date"], planned["amount"], planned.get("notes") or ""),
        )
        conn.execute(
            "UPDATE planned_deposits SET status = 'done' WHERE planned_deposit_id = ?",
            (planned_id,),
        )
        acc = query_one(
            "SELECT available_balance FROM user_bank_account WHERE user_bank_acc_id = ?",
            (planned["user_bank_acc_id"],),
        )
        new_balance = acc["available_balance"] + planned["amount"]
        conn.execute(
            "UPDATE user_bank_account SET available_balance = ? WHERE user_bank_acc_id = ?",
            (new_balance, planned["user_bank_acc_id"]),
        )
    return planned


def get_outstanding_liabilities():
    return query(
        """SELECT COALESCE(SUM(total_amount), 0) AS total FROM invoices
           WHERE user_id = ? AND is_invoice_verified = 1 AND cheque_id IS NULL""",
        (Config.USER_ID,),
    )[0]["total"]


def get_recent_deposits_total(weeks=4):
    """Return total deposit amount over the last `weeks` week buckets."""
    rows = query(
        """SELECT strftime('%Y-W%W', deposit_date) AS week, SUM(amount) AS total
           FROM bank_deposits GROUP BY week ORDER BY week DESC LIMIT ?""",
        (weeks,),
    )
    return sum(float(r["total"] or 0) for r in rows)


def get_recent_deposits_by_week(weeks=4):
    """Return recent deposit totals grouped by week (newest first)."""
    return query(
        """SELECT strftime('%Y-W%W', deposit_date) AS week, SUM(amount) AS total
           FROM bank_deposits GROUP BY week ORDER BY week DESC LIMIT ?""",
        (weeks,),
    )


def save_cheques(cheques: list, invoice_map: dict):
    """Persist cheques and invoice links.

    invoice_map: {cheque_index: [invoice_id | {invoices_id, amount, part_index, part_count}]}
    Split parts write cheque_invoice_allocation rows so one invoice can fund multiple cheques.
    """
    with transaction() as conn:
        first_cheque_for_invoice: dict[int, int] = {}
        for idx, ch in enumerate(cheques):
            cursor = conn.execute(
                """INSERT INTO cheque (user_bank_acc_id, cheque_no, cheque_date, amount_in_words,
                   amount_in_numerals, verification_status, predicted_clearance_date)
                   VALUES (?, ?, ?, ?, ?, 1, ?)""",
                (
                    ch["user_bank_acc_id"],
                    ch["cheque_no"],
                    ch["cheque_date"],
                    ch["amount_in_words"],
                    ch["amount_in_numerals"],
                    ch["predicted_clearance_date"],
                ),
            )
            cheque_id = cursor.lastrowid
            for entry in invoice_map.get(idx, []) or []:
                if isinstance(entry, dict):
                    inv_id = int(entry["invoices_id"])
                    amount = float(entry.get("amount") or entry.get("total_amount") or 0)
                    part_index = int(entry.get("part_index") or 1)
                    part_count = int(entry.get("part_count") or 1)
                else:
                    inv_id = int(entry)
                    amount = None
                    part_index = 1
                    part_count = 1
                    row = conn.execute(
                        "SELECT total_amount FROM invoices WHERE invoices_id = ?",
                        (inv_id,),
                    ).fetchone()
                    amount = float(row[0]) if row else 0.0

                conn.execute(
                    """INSERT INTO cheque_invoice_allocation
                       (cheque_id, invoices_id, amount, part_index, part_count)
                       VALUES (?, ?, ?, ?, ?)""",
                    (cheque_id, inv_id, amount, part_index, part_count),
                )
                if inv_id not in first_cheque_for_invoice:
                    first_cheque_for_invoice[inv_id] = cheque_id
                    conn.execute(
                        "UPDATE invoices SET cheque_id = ? WHERE invoices_id = ?",
                        (cheque_id, inv_id),
                    )

    for idx, ch in enumerate(cheques):
        entries = invoice_map.get(idx, []) or []
        dealer_id = None
        first_inv = None
        if entries:
            first = entries[0]
            first_inv = int(first["invoices_id"] if isinstance(first, dict) else first)
            row = query_one("SELECT dealer_id FROM invoices WHERE invoices_id = ?", (first_inv,))
            if row:
                dealer_id = row["dealer_id"]
        cheque_row = query_one(
            "SELECT cheque_id FROM cheque WHERE cheque_no = ? AND user_bank_acc_id = ? ORDER BY cheque_id DESC LIMIT 1",
            (ch["cheque_no"], ch["user_bank_acc_id"]),
        )
        if cheque_row:
            sync_timetable_from_cheque(cheque_row["cheque_id"], dealer_id)


def save_analyst_report(markdown: str):
    return execute(
        "INSERT INTO analyst_reports (report_markdown) VALUES (?)",
        (markdown,),
    )


def get_latest_analyst_report():
    return query_one("SELECT * FROM analyst_reports ORDER BY report_id DESC LIMIT 1")


def get_analytics_metrics():
    liabilities = get_outstanding_liabilities()
    deposits = get_recent_deposits_total()
    cheques = query(
        """SELECT COUNT(*) AS cnt, COALESCE(SUM(amount_in_numerals), 0) AS total
           FROM cheque WHERE verification_status = 1"""
    )[0]
    verified_pending = query(
        """SELECT COUNT(*) AS cnt FROM invoices
           WHERE is_invoice_verified = 0 AND user_id = ?""",
        (Config.USER_ID,),
    )[0]["cnt"]
    return {
        "outstanding_liabilities_lkr": liabilities,
        "committed_cheques_count": cheques["cnt"],
        "committed_cheques_total_lkr": cheques["total"],
        "unverified_invoices": verified_pending,
        "weekly_deposits": deposits,
        "generated_at": datetime.now().isoformat(),
    }


def ensure_bundle_drafts_table():
    execute(
        """CREATE TABLE IF NOT EXISTS bundle_drafts (
            dealer_id INTEGER PRIMARY KEY,
            ceiling_lkr REAL NOT NULL,
            bundles_json TEXT NOT NULL,
            validation_issues_json TEXT,
            allow_exceed_ceiling INTEGER NOT NULL DEFAULT 0,
            chat_history_json TEXT,
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (dealer_id) REFERENCES dealers(dealer_id)
        )"""
    )


def save_bundle_draft(
    dealer_id: int,
    ceiling_lkr: float,
    bundles_slim: list,
    validation_issues: list,
    chat_history: list,
    allow_exceed_ceiling: bool = False,
):
    import json

    ensure_bundle_drafts_table()
    execute(
        """INSERT OR REPLACE INTO bundle_drafts
           (dealer_id, ceiling_lkr, bundles_json, validation_issues_json,
            allow_exceed_ceiling, chat_history_json, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
        (
            dealer_id,
            ceiling_lkr,
            json.dumps(bundles_slim),
            json.dumps(validation_issues or []),
            1 if allow_exceed_ceiling else 0,
            json.dumps(chat_history or []),
        ),
    )


def load_bundle_draft(dealer_id: int):
    ensure_bundle_drafts_table()
    return query_one("SELECT * FROM bundle_drafts WHERE dealer_id = ?", (dealer_id,))


def clear_bundle_draft(dealer_id: int):
    ensure_bundle_drafts_table()
    execute("DELETE FROM bundle_drafts WHERE dealer_id = ?", (dealer_id,))


def list_bank_cheque_templates():
    return query("SELECT * FROM bank_cheque_templates ORDER BY bank_name")


def get_bank_cheque_template(bank_code: str):
    return query_one("SELECT * FROM bank_cheque_templates WHERE bank_code = ?", (bank_code,))


def get_printer_settings(user_bank_acc_id: int | None, bank_code: str) -> dict:
    if user_bank_acc_id:
        row = query_one(
            """SELECT * FROM shop_printer_settings
               WHERE bank_code = ? AND is_active = 1 AND user_bank_acc_id = ?""",
            (bank_code, user_bank_acc_id),
        )
        if row:
            return dict(row)
    row = query_one(
        """SELECT * FROM shop_printer_settings
           WHERE bank_code = ? AND is_active = 1 AND user_bank_acc_id IS NULL""",
        (bank_code,),
    )
    if row:
        return dict(row)
    return {
        "offset_x_mm": 0.0,
        "offset_y_mm": 0.0,
        "feed_orientation": "VERTICAL",
    }


CITS_CHEQUE_LENGTH_MM = 177.8
CITS_CHEQUE_WIDTH_MM = 88.9


def validate_cheque_dimensions(length_mm: float, width_mm: float) -> str | None:
    """Validate user-facing length (long edge) and width (short edge) in mm."""
    try:
        length = float(length_mm)
        width = float(width_mm)
    except (TypeError, ValueError):
        return "flash_cheque_dimensions_invalid"
    if length <= 0 or width <= 0:
        return "flash_cheque_dimensions_invalid"
    if not (150.0 <= length <= 220.0):
        return "flash_cheque_length_out_of_range"
    if not (60.0 <= width <= 120.0):
        return "flash_cheque_width_out_of_range"
    return None


def get_account_cheque_setup(user_bank_acc_id: int | None, bank_name: str | None) -> dict:
    """Return form-friendly cheque dimensions (length = long edge, width = short edge)."""
    from core.cheque_utils import resolve_bank_code

    length_mm = CITS_CHEQUE_LENGTH_MM
    width_mm = CITS_CHEQUE_WIDTH_MM
    use_standard = True

    bank_code = resolve_bank_code(bank_name)
    if bank_code:
        template = get_bank_cheque_template(bank_code)
        if template:
            length_mm = float(template.get("cheque_width_mm") or CITS_CHEQUE_LENGTH_MM)
            width_mm = float(template.get("cheque_height_mm") or CITS_CHEQUE_WIDTH_MM)

    if user_bank_acc_id and bank_code:
        settings = get_printer_settings(user_bank_acc_id, bank_code)
        if settings.get("cheque_width_mm") is not None:
            length_mm = float(settings["cheque_width_mm"])
        if settings.get("cheque_height_mm") is not None:
            width_mm = float(settings["cheque_height_mm"])

    use_standard = (
        abs(length_mm - CITS_CHEQUE_LENGTH_MM) < 0.05
        and abs(width_mm - CITS_CHEQUE_WIDTH_MM) < 0.05
    )
    return {
        "length_mm": length_mm,
        "width_mm": width_mm,
        "use_standard_cheque_size": use_standard,
    }


def validate_printer_offsets(offset_x_mm: float, offset_y_mm: float) -> str | None:
    try:
        x = float(offset_x_mm)
        y = float(offset_y_mm)
    except (TypeError, ValueError):
        return "flash_printer_offsets_invalid"
    if not (-20.0 <= x <= 20.0) or not (-20.0 <= y <= 20.0):
        return "flash_printer_offsets_out_of_range"
    return None


def get_account_printer_calibration(user_bank_acc_id: int | None, bank_name: str | None) -> dict:
    from core.cheque_utils import resolve_bank_code

    calibration = {
        "offset_x_mm": 0.0,
        "offset_y_mm": 0.0,
        "feed_orientation": "VERTICAL",
        "bank_code": resolve_bank_code(bank_name),
    }
    bank_code = calibration["bank_code"]
    if user_bank_acc_id and bank_code:
        settings = get_printer_settings(user_bank_acc_id, bank_code)
        calibration["offset_x_mm"] = float(settings.get("offset_x_mm") or 0.0)
        calibration["offset_y_mm"] = float(settings.get("offset_y_mm") or 0.0)
        calibration["feed_orientation"] = settings.get("feed_orientation") or "VERTICAL"
    return calibration


def save_account_printer_calibration(
    user_bank_acc_id: int,
    bank_code: str,
    offset_x_mm: float,
    offset_y_mm: float,
    feed_orientation: str = "VERTICAL",
) -> str | None:
    err = validate_printer_offsets(offset_x_mm, offset_y_mm)
    if err:
        return err
    if not get_bank_cheque_template(bank_code):
        return "flash_bank_name_required"
    existing = get_printer_settings(user_bank_acc_id, bank_code)
    upsert_printer_settings(
        bank_code,
        user_bank_acc_id=user_bank_acc_id,
        offset_x_mm=float(offset_x_mm),
        offset_y_mm=float(offset_y_mm),
        feed_orientation=feed_orientation,
        cheque_width_mm=existing.get("cheque_width_mm"),
        cheque_height_mm=existing.get("cheque_height_mm"),
    )
    return None


def bank_name_for_code(bank_code: str | None) -> str | None:
    if not bank_code:
        return None
    template = get_bank_cheque_template(bank_code.strip())
    return template["bank_name"] if template else None


def save_account_cheque_setup(
    user_bank_acc_id: int,
    bank_name: str,
    length_mm: float,
    width_mm: float,
    bank_code: str | None = None,
) -> str | None:
    """Persist per-account cheque leaf dimensions. Returns flash key on validation error."""
    from core.cheque_utils import resolve_bank_code

    err = validate_cheque_dimensions(length_mm, width_mm)
    if err:
        return err

    if not bank_code:
        bank_code = resolve_bank_code(bank_name)
    if not bank_code:
        return None

    existing = get_printer_settings(user_bank_acc_id, bank_code)
    upsert_printer_settings(
        bank_code,
        user_bank_acc_id=user_bank_acc_id,
        offset_x_mm=float(existing.get("offset_x_mm") or 0.0),
        offset_y_mm=float(existing.get("offset_y_mm") or 0.0),
        feed_orientation=existing.get("feed_orientation") or "VERTICAL",
        cheque_width_mm=float(length_mm),
        cheque_height_mm=float(width_mm),
    )
    return None


def upsert_printer_settings(
    bank_code: str,
    *,
    user_bank_acc_id: int | None = None,
    offset_x_mm: float = 0.0,
    offset_y_mm: float = 0.0,
    feed_orientation: str = "VERTICAL",
    cheque_width_mm: float | None = None,
    cheque_height_mm: float | None = None,
    is_active: bool = True,
):
    existing = query_one(
        """SELECT id FROM shop_printer_settings
           WHERE bank_code = ? AND user_bank_acc_id IS ?""",
        (bank_code, user_bank_acc_id),
    )
    orientation = feed_orientation.upper()
    if orientation not in ("VERTICAL", "HORIZONTAL"):
        orientation = "VERTICAL"
    if existing:
        execute(
            """UPDATE shop_printer_settings
               SET offset_x_mm = ?, offset_y_mm = ?, feed_orientation = ?, is_active = ?,
                   cheque_width_mm = COALESCE(?, cheque_width_mm),
                   cheque_height_mm = COALESCE(?, cheque_height_mm)
               WHERE id = ?""",
            (
                offset_x_mm,
                offset_y_mm,
                orientation,
                1 if is_active else 0,
                cheque_width_mm,
                cheque_height_mm,
                existing["id"],
            ),
        )
        return existing["id"]
    return execute(
        """INSERT INTO shop_printer_settings
           (user_bank_acc_id, bank_code, offset_x_mm, offset_y_mm, feed_orientation,
            cheque_width_mm, cheque_height_mm, is_active)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            user_bank_acc_id,
            bank_code,
            offset_x_mm,
            offset_y_mm,
            orientation,
            cheque_width_mm,
            cheque_height_mm,
            1 if is_active else 0,
        ),
    )


# --- WhatsApp local bridge: whitelist, inbound idempotency, unprocessed media ---


def ensure_whatsapp_allowed_senders_schema():
    execute(
        """CREATE TABLE IF NOT EXISTS whatsapp_allowed_senders (
            sender_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            phone_e164 TEXT NOT NULL,
            display_name TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(user_id, phone_e164),
            FOREIGN KEY (user_id) REFERENCES user(user_id)
        )"""
    )
    execute(
        "CREATE INDEX IF NOT EXISTS idx_whatsapp_allowed_senders_user ON whatsapp_allowed_senders(user_id)"
    )


def ensure_inbound_messages_schema():
    execute(
        """CREATE TABLE IF NOT EXISTS inbound_messages (
            inbound_id INTEGER PRIMARY KEY AUTOINCREMENT,
            wa_msg_id TEXT NOT NULL UNIQUE,
            sender_phone TEXT,
            received_at TEXT,
            location_path TEXT,
            pipeline_status TEXT NOT NULL DEFAULT 'processing',
            invoice_id INTEGER,
            error_message TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (invoice_id) REFERENCES invoices(invoices_id)
        )"""
    )
    execute(
        "CREATE INDEX IF NOT EXISTS idx_inbound_messages_status ON inbound_messages(pipeline_status)"
    )


def ensure_unprocessed_media_schema():
    execute(
        """CREATE TABLE IF NOT EXISTS unprocessed_media_log (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            wa_msg_id TEXT,
            sender_phone TEXT,
            location_path TEXT NOT NULL,
            received_at TEXT,
            reject_reason TEXT NOT NULL DEFAULT 'not_invoice',
            classifier_json TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES user(user_id)
        )"""
    )
    execute("CREATE INDEX IF NOT EXISTS idx_unprocessed_media_user ON unprocessed_media_log(user_id)")
    execute(
        "CREATE INDEX IF NOT EXISTS idx_unprocessed_media_status ON unprocessed_media_log(status)"
    )


def _ensure_whatsapp_bridge_schemas():
    ensure_whatsapp_allowed_senders_schema()
    ensure_inbound_messages_schema()
    ensure_unprocessed_media_schema()


def list_allowed_senders():
    _ensure_whatsapp_bridge_schemas()
    return query(
        """SELECT * FROM whatsapp_allowed_senders
           WHERE user_id = ?
           ORDER BY display_name, phone_e164""",
        (Config.USER_ID,),
    )


def get_allowed_sender(sender_id: int):
    _ensure_whatsapp_bridge_schemas()
    return query_one(
        "SELECT * FROM whatsapp_allowed_senders WHERE sender_id = ? AND user_id = ?",
        (sender_id, Config.USER_ID),
    )


def add_allowed_sender(phone_e164: str, display_name: str | None = None) -> int:
    from core.whatsapp_utils import normalize_whatsapp_phone

    _ensure_whatsapp_bridge_schemas()
    phone = normalize_whatsapp_phone(phone_e164)
    with transaction() as conn:
        cursor = conn.execute(
            """INSERT INTO whatsapp_allowed_senders (user_id, phone_e164, display_name)
               VALUES (?, ?, ?)""",
            (Config.USER_ID, phone, (display_name or "").strip() or None),
        )
        return cursor.lastrowid


def update_allowed_sender(
    sender_id: int,
    *,
    display_name: str | None = None,
    is_active: bool | None = None,
):
    _ensure_whatsapp_bridge_schemas()
    row = get_allowed_sender(sender_id)
    if not row:
        return
    name = row.get("display_name") if display_name is None else display_name
    active = row.get("is_active") if is_active is None else (1 if is_active else 0)
    execute(
        """UPDATE whatsapp_allowed_senders
           SET display_name = ?, is_active = ?, updated_at = datetime('now')
           WHERE sender_id = ? AND user_id = ?""",
        (name, active, sender_id, Config.USER_ID),
    )


def remove_allowed_sender(sender_id: int):
    execute(
        "DELETE FROM whatsapp_allowed_senders WHERE sender_id = ? AND user_id = ?",
        (sender_id, Config.USER_ID),
    )


def is_sender_allowed(phone: str) -> bool:
    from core.whatsapp_utils import normalize_whatsapp_phone

    _ensure_whatsapp_bridge_schemas()
    active = query(
        """SELECT phone_e164 FROM whatsapp_allowed_senders
           WHERE user_id = ? AND is_active = 1""",
        (Config.USER_ID,),
    )
    if not active:
        return False
    normalized = normalize_whatsapp_phone(phone)
    allowed = {normalize_whatsapp_phone(r["phone_e164"]) for r in active}
    return normalized in allowed


def get_inbound_message(wa_msg_id: str):
    _ensure_whatsapp_bridge_schemas()
    return query_one("SELECT * FROM inbound_messages WHERE wa_msg_id = ?", (wa_msg_id,))


def begin_inbound_processing(
    wa_msg_id: str,
    *,
    sender_phone: str | None,
    received_at: str | None,
    location_path: str | None,
) -> tuple[str, dict | None]:
    """Returns ('new', None) or ('duplicate', existing_row)."""
    _ensure_whatsapp_bridge_schemas()
    existing = get_inbound_message(wa_msg_id)
    if existing:
        return "duplicate", existing
    with transaction() as conn:
        conn.execute(
            """INSERT INTO inbound_messages
               (wa_msg_id, sender_phone, received_at, location_path, pipeline_status)
               VALUES (?, ?, ?, ?, 'processing')""",
            (wa_msg_id, sender_phone, received_at, location_path),
        )
    return "new", None


def finalize_inbound(
    wa_msg_id: str,
    *,
    status: str,
    invoice_id: int | None = None,
    location_path: str | None = None,
    error_message: str | None = None,
):
    _ensure_whatsapp_bridge_schemas()
    execute(
        """UPDATE inbound_messages
           SET pipeline_status = ?, invoice_id = COALESCE(?, invoice_id),
               location_path = COALESCE(?, location_path),
               error_message = ?
           WHERE wa_msg_id = ?""",
        (status, invoice_id, location_path, error_message, wa_msg_id),
    )


def save_unprocessed_media_log(
    *,
    wa_msg_id: str | None,
    sender_phone: str | None,
    location_path: str,
    received_at: str | None,
    reject_reason: str,
    classifier_json: str | None = None,
) -> int:
    _ensure_whatsapp_bridge_schemas()
    with transaction() as conn:
        cursor = conn.execute(
            """INSERT INTO unprocessed_media_log
               (user_id, wa_msg_id, sender_phone, location_path, received_at,
                reject_reason, classifier_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                Config.USER_ID,
                wa_msg_id,
                sender_phone,
                location_path,
                received_at,
                reject_reason,
                classifier_json,
            ),
        )
        return cursor.lastrowid


def get_unprocessed_media_pending():
    _ensure_whatsapp_bridge_schemas()
    return query(
        """SELECT * FROM unprocessed_media_log
           WHERE user_id = ? AND status = 'pending'
           ORDER BY created_at DESC""",
        (Config.USER_ID,),
    )


def get_unprocessed_media_item(log_id: int):
    _ensure_whatsapp_bridge_schemas()
    return query_one(
        "SELECT * FROM unprocessed_media_log WHERE log_id = ? AND user_id = ?",
        (log_id, Config.USER_ID),
    )


def dismiss_unprocessed_media(log_id: int):
    execute(
        """UPDATE unprocessed_media_log SET status = 'dismissed'
           WHERE log_id = ? AND user_id = ?""",
        (log_id, Config.USER_ID),
    )

