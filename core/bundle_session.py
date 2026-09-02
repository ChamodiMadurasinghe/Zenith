"""Keep Flask session bundles small (cookie limit ~4KB)."""

import json

from core.guardrails import collect_bundle_issues
from core.invoice_parts import hydrate_invoice_from_meta, slim_invoice_meta
from db import repositories as repo
from db.connection import query_one

_BUNDLE_KEYS = (
    "group",
    "total_lkr",
    "cheque_date",
    "true_settlement_date",
    "target_funding_date",
    "predicted_clearance_date",
    "days_gained_by_holiday_lag",
    "days_gained_total",
    "is_interbank",
)


def slim_bundle(bundle: dict) -> dict:
    invoices = bundle.get("invoices") or []
    invoice_ids = [int(inv["invoices_id"]) for inv in invoices]
    slim = {k: bundle[k] for k in _BUNDLE_KEYS if k in bundle}
    slim["invoice_ids"] = invoice_ids
    # Persist split part amounts/labels (hydrate reloads base invoice from DB).
    slim["invoices_meta"] = [slim_invoice_meta(inv) for inv in invoices]
    return slim


def slim_bundles(bundles: list) -> list:
    return [slim_bundle(b) for b in bundles]


def hydrate_bundle(slim: dict) -> dict:
    if slim.get("invoices") and not slim.get("invoice_ids") and not slim.get("invoices_meta"):
        return slim

    meta_list = slim.get("invoices_meta")
    invoices = []
    if meta_list:
        for meta in meta_list:
            inv_id = int(meta["invoices_id"])
            row = query_one("SELECT * FROM invoices WHERE invoices_id = ?", (inv_id,))
            if row:
                invoices.append(hydrate_invoice_from_meta(row, meta))
    elif slim.get("invoices"):
        return slim
    else:
        for inv_id in slim.get("invoice_ids", []):
            inv = query_one("SELECT * FROM invoices WHERE invoices_id = ?", (int(inv_id),))
            if inv:
                invoices.append(inv)

    bundle = {k: slim[k] for k in _BUNDLE_KEYS if k in slim}
    bundle["invoices"] = invoices
    bundle["total_lkr"] = slim.get("total_lkr") or sum(float(i["total_amount"]) for i in invoices)
    # Re-enrich clearance dates if slim lost them (cookie trim / older drafts).
    if bundle.get("cheque_date") and not bundle.get("predicted_clearance_date"):
        dealer_id = None
        if invoices:
            dealer_id = invoices[0].get("dealer_id")
        if dealer_id:
            from core.bundling import enrich_bundle_liquidity

            enrich_bundle_liquidity(bundle, int(dealer_id), repo.get_holidays())
        else:
            bundle["predicted_clearance_date"] = (
                bundle.get("target_funding_date")
                or bundle.get("true_settlement_date")
                or bundle["cheque_date"]
            )
    return bundle


def hydrate_bundles(slims: list) -> list:
    return [hydrate_bundle(s) for s in slims]


def trim_chat_history(history: list, limit: int = 8) -> list:
    return history[-limit:] if history else []


def _state_from_db_draft(draft: dict) -> dict:
    bundles = hydrate_bundles(json.loads(draft["bundles_json"] or "[]"))
    validation_issues = json.loads(draft["validation_issues_json"] or "[]")
    chat_history = json.loads(draft.get("chat_history_json") or "[]")
    return {
        "bundles": bundles,
        "ceiling_lkr": float(draft["ceiling_lkr"]),
        "chat_history": chat_history,
        "validation_issues": validation_issues,
        "allow_exceed_ceiling": bool(draft.get("allow_exceed_ceiling")),
    }


def load_bundle_state(session, dealer_id: int, default_ceiling: float = 500000) -> dict:
    session_state = session.setdefault("bundle_state", {}).get(str(dealer_id), {})
    db_draft = repo.load_bundle_draft(dealer_id)

    if session_state.get("bundles"):
        return {
            "bundles": hydrate_bundles(session_state.get("bundles", [])),
            "ceiling_lkr": session_state.get("ceiling_lkr", default_ceiling),
            "chat_history": session_state.get("chat_history", []),
            "validation_issues": session_state.get("validation_issues", []),
            "allow_exceed_ceiling": session_state.get("allow_exceed_ceiling", False),
            "pending_review": session_state.get("pending_review"),
            "strategy_summary": session_state.get("strategy_summary"),
            "proposed_cheques": session_state.get("proposed_cheques"),
        }

    if db_draft:
        db_state = _state_from_db_draft(db_draft)
        session["bundle_state"][str(dealer_id)] = {
            "bundles": slim_bundles(db_state["bundles"]),
            "ceiling_lkr": db_state["ceiling_lkr"],
            "chat_history": trim_chat_history(db_state["chat_history"]),
            "validation_issues": db_state["validation_issues"],
            "allow_exceed_ceiling": db_state["allow_exceed_ceiling"],
            "pending_review": session_state.get("pending_review"),
        }
        session.modified = True
        db_state["pending_review"] = session_state.get("pending_review")
        return db_state

    return {
        "bundles": [],
        "ceiling_lkr": default_ceiling,
        "chat_history": [],
        "validation_issues": [],
        "allow_exceed_ceiling": False,
        "pending_review": session_state.get("pending_review"),
        "strategy_summary": session_state.get("strategy_summary"),
        "proposed_cheques": session_state.get("proposed_cheques"),
    }


def save_bundle_state(
    session,
    dealer_id: int,
    bundles: list,
    ceiling_lkr: float,
    chat_history: list,
    validation_issues: list | None = None,
    allow_exceed_ceiling: bool = False,
    pending_review: str | None = None,
    strategy_summary: str | None = None,
    proposed_cheques: list | None = None,
):
    existing = session.setdefault("bundle_state", {}).get(str(dealer_id), {})
    allow_exceed = allow_exceed_ceiling or existing.get("allow_exceed_ceiling", False)
    review_flag = pending_review if pending_review is not None else existing.get("pending_review")
    strategy_text = strategy_summary if strategy_summary is not None else existing.get("strategy_summary")
    cheques_plan = proposed_cheques if proposed_cheques is not None else existing.get("proposed_cheques")
    issues = (
        validation_issues
        if validation_issues is not None
        else collect_bundle_issues(
            {"bundles": bundles},
            dealer_id,
            ceiling_lkr,
            allow_exceed_ceiling=allow_exceed,
        )
    )
    slim = slim_bundles(bundles)
    trimmed_history = trim_chat_history(chat_history)
    session.setdefault("bundle_state", {})[str(dealer_id)] = {
        "bundles": slim,
        "ceiling_lkr": ceiling_lkr,
        "chat_history": trimmed_history,
        "validation_issues": issues,
        "allow_exceed_ceiling": allow_exceed,
        "pending_review": review_flag,
        "strategy_summary": strategy_text,
        "proposed_cheques": cheques_plan,
    }
    session.modified = True
    repo.save_bundle_draft(
        dealer_id,
        ceiling_lkr,
        slim,
        issues,
        trimmed_history,
        allow_exceed_ceiling=allow_exceed,
    )
