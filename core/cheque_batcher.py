"""Agent-callable cheque batch tool (ported from Zenith-1/main/cheque_batcher.py).

Loads invoices, rolls settlement past CBSL holidays, and audits daily casual-limit exposure
against deposit_timetable so bundling agents can self-correct.
"""

from __future__ import annotations

from datetime import timedelta

from config import Config
from core.dates import format_date, parse_date
from core.liquidity_engine import apply_liquidity_dates, is_interbank, true_settlement_date
from db import repositories as repo
from db.connection import query_one


def _default_account_id() -> int:
    return int(repo.get_setting("default_bank_acc_id", "1"))


def _merchant_bank_name(account_id: int) -> str:
    acc = repo.get_bank_account(account_id)
    return acc["bank_name"] if acc else ""


def day_exposure_for_settlement(
    settlement_date: str,
    account_id: int | None = None,
) -> float:
    """Sum pending timetable amounts already scheduled for a settlement day."""
    account_id = account_id or _default_account_id()
    row = query_one(
        """SELECT COALESCE(SUM(total_amount), 0) AS total
           FROM deposit_timetable
           WHERE user_bank_acc_id = ?
             AND status NOT IN ('cleared', 'cancelled', 'Cancelled')
             AND COALESCE(true_settlement_date, stated_date) = ?""",
        (account_id, settlement_date),
    )
    return float(row["total"] if row else 0)


def evaluate_settlement(
    *,
    amount: float,
    original_date_str: str,
    supplier_name: str = "",
    dealer_id: int | None = None,
    casual_limit: float | None = None,
    account_id: int | None = None,
) -> dict:
    """Roll one cheque date past holidays and audit casual daily limit exposure."""
    account_id = account_id or _default_account_id()
    casual_limit = float(
        casual_limit if casual_limit is not None else Config.CASUAL_DAILY_LIMIT_LKR
    )
    holidays = repo.get_holidays()
    original = parse_date(original_date_str)
    settlement = true_settlement_date(original, holidays)
    settlement_str = format_date(settlement)
    days_gained = (settlement - original).days

    dealer_bank = repo.get_dealer_preferred_bank(dealer_id) if dealer_id else None
    interbank = is_interbank(
        _merchant_bank_name(account_id),
        dealer_bank["bank_name"] if dealer_bank else "",
    )
    liquidity = apply_liquidity_dates(
        original_date_str, holidays, is_interbank=interbank
    )

    existing = day_exposure_for_settlement(settlement_str, account_id)
    total_predicted = existing + float(amount)

    if total_predicted > casual_limit:
        verdict = "LIMIT_BREACH_WARNING"
        notes = (
            f"Warning: Adding LKR {amount:,.2f} pushes total allocation to "
            f"LKR {total_predicted:,.2f}, which breaches your casual cap of "
            f"LKR {casual_limit:,.2f}."
        )
    else:
        verdict = "CLEAR_TO_BATCH"
        notes = (
            f"Success: Scheduled smoothly. Gained {days_gained} extra days of "
            "interest-free float holding time."
        )

    return {
        "supplier": supplier_name,
        "dealer_id": dealer_id,
        "original_date": original_date_str,
        "calculated_settlement_date": settlement_str,
        "true_settlement_date": liquidity["true_settlement_date"],
        "target_funding_date": liquidity["target_funding_date"],
        "days_gained": days_gained,
        "is_interbank": interbank,
        "invoice_amount": float(amount),
        "existing_day_exposure": existing,
        "total_day_exposure": total_predicted,
        "casual_limit": casual_limit,
        "verdict": verdict,
        "notes": notes,
    }


def calculate_optimal_cheque_batch(
    invoice_id_list: list | None = None,
    *,
    invoice_amount: float | None = None,
    original_date_str: str | None = None,
    supplier_name: str = "",
    casual_limit: float | None = None,
    account_id: int | None = None,
) -> dict | list[dict]:
    """Zenith-1-compatible entry point for Agent 2 / Agent 3 evaluation loops.

    Call styles:
      - invoice IDs: calculate_optimal_cheque_batch([1, 2, 3])
      - single sim: calculate_optimal_cheque_batch(
            invoice_amount=450000, original_date_str="2026-04-11",
            supplier_name="Keells Wholesale")
    """
    if invoice_id_list is not None:
        results = []
        for invoice_id in invoice_id_list:
            inv = query_one(
                "SELECT * FROM invoices WHERE invoices_id = ?",
                (int(invoice_id),),
            )
            if inv is None:
                results.append(
                    {
                        "invoice_id": invoice_id,
                        "verdict": "NOT_FOUND",
                        "notes": f"Invoice ID {invoice_id} not found. Skipping.",
                    }
                )
                continue
            dealer = repo.get_dealer(inv["dealer_id"]) or {}
            due = parse_date(inv["invoiced_date"]) + timedelta(
                days=int(inv["credit_period_days"] or 0)
            )
            eval_row = evaluate_settlement(
                amount=float(inv["total_amount"]),
                original_date_str=format_date(due),
                supplier_name=dealer.get("dealer_name") or supplier_name,
                dealer_id=inv["dealer_id"],
                casual_limit=casual_limit,
                account_id=account_id,
            )
            eval_row["invoice_id"] = inv["invoices_id"]
            eval_row["invoice_no"] = inv.get("invoice_no")
            results.append(eval_row)
        return results

    if invoice_amount is None or not original_date_str:
        raise ValueError(
            "Provide invoice_id_list, or both invoice_amount and original_date_str."
        )
    return evaluate_settlement(
        amount=float(invoice_amount),
        original_date_str=original_date_str,
        supplier_name=supplier_name,
        casual_limit=casual_limit,
        account_id=account_id,
    )


def audit_bundle_day_limits(
    bundles: list,
    *,
    casual_limit: float | None = None,
    account_id: int | None = None,
) -> list[dict]:
    """Attach Zenith-1 day-limit audits to each proposed bundle."""
    account_id = account_id or _default_account_id()
    casual_limit = float(
        casual_limit if casual_limit is not None else Config.CASUAL_DAILY_LIMIT_LKR
    )
    # Aggregate proposed amounts by settlement day so multi-cheque same-day is honest.
    proposed_by_day: dict[str, float] = {}
    for bundle in bundles or []:
        day = (
            bundle.get("true_settlement_date")
            or bundle.get("calculated_settlement_date")
            or bundle.get("cheque_date")
        )
        if not day:
            continue
        proposed_by_day[day] = proposed_by_day.get(day, 0.0) + float(
            bundle.get("total_lkr") or 0
        )

    audits = []
    for bundle in bundles or []:
        day = (
            bundle.get("true_settlement_date")
            or bundle.get("cheque_date")
        )
        amount = float(bundle.get("total_lkr") or 0)
        if not day:
            audits.append(
                {
                    "group": bundle.get("group"),
                    "verdict": "MISSING_DATE",
                    "notes": "Bundle has no settlement/cheque date.",
                }
            )
            continue
        existing = day_exposure_for_settlement(day, account_id)
        # Count other proposed bundles on same day, not this one twice.
        same_day_proposed = proposed_by_day.get(day, 0.0)
        total = existing + same_day_proposed
        verdict = "LIMIT_BREACH_WARNING" if total > casual_limit else "CLEAR_TO_BATCH"
        audit = {
            "group": bundle.get("group"),
            "calculated_settlement_date": day,
            "invoice_amount": amount,
            "existing_day_exposure": existing,
            "total_day_exposure": total,
            "casual_limit": casual_limit,
            "verdict": verdict,
            "notes": (
                f"Day exposure LKR {total:,.2f} vs casual limit LKR {casual_limit:,.2f}."
            ),
        }
        audits.append(audit)
        bundle["day_limit_audit"] = audit
    return audits
