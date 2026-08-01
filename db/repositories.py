import json
from datetime import datetime

from config import Config
from core.ingestion_helpers import PENDING_SUPPLIER_NAME
from db.connection import execute, query, query_one, transaction


def get_user():
    return query_one("SELECT * FROM user WHERE user_id = ?", (Config.USER_ID,))


def get_setting(key: str, default: str = "") -> str:
    row = query_one("SELECT setting_value FROM app_settings WHERE setting_key = ?", (key,))
    return row["setting_value"] if row else default


def get_bank_accounts():
    return query(
        "SELECT * FROM user_bank_account WHERE user_id = ? ORDER BY user_bank_acc_id",
        (Config.USER_ID,),
    )


def get_bank_account(acc_id: int):
    return query_one(
        "SELECT * FROM user_bank_account WHERE user_bank_acc_id = ? AND user_id = ?",
        (acc_id, Config.USER_ID),
    )


def update_balance(acc_id: int, balance: float):
    execute(
        "UPDATE user_bank_account SET available_balance = ? WHERE user_bank_acc_id = ?",
        (balance, acc_id),
    )


def get_dealers():
    return query("SELECT * FROM dealers ORDER BY dealer_name")


def find_dealer_by_name(name: str):
    dealers = get_dealers()
    normalized = name.strip().lower()
    for d in dealers:
        if d["dealer_name"].strip().lower() == PENDING_SUPPLIER_NAME.lower():
            continue
        if d["dealer_name"].strip().lower() == normalized:
            return d
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
                   {display_name} AS display_dealer_name
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


def get_committed_cheque_bundles(dealer_id: int):
    cheques = query(
        """SELECT DISTINCT c.* FROM cheque c
           JOIN invoices i ON i.cheque_id = c.cheque_id
           WHERE i.dealer_id = ? AND i.user_id = ?
           ORDER BY c.cheque_date DESC""",
        (dealer_id, Config.USER_ID),
    )
    result = []
    for ch in cheques:
        invoices = query(
            """SELECT invoice_no, total_amount, invoiced_date, credit_period_days
               FROM invoices WHERE cheque_id = ? ORDER BY invoice_no""",
            (ch["cheque_id"],),
        )
        result.append({**ch, "invoices": invoices})
    return result


def update_verified_invoice(invoice_id: int, data: dict, items: list, dealer_id: int):
    with transaction() as conn:
        conn.execute(
            """UPDATE invoices SET dealer_id = ?, invoice_no = ?, invoiced_date = ?,
               credit_period_days = ?, total_amount = ?, is_invoice_verified = 1,
               pending_dealer_json = NULL
               WHERE invoices_id = ? AND user_id = ?""",
            (
                dealer_id,
                data["invoice_no"],
                data["invoiced_date"],
                int(data["credit_period_days"]),
                float(data["total_amount"]),
                invoice_id,
                Config.USER_ID,
            ),
        )
        conn.execute("DELETE FROM item WHERE invoices_id = ?", (invoice_id,))
        for item in items:
            conn.execute(
                """INSERT INTO item (invoices_id, item_code, item_name, item_qty, item_price, item_discount)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    invoice_id,
                    item["item_code"],
                    item["item_name"],
                    int(item["item_qty"]),
                    float(item["item_price"]),
                    float(item.get("item_discount", 0)),
                ),
            )


def get_invoice(invoice_id: int):
    return query_one(
        "SELECT i.*, d.dealer_name FROM invoices i JOIN dealers d ON d.dealer_id = i.dealer_id WHERE i.invoices_id = ?",
        (invoice_id,),
    )


def get_invoice_items(invoice_id: int):
    return query("SELECT * FROM item WHERE invoices_id = ?", (invoice_id,))


def find_invoice_by_no_and_dealer(invoice_no: str, dealer_id: int):
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


def save_verified_invoice(data: dict, items: list, dealer_id: int) -> int:
    with transaction() as conn:
        cursor = conn.execute(
            """INSERT INTO invoices (user_id, dealer_id, invoice_no, invoiced_date,
               credit_period_days, total_amount, location_path, is_invoice_verified)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                Config.USER_ID,
                dealer_id,
                data["invoice_no"],
                data["invoiced_date"],
                int(data["credit_period_days"]),
                float(data["total_amount"]),
                data.get("location_path"),
            ),
        )
        invoice_id = cursor.lastrowid
        for item in items:
            conn.execute(
                """INSERT INTO item (invoices_id, item_code, item_name, item_qty, item_price, item_discount)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    invoice_id,
                    item["item_code"],
                    item["item_name"],
                    int(item["item_qty"]),
                    float(item["item_price"]),
                    float(item.get("item_discount", 0)),
                ),
            )
    return invoice_id


def save_pending_invoice(
    data: dict,
    items: list,
    dealer_id: int,
    pending_dealer_json: str | None = None,
) -> int:
    with transaction() as conn:
        cursor = conn.execute(
            """INSERT INTO invoices (user_id, dealer_id, invoice_no, invoiced_date,
               credit_period_days, total_amount, location_path, pending_dealer_json,
               is_invoice_verified)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)""",
            (
                Config.USER_ID,
                dealer_id,
                data["invoice_no"],
                data["invoiced_date"],
                int(data["credit_period_days"]),
                float(data["total_amount"]),
                data.get("location_path"),
                pending_dealer_json,
            ),
        )
        invoice_id = cursor.lastrowid
        for item in items:
            conn.execute(
                """INSERT INTO item (invoices_id, item_code, item_name, item_qty, item_price, item_discount)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    invoice_id,
                    item["item_code"],
                    item["item_name"],
                    int(item["item_qty"]),
                    float(item["item_price"]),
                    float(item.get("item_discount", 0)),
                ),
            )
    return invoice_id


def update_invoice_dealer_id(invoice_id: int, dealer_id: int):
    execute(
        "UPDATE invoices SET dealer_id = ? WHERE invoices_id = ? AND user_id = ?",
        (dealer_id, invoice_id, Config.USER_ID),
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
        dates["days_gained_by_holiday_lag"],
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
    return query(
        """SELECT * FROM cheque WHERE user_bank_acc_id = ?
           AND verification_status = 1 ORDER BY predicted_clearance_date""",
        (account_id,),
    )


def get_planned_deposits(account_id: int):
    return query(
        "SELECT * FROM planned_deposits WHERE user_bank_acc_id = ? AND status = 'planned' ORDER BY planned_date",
        (account_id,),
    )


def get_bank_deposits(account_id: int):
    return query(
        "SELECT * FROM bank_deposits WHERE user_bank_acc_id = ? ORDER BY deposit_date",
        (account_id,),
    )


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
    return query(
        """SELECT strftime('%Y-W%W', deposit_date) AS week, SUM(amount) AS total
           FROM bank_deposits GROUP BY week ORDER BY week DESC LIMIT ?""",
        (weeks,),
    )


def save_cheques(cheques: list, invoice_map: dict):
    """cheques: list of dicts with bank_acc_id, cheque_no, cheque_date, amount, words, clearance
    invoice_map: {cheque_index: [invoice_ids]}
    """
    with transaction() as conn:
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
            inv_ids = invoice_map.get(idx, [])
            dealer_id = None
            for inv_id in inv_ids:
                conn.execute("UPDATE invoices SET cheque_id = ? WHERE invoices_id = ?", (cheque_id, inv_id))
                if dealer_id is None:
                    row = conn.execute(
                        "SELECT dealer_id FROM invoices WHERE invoices_id = ?", (inv_id,)
                    ).fetchone()
                    if row:
                        dealer_id = row[0]
    for idx, ch in enumerate(cheques):
        inv_ids = invoice_map.get(idx, [])
        dealer_id = None
        if inv_ids:
            row = query_one("SELECT dealer_id FROM invoices WHERE invoices_id = ?", (inv_ids[0],))
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
