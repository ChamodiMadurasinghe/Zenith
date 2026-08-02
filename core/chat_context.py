"""Build structured context for the bundling chat assistant."""

from datetime import date

from core.bundling import invoice_due_date
from db import repositories as repo

BUNDLING_ALGORITHM = """Python bundling rules (compute_bundles):
1. User selects verified, unassigned invoices and sets an LKR ceiling per cheque.
2. Invoices are sorted by due date (invoiced_date + credit_period_days).
3. Greedy grouping: add invoices to the current cheque until the next would exceed the ceiling; then start a new cheque.
4. Any single invoice above the ceiling gets its own cheque.
5. Cheque date = latest due date in the group + dealer casual_days (business days), respecting CBSL holidays and dealer impossible_days.
6. If that date is in the past, use tomorrow (next business day) instead.
7. enrich_bundle_liquidity adds true_settlement_date, target_funding_date, days_gained_by_holiday_lag, and is_interbank (dealer bank vs merchant bank).
8. calculate_optimal_cheque_batch (Zenith-1 tool) rolls settlement past CBSL holidays and audits deposit_timetable day exposure vs CASUAL_DAILY_LIMIT_LKR; verdict CLEAR_TO_BATCH or LIMIT_BREACH_WARNING."""


def _slim_invoice(inv: dict) -> dict:
    due = invoice_due_date(inv)
    return {
        "invoices_id": inv.get("invoices_id"),
        "invoice_no": inv.get("invoice_no"),
        "invoiced_date": inv.get("invoiced_date"),
        "credit_period_days": inv.get("credit_period_days"),
        "due_date": due.isoformat(),
        "total_amount": float(inv.get("total_amount") or 0),
        "on_cheque": inv.get("cheque_id") is not None,
        "verified": bool(inv.get("is_invoice_verified")),
    }


def _slim_bundle(b: dict) -> dict:
    audit = b.get("day_limit_audit") or {}
    return {
        "group": b.get("group"),
        "cheque_date": b.get("cheque_date"),
        "true_settlement_date": b.get("true_settlement_date"),
        "target_funding_date": b.get("target_funding_date"),
        "predicted_clearance_date": b.get("predicted_clearance_date"),
        "days_gained_by_holiday_lag": b.get("days_gained_by_holiday_lag"),
        "total_lkr": b.get("total_lkr"),
        "is_interbank": b.get("is_interbank"),
        "day_limit_verdict": audit.get("verdict"),
        "total_day_exposure": audit.get("total_day_exposure"),
        "invoices": [
            {
                "invoices_id": inv.get("invoices_id"),
                "invoice_no": inv.get("invoice_no"),
                "total_amount": float(inv.get("total_amount") or 0),
                "invoiced_date": inv.get("invoiced_date"),
                "credit_period_days": inv.get("credit_period_days"),
            }
            for inv in b.get("invoices", [])
        ],
    }


def build_bundling_chat_context(
    dealer_id: int,
    bundles: list,
    ceiling_lkr: float,
    agentic_hints: dict | None = None,
) -> dict:
    dealer = repo.get_dealer(dealer_id) or {}
    bank = repo.get_dealer_preferred_bank(dealer_id)
    summary = repo.get_dealer_invoice_summary(dealer_id)
    ready = repo.get_verified_unassigned_invoices(dealer_id)
    pending = repo.get_pending_verification_invoices(dealer_id)
    committed = repo.get_committed_cheque_bundles(dealer_id)

    merchant_acc = repo.get_bank_account(int(repo.get_setting("default_bank_acc_id", "1")))
    merchant_bank = merchant_acc["bank_name"] if merchant_acc else None

    hints = agentic_hints or {}
    return {
        "assistant_role": "Bundling Assistant",
        "naming_note": (
            "agentic Agent 2 = Anomaly; agentic Agent 3 = Liquidity Forecast; "
            "this chat is Bundling Assistant (not those pipeline agents)."
        ),
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
        "merchant_bank": merchant_bank,
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
        "bundling_algorithm": BUNDLING_ALGORITHM,
        "today": date.today().isoformat(),
        # From agentic pipeline when session_id is provided (feeds Bundling Assistant).
        "cheque_plan": hints.get("cheque_plan"),
        "anomaly_flags": hints.get("anomaly_flags") or [],
        "agentic_session_id": hints.get("session_id"),
    }
