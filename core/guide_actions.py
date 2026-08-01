"""Safe navigation actions for the Zenith Guide (no bundling)."""

import re

from flask import url_for

CHEQUE_SECTION = (
    re.compile(r"^/bundling"),
    re.compile(r"^/dealers/\d+/cheques"),
)

NAV_TARGETS: dict[str, tuple[str, dict]] = {
    "invoices": ("ingestion.dashboard", {}),
    "cheques": ("bundling.bundling_home", {}),
    "cash_flow": ("cash_flow.cash_flow", {}),
    "analytics": ("analytics.analytics", {}),
    "add_dealer": ("dealers.new_dealer", {}),
    "manual_invoice": ("ingestion.manual_invoice", {}),
}

ALLOWED_ACTIONS = frozenset({"navigate", "logout"})


def is_cheque_section(page_path: str) -> bool:
    path = (page_path or "/").split("?")[0] or "/"
    return any(p.search(path) for p in CHEQUE_SECTION)


def build_nav_catalog() -> str:
    lines = [
        "Navigation targets you may use in guide_actions (non-cheque pages only):",
        '- {"action": "navigate", "target": "invoices"} — Invoices dashboard',
        '- {"action": "navigate", "target": "cheques"} — Cheques home (pick supplier)',
        '- {"action": "navigate", "target": "cash_flow"} — Bank Balance',
        '- {"action": "navigate", "target": "analytics"} — Reports',
        '- {"action": "navigate", "target": "add_dealer"} — Add new supplier',
        '- {"action": "navigate", "target": "manual_invoice"} — Enter invoice manually',
        '- {"action": "logout"} — Sign the user out',
        "When the user asks to go somewhere or log out, include a ```json``` block:",
        '{"guide_actions": [{"action": "navigate", "target": "cheques"}]}',
    ]
    return "\n".join(lines)


def normalize_guide_actions(raw) -> list[dict]:
    if not raw:
        return []
    items = raw if isinstance(raw, list) else [raw] if isinstance(raw, dict) else []
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        action = (item.get("action") or "").strip().lower()
        if action not in ALLOWED_ACTIONS:
            continue
        if action == "logout":
            out.append({"action": "logout"})
            continue
        target = (item.get("target") or "").strip().lower()
        if target in NAV_TARGETS:
            out.append({"action": "navigate", "target": target})
    return out


def resolve_guide_actions(actions: list[dict]) -> list[dict]:
    resolved: list[dict] = []
    for item in actions:
        action = item.get("action")
        if action == "logout":
            resolved.append({"action": "logout"})
            continue
        if action == "navigate":
            target = item.get("target")
            endpoint, values = NAV_TARGETS.get(target, (None, None))
            if not endpoint:
                continue
            resolved.append({"action": "navigate", "target": target, "url": url_for(endpoint, **values)})
    return resolved


def infer_guide_actions(message: str, lang: str = "en") -> list[dict]:
    lower = message.lower()
    if any(w in lower for w in ("logout", "log out", "sign out", "වෙන්න", "නික්ම", "வெளியேற", "வெளியே")):
        return [{"action": "logout"}]
    if any(
        w in lower
        for w in (
            "write cheque",
            "write cheques",
            "open cheque",
            "open cheques",
            "go to cheque",
            "cheques page",
            "චෙක්පත් ලිය",
            "காசோலை எழுத",
        )
    ):
        return [{"action": "navigate", "target": "cheques"}]
    if any(w in lower for w in ("invoice", "upload", "invoices page", "ඉන්වොයිස්", "புகைப்பட")):
        if any(w in lower for w in ("manual", "by hand", "අතින්", "கையால்")):
            return [{"action": "navigate", "target": "manual_invoice"}]
        return [{"action": "navigate", "target": "invoices"}]
    if any(w in lower for w in ("bank balance", "cash flow", "බැංකු", "வங்கி", "balance")):
        return [{"action": "navigate", "target": "cash_flow"}]
    if any(w in lower for w in ("report", "analytics", "වාර්තා", "அறிக்கை")):
        return [{"action": "navigate", "target": "analytics"}]
    if any(w in lower for w in ("add supplier", "add dealer", "new supplier", "සැපයුම්කරු", "சப்ளையர் சேர்")):
        return [{"action": "navigate", "target": "add_dealer"}]
    return []
