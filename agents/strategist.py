"""Agent 3: Cunning Financial Strategist — Gemini JSON cheque planner."""

from __future__ import annotations

import copy
from datetime import date, timedelta

from agents.base import generate_json
from config import Config
from core.bundling import compute_bundles, invoice_due_date, recalculate_all_bundles
from core.dates import format_date, parse_date
from core.dealer_patterns import build_dealer_pattern_document
from core.invoice_parts import apply_part_fields, original_amount
from core.strategist_dates import (
    earliest_cheque_date,
    interbank_account_options,
    latest_permissible_cheque_date,
)
from db import repositories as repo
from db.connection import query_one

STRATEGIST_SYSTEM = """You are Agent 3: the Cunning Financial Strategist for a Sri Lankan SME hardware shop.
You plan cheque payments to maximize legal cash float while respecting distributor credit terms.

Core directives:
1. Maximize liquidity float — keep shop cash in the bank as long as possible without breaching credit terms.
2. Prefer INTERBANK cheques when the shop paying account bank differs from the supplier bank (+1–2 SLIPS clearing days).
3. Position cheque dates before weekends/CBSL holidays when interbank cheques gain extra calendar float.
4. Split large totals into multiple cheques under the per-cheque ceiling to smooth daily cash outflow.
5. Learn from rag_historical_patterns — match past bank choices, split counts, and float style when sensible.

Output ONLY valid JSON with keys:
- strategy_summary (short string)
- proposed_cheques (array of objects), each with:
  cheque_index (int), selected_shop_account_id (int), payee_bank (string),
  amount (number), proposed_date (YYYY-MM-DD), clearing_type ("INTERBANK"|"INTRABANK"),
  strategic_reasoning (string)

Rules:
- Sum of proposed_cheques amounts must equal sum of invoices_to_pay amounts (minor rounding ok).
- Every invoice must be fully covered across all cheques.
- proposed_date must be on or after today and respect credit due dates.
- Use only account IDs and invoice data from the input JSON.
- No markdown. No text outside the JSON object."""


def _invoice_rows(invoice_ids: list[int]) -> list[dict]:
    rows = []
    for inv_id in invoice_ids:
        row = query_one("SELECT * FROM invoices WHERE invoices_id = ?", (int(inv_id),))
        if row:
            rows.append(dict(row))
    rows.sort(key=invoice_due_date)
    return rows


def _upcoming_holidays(invoices: list[dict], window_days: int = 45) -> list[dict]:
    if not invoices:
        return []
    today = date.today()
    end = today + timedelta(days=window_days)
    for inv in invoices:
        due = invoice_due_date(inv)
        if due > end:
            end = due + timedelta(days=14)
    return repo.get_holidays_in_range(today.isoformat(), end.isoformat())


def build_strategist_context(dealer_id: int, invoice_ids: list[int], ceiling_lkr: float) -> dict:
    dealer = repo.get_dealer(dealer_id) or {}
    bank = repo.get_dealer_preferred_bank(dealer_id)
    invoices = _invoice_rows(invoice_ids)
    pattern_doc = build_dealer_pattern_document(dealer_id)
    rag_patterns = []
    if pattern_doc and "No committed cheque payment history" not in pattern_doc:
        rag_patterns.append(pattern_doc)

    shop_accounts = []
    for acc in repo.get_bank_accounts():
        balance = float(acc.get("available_balance") or 0) + float(acc.get("overdraft_limit") or 0)
        shop_accounts.append(
            {
                "account_id": int(acc["user_bank_acc_id"]),
                "bank_name": acc.get("bank_name") or "",
                "current_balance": balance,
            }
        )

    holidays = repo.get_holidays()
    impossible = (dealer.get("impossible_days") or "") if dealer else ""
    invoices_enriched = []
    for inv in invoices:
        due = invoice_due_date(inv)
        earliest = earliest_cheque_date(holidays, impossible)
        latest = latest_permissible_cheque_date(inv, dealer, holidays)
        invoices_enriched.append(
            {
                "invoice_id": int(inv["invoices_id"]),
                "invoice_number": inv.get("invoice_no") or "",
                "amount": float(inv.get("total_amount") or 0),
                "date": inv.get("invoiced_date") or "",
                "due_date": due.isoformat(),
                "earliest_permissible_cheque_date": earliest.isoformat(),
                "latest_permissible_cheque_date": latest.isoformat(),
            }
        )

    return {
        "distributor": {
            "id": dealer_id,
            "name": dealer.get("dealer_name") or "",
            "credit_period_days": int(invoices[0].get("credit_period_days") or Config.DEFAULT_CREDIT_PERIOD_DAYS)
            if invoices
            else Config.DEFAULT_CREDIT_PERIOD_DAYS,
            "max_cheque_limit_per_cheque": float(ceiling_lkr),
            "bank_name": (bank or {}).get("bank_name") or "",
            "account_number": (bank or {}).get("account_name") or "",
            "casual_days": int(dealer.get("casual_days") or 0),
            "impossible_days": impossible,
        },
        "invoices_to_pay": invoices_enriched,
        "available_shop_accounts": shop_accounts,
        "interbank_account_options": interbank_account_options(dealer_id),
        "rag_historical_patterns": rag_patterns,
        "upcoming_cbsl_holidays": _upcoming_holidays(invoices),
        "today": format_date(date.today()),
    }


def _normalize_proposed_cheques(raw: list, ctx: dict) -> list[dict]:
    accounts = {int(a["account_id"]): a for a in ctx.get("available_shop_accounts") or []}
    default_acc = next(iter(accounts.keys()), None)
    payee_bank = (ctx.get("distributor") or {}).get("bank_name") or ""
    normalized = []
    for idx, item in enumerate(raw or []):
        if not isinstance(item, dict):
            continue
        acc_id = item.get("selected_shop_account_id")
        try:
            acc_id = int(acc_id)
        except (TypeError, ValueError):
            acc_id = default_acc
        if acc_id not in accounts and default_acc is not None:
            acc_id = default_acc
        clearing = str(item.get("clearing_type") or "INTERBANK").upper()
        if clearing not in ("INTERBANK", "INTRABANK"):
            clearing = "INTERBANK"
        try:
            amount = round(float(item.get("amount") or 0), 2)
        except (TypeError, ValueError):
            amount = 0.0
        proposed_date = (item.get("proposed_date") or "").strip()
        normalized.append(
            {
                "cheque_index": int(item.get("cheque_index") or idx + 1),
                "selected_shop_account_id": acc_id,
                "payee_bank": item.get("payee_bank") or payee_bank,
                "amount": amount,
                "proposed_date": proposed_date,
                "clearing_type": clearing,
                "strategic_reasoning": (item.get("strategic_reasoning") or "").strip(),
            }
        )
    normalized.sort(key=lambda c: c["cheque_index"])
    return [c for c in normalized if c["amount"] > 0]


def _allocate_invoices_to_cheques(
    invoices: list[dict], proposed_cheques: list[dict]
) -> list[list[dict]]:
    """Greedy amount allocation; may split one invoice across cheques."""
    pool: list[tuple[dict, float]] = [
        (copy.deepcopy(inv), float(inv["total_amount"])) for inv in invoices
    ]
    groups: list[list[dict]] = []

    for cheque in proposed_cheques:
        need = float(cheque["amount"])
        group: list[dict] = []
        while need > 0.01 and pool:
            inv, remaining = pool[0]
            if remaining <= need + 0.02:
                group.append(inv)
                pool.pop(0)
                need -= remaining
                continue
            orig = original_amount(inv)
            part = apply_part_fields(
                inv,
                amount=need,
                part_index=1,
                part_count=2,
                original=orig,
            )
            group.append(part)
            rest_amount = round(remaining - need, 2)
            if rest_amount > 0.01:
                rest_inv = apply_part_fields(
                    inv,
                    amount=rest_amount,
                    part_index=2,
                    part_count=2,
                    original=orig,
                )
                pool[0] = (rest_inv, rest_amount)
            else:
                pool.pop(0)
            need = 0.0
        groups.append(group)
    return groups


def proposed_cheques_to_bundles(
    dealer_id: int,
    proposed_cheques: list[dict],
    invoice_ids: list[int],
) -> list:
    invoices = _invoice_rows(invoice_ids)
    if not proposed_cheques:
        return compute_bundles(dealer_id, invoice_ids, 500_000)

    groups = _allocate_invoices_to_cheques(invoices, proposed_cheques)
    bundles = []
    for idx, cheque in enumerate(proposed_cheques):
        invs = groups[idx] if idx < len(groups) else []
        total = sum(float(i.get("total_amount") or 0) for i in invs)
        if total <= 0 and cheque.get("amount"):
            total = float(cheque["amount"])
        entry = {
            "group": int(cheque.get("cheque_index") or idx + 1),
            "invoices": invs,
            "total_lkr": round(total, 2),
            "cheque_date": cheque.get("proposed_date") or format_date(date.today()),
            "paying_account_id": cheque.get("selected_shop_account_id"),
            "clearing_type": cheque.get("clearing_type"),
            "strategic_reasoning": cheque.get("strategic_reasoning") or "",
        }
        bundles.append(entry)

    return recalculate_all_bundles(bundles, dealer_id)


def _bundles_to_strategy(bundles: list, dealer_id: int, ceiling_lkr: float) -> dict:
    """Convert Python bundles into spec-shaped strategist output (mock/fallback)."""
    dealer_bank = (repo.get_dealer_preferred_bank(dealer_id) or {}).get("bank_name") or ""
    default_acc = repo.paying_account_id_for_dealer(dealer_id)
    proposed = []
    for b in bundles:
        proposed.append(
            {
                "cheque_index": int(b.get("group") or len(proposed) + 1),
                "selected_shop_account_id": b.get("paying_account_id") or default_acc,
                "payee_bank": dealer_bank,
                "amount": float(b.get("total_lkr") or 0),
                "proposed_date": b.get("cheque_date") or format_date(date.today()),
                "clearing_type": "INTERBANK" if b.get("is_interbank") else "INTRABANK",
                "strategic_reasoning": "Standard ceiling packing with liquidity dates.",
            }
        )
    return {
        "strategy_summary": (
            f"Packed invoices into {len(proposed)} cheque(s) under Rs. {ceiling_lkr:,.0f} ceiling."
        ),
        "proposed_cheques": proposed,
    }


def propose_cheque_strategy(dealer_id: int, invoice_ids: list[int], ceiling_lkr: float) -> dict:
    if not invoice_ids:
        return {"strategy_summary": "No invoices selected.", "proposed_cheques": []}

    if Config.use_fake_ai():
        from agents.mock import mock_strategist

        return mock_strategist(dealer_id, invoice_ids, ceiling_lkr)

    if Config.use_strategist_tool_agent():
        try:
            from agents.strategist_agent import (
                run_strategist_agent,
                strategist_tool_agent_available,
            )

            if strategist_tool_agent_available():
                return run_strategist_agent(dealer_id, invoice_ids, ceiling_lkr)
        except Exception:
            pass

    ctx = build_strategist_context(dealer_id, invoice_ids, ceiling_lkr)
    import json

    prompt = f"Plan cheque payments for this context:\n{json.dumps(ctx, indent=2, default=str)}"
    try:
        raw = generate_json(
            prompt,
            STRATEGIST_SYSTEM,
            provider="gemini",
            model=Config.gemini_text_model(),
        )
        proposed = _normalize_proposed_cheques(raw.get("proposed_cheques") or [], ctx)
        if not proposed:
            raise ValueError("Strategist returned no proposed cheques")
        return {
            "strategy_summary": (raw.get("strategy_summary") or "Cunning float strategy applied.").strip(),
            "proposed_cheques": proposed,
        }
    except Exception:
        bundles = compute_bundles(dealer_id, invoice_ids, ceiling_lkr)
        return _bundles_to_strategy(bundles, dealer_id, ceiling_lkr)
