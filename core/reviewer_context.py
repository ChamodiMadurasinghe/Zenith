"""Full context payload for the SME liquidity reviewer (Agent 2)."""

from datetime import date, timedelta

from core.bundling import invoice_due_date
from core.chat_context import BUNDLING_ALGORITHM, _slim_bundle, _slim_invoice
from core.dates import parse_date
from db import repositories as repo

_HOLIDAY_WINDOW_DAYS = 7


def _days_until(date_str: str | None, today: date) -> int | None:
    if not date_str:
        return None
    try:
        return (parse_date(date_str) - today).days
    except (TypeError, ValueError):
        return None


def _liquidity_bundle(b: dict, today: date) -> dict:
    fund_by = b.get("target_funding_date") or b.get("predicted_clearance_date")
    return {
        "group": b.get("group"),
        "cheque_date": b.get("cheque_date"),
        "true_settlement_date": b.get("true_settlement_date"),
        "target_funding_date": fund_by,
        "predicted_clearance_date": b.get("predicted_clearance_date"),
        "days_gained_by_holiday_lag": b.get("days_gained_by_holiday_lag", 0),
        "days_gained_total": b.get(
            "days_gained_total",
            b.get("days_gained_by_holiday_lag", 0),
        ),
        "days_until_funding_from_today": _days_until(fund_by, today),
        "total_lkr": b.get("total_lkr"),
        "is_interbank": b.get("is_interbank"),
        "invoices": [
            {
                "invoices_id": inv.get("invoices_id"),
                "invoice_no": inv.get("invoice_no"),
                "total_amount": float(inv.get("total_amount") or 0),
                "invoiced_date": inv.get("invoiced_date"),
                "credit_period_days": inv.get("credit_period_days"),
                "due_date": invoice_due_date(inv).isoformat(),
            }
            for inv in b.get("invoices", [])
        ],
    }


def _holidays_near_cheques(bundles: list) -> list[dict]:
    if not bundles:
        return []

    group_windows: dict[int, tuple[date, date]] = {}
    for b in bundles:
        group = b.get("group")
        if group is None:
            continue
        dates_to_span = []
        for key in ("cheque_date", "true_settlement_date", "target_funding_date", "predicted_clearance_date"):
            val = b.get(key)
            if val:
                try:
                    dates_to_span.append(parse_date(val))
                except (TypeError, ValueError):
                    pass
        if not dates_to_span:
            continue
        start = min(dates_to_span) - timedelta(days=_HOLIDAY_WINDOW_DAYS)
        end = max(dates_to_span) + timedelta(days=_HOLIDAY_WINDOW_DAYS)
        if group in group_windows:
            prev_start, prev_end = group_windows[group]
            group_windows[group] = (min(prev_start, start), max(prev_end, end))
        else:
            group_windows[group] = (start, end)

    if not group_windows:
        return []

    global_start = min(w[0] for w in group_windows.values())
    global_end = max(w[1] for w in group_windows.values())
    holidays = repo.get_holidays_in_range(global_start.isoformat(), global_end.isoformat())

    result = []
    for h in holidays:
        try:
            hd = parse_date(h["date"])
        except (TypeError, ValueError):
            continue
        near_groups = []
        for group, (start, end) in group_windows.items():
            if start <= hd <= end:
                near_groups.append(group)
        if near_groups:
            result.append(
                {
                    "date": h["date"],
                    "description": h.get("description") or "",
                    "near_cheque_groups": sorted(near_groups),
                }
            )
    return result


def build_reviewer_context(
    dealer_id: int,
    bundles: list,
    ceiling_lkr: float,
    validation_issues: list | None = None,
    trigger: str = "compute",
) -> dict:
    dealer = repo.get_dealer(dealer_id) or {}
    bank = repo.get_dealer_preferred_bank(dealer_id)
    summary = repo.get_dealer_invoice_summary(dealer_id)
    ready = repo.get_verified_unassigned_invoices(dealer_id)
    pending = repo.get_pending_verification_invoices(dealer_id)
    committed = repo.get_committed_cheque_bundles(dealer_id)

    merchant_acc_id = repo.paying_account_id_for_dealer(dealer_id)
    merchant_acc = repo.get_bank_account(merchant_acc_id)
    today = date.today()

    liquidity_bundles = [_liquidity_bundle(b, today) for b in bundles]
    holidays_near = _holidays_near_cheques(bundles)

    total_at_risk = sum(float(b.get("total_lkr") or 0) for b in bundles)
    max_funding_days = max(
        (lb["days_until_funding_from_today"] for lb in liquidity_bundles if lb["days_until_funding_from_today"] is not None),
        default=0,
    )
    total_holiday_lag = sum(int(lb.get("days_gained_by_holiday_lag") or 0) for lb in liquidity_bundles)
    total_float_days = sum(
        int(lb.get("days_gained_total") if lb.get("days_gained_total") is not None else lb.get("days_gained_by_holiday_lag") or 0)
        for lb in liquidity_bundles
    )

    return {
        "trigger": trigger,
        "today": today.isoformat(),
        "dealer": {
            "dealer_id": dealer.get("dealer_id"),
            "dealer_name": dealer.get("dealer_name"),
            "dealer_email": dealer.get("dealer_email"),
            "dealer_telno": dealer.get("dealer_telno"),
            "dealer_address": dealer.get("dealer_address"),
            "dealer_strictness": dealer.get("dealer_strictness"),
            "casual_days": dealer.get("casual_days"),
            "impossible_days": dealer.get("impossible_days"),
        },
        "dealer_bank": {
            "bank_name": bank.get("bank_name") if bank else None,
            "branch_name": bank.get("branch_name") if bank else None,
            "account_name": bank.get("account_name") if bank else None,
        },
        "merchant_bank": {
            "bank_name": merchant_acc.get("bank_name") if merchant_acc else None,
            "available_balance_lkr": float(merchant_acc.get("available_balance") or 0) if merchant_acc else None,
            "overdraft_limit_lkr": float(merchant_acc.get("overdraft_limit") or 0) if merchant_acc else None,
            "usable_funds_lkr": (
                float(merchant_acc.get("available_balance") or 0)
                + float(merchant_acc.get("overdraft_limit") or 0)
            )
            if merchant_acc
            else None,
        },
        "ceiling_lkr": ceiling_lkr,
        "invoice_summary": summary,
        "ready_invoices": [_slim_invoice(i) for i in ready],
        "pending_invoices": [_slim_invoice(i) for i in pending],
        "committed_cheques": [
            {
                "cheque_no": ch.get("cheque_no"),
                "cheque_date": ch.get("cheque_date"),
                "amount_in_numerals": float(ch.get("amount_in_numerals") or 0),
                "predicted_clearance_date": ch.get("predicted_clearance_date"),
                "invoices": [
                    {
                        "invoice_no": inv.get("invoice_no"),
                        "total_amount": float(inv.get("total_amount") or 0),
                    }
                    for inv in ch.get("invoices", [])
                ],
            }
            for ch in committed
        ],
        "current_bundles": [_slim_bundle(b) for b in bundles],
        "liquidity_bundles": liquidity_bundles,
        "liquidity_summary": {
            "total_lkr_in_proposal": total_at_risk,
            "max_days_until_funding": max_funding_days,
            "total_days_gained_by_holiday_lag": total_holiday_lag,
            "total_days_gained": total_float_days,
            "num_cheques": len(bundles),
        },
        "holidays_near_cheques": holidays_near,
        "validation_issues": validation_issues or [],
        "bundling_algorithm": BUNDLING_ALGORITHM,
    }
