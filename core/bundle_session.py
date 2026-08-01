"""Keep Flask session bundles small (cookie limit ~4KB)."""

import json

from core.guardrails import collect_bundle_issues
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
    "is_interbank",
)


def slim_bundle(bundle: dict) -> dict:
    invoice_ids = [int(inv["invoices_id"]) for inv in bundle.get("invoices", [])]
    slim = {k: bundle[k] for k in _BUNDLE_KEYS if k in bundle}
    slim["invoice_ids"] = invoice_ids
    return slim


def slim_bundles(bundles: list) -> list:
    return [slim_bundle(b) for b in bundles]


def hydrate_bundle(slim: dict) -> dict:
    if slim.get("invoices"):
        return slim
    invoices = []
    for inv_id in slim.get("invoice_ids", []):
        inv = query_one("SELECT * FROM invoices WHERE invoices_id = ?", (int(inv_id),))
        if inv:
            invoices.append(inv)
    bundle = {k: slim[k] for k in _BUNDLE_KEYS if k in slim}
    bundle["invoices"] = invoices
    bundle["total_lkr"] = slim.get("total_lkr") or sum(float(i["total_amount"]) for i in invoices)
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
):
    existing = session.setdefault("bundle_state", {}).get(str(dealer_id), {})
    allow_exceed = allow_exceed_ceiling or existing.get("allow_exceed_ceiling", False)
    review_flag = pending_review if pending_review is not None else existing.get("pending_review")
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
