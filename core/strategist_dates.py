"""Cheque date helpers for Agent 3 float maximization within credit terms."""

from __future__ import annotations

from datetime import date, timedelta

from core.bundling import invoice_due_date
from core.dates import add_business_days, format_date
from core.liquidity_engine import apply_liquidity_dates, is_interbank
from db import repositories as repo


def latest_permissible_cheque_date(invoice: dict, dealer: dict | None, holidays: set) -> date:
    """Latest stated cheque date still within distributor credit + casual buffer."""
    due = invoice_due_date(invoice)
    impossible = (dealer or {}).get("impossible_days") or ""
    casual = int((dealer or {}).get("casual_days") or 0)
    return add_business_days(due, casual, holidays, impossible)


def earliest_cheque_date(holidays: set, impossible: str = "") -> date:
    today = date.today()
    return add_business_days(today, 1, holidays, impossible)


def suggest_float_cheque_date(
    invoice: dict,
    dealer: dict | None,
    holidays: set,
    *,
    merchant_bank_name: str,
    dealer_bank_name: str,
    prefer_interbank: bool = True,
) -> dict:
    """Pick a stated date in [earliest, latest] that maximizes days_gained_total."""
    impossible = (dealer or {}).get("impossible_days") or ""
    earliest = earliest_cheque_date(holidays, impossible)
    latest = latest_permissible_cheque_date(invoice, dealer, holidays)
    if latest < earliest:
        latest = earliest

    interbank = prefer_interbank and is_interbank(merchant_bank_name, dealer_bank_name)
    best_date = earliest
    best_gain = -1
    best_meta: dict = {}

    cursor = earliest
    while cursor <= latest:
        date_str = format_date(cursor)
        meta = apply_liquidity_dates(date_str, holidays, is_interbank=interbank)
        gain = int(meta.get("days_gained_total") or 0)
        if gain > best_gain:
            best_gain = gain
            best_date = cursor
            best_meta = meta
        cursor += timedelta(days=1)

    return {
        "proposed_date": format_date(best_date),
        "days_gained_total": best_gain,
        "is_interbank": interbank,
        "earliest_permissible": format_date(earliest),
        "latest_permissible": format_date(latest),
        **best_meta,
    }


def suggest_float_date_for_bundle(
    bundle: dict,
    dealer_id: int,
    *,
    prefer_interbank: bool = True,
) -> dict:
    """Optimize stated cheque date for one bundle using its invoices' due window."""
    dealer = repo.get_dealer(dealer_id) or {}
    dealer_bank = repo.get_dealer_preferred_bank(dealer_id)
    dealer_bank_name = (dealer_bank or {}).get("bank_name") or ""

    acc_id = bundle.get("paying_account_id") or repo.paying_account_id_for_dealer(dealer_id)
    acc = repo.get_bank_account(int(acc_id)) if acc_id else None
    merchant_bank = (acc or {}).get("bank_name") or ""

    invoices = bundle.get("invoices") or []
    if not invoices:
        holidays = repo.get_holidays()
        today_str = format_date(earliest_cheque_date(holidays, dealer.get("impossible_days") or ""))
        interbank = prefer_interbank and is_interbank(merchant_bank, dealer_bank_name)
        meta = apply_liquidity_dates(today_str, holidays, is_interbank=interbank)
        return {"proposed_date": today_str, **meta}

    holidays = repo.get_holidays()
    earliest = max(
        earliest_cheque_date(holidays, dealer.get("impossible_days") or "") for _ in [0]
    )
    latest = min(latest_permissible_cheque_date(inv, dealer, holidays) for inv in invoices)
    if latest < earliest:
        latest = earliest

    interbank = prefer_interbank and is_interbank(merchant_bank, dealer_bank_name)
    best_date = earliest
    best_gain = -1
    best_meta: dict = {}

    cursor = earliest
    while cursor <= latest:
        date_str = format_date(cursor)
        meta = apply_liquidity_dates(date_str, holidays, is_interbank=interbank)
        gain = int(meta.get("days_gained_total") or 0)
        if gain > best_gain:
            best_gain = gain
            best_date = cursor
            best_meta = meta
        cursor += timedelta(days=1)

    return {
        "proposed_date": format_date(best_date),
        "days_gained_total": best_gain,
        "is_interbank": interbank,
        "earliest_permissible": format_date(earliest),
        "latest_permissible": format_date(latest),
        **best_meta,
    }


def interbank_account_options(dealer_id: int) -> list[dict]:
    """Shop accounts with clearing type vs distributor preferred bank."""
    dealer_bank = repo.get_dealer_preferred_bank(dealer_id)
    payee = (dealer_bank or {}).get("bank_name") or ""
    options = []
    for acc in repo.get_bank_accounts():
        bank = (acc.get("bank_name") or "").strip()
        if not payee or not bank:
            clearing = "UNKNOWN"
        elif bank.lower() == payee.lower():
            clearing = "INTRABANK"
        else:
            clearing = "INTERBANK"
        balance = float(acc.get("available_balance") or 0) + float(acc.get("overdraft_limit") or 0)
        options.append(
            {
                "account_id": int(acc["user_bank_acc_id"]),
                "bank_name": bank,
                "current_balance": balance,
                "clearing_type": clearing,
                "payee_bank": payee,
            }
        )
    return options
