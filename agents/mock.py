"""Instant demo responses for bundling chat — zero API quota."""

from core.chat_context import build_bundling_chat_context
from core.guide_actions import infer_guide_actions, is_cheque_section
from core.i18n import translate
from core.reviewer_context import build_reviewer_context


def mock_bundling_chat(
    user_message: str,
    dealer_id: int,
    bundles: list,
    dealer: dict,
    history: list,
    ceiling_lkr: float,
    lang: str = "en",
) -> dict:
    ctx = build_bundling_chat_context(dealer_id, bundles, ceiling_lkr)
    dealer_name = ctx["dealer"].get("dealer_name") or "your supplier"
    n_bundles = len(bundles)
    dates = ", ".join(b.get("cheque_date", "?") for b in bundles[:3]) or "not set yet"
    ready = ctx.get("ready_invoices") or []
    ready_list = ", ".join(
        f"{i['invoice_no']} (Rs. {i['total_amount']:,.0f})" for i in ready[:5]
    ) or "none"

    reply = translate("mock_chat_intro", lang, dealer=dealer_name, n=n_bundles, dates=dates)
    reply += f" Ready invoices: {ready_list}. Ceiling Rs. {ceiling_lkr:,.0f}."

    actions = []
    lower = user_message.lower()
    if any(w in lower for w in ("invoice", "inv", "ready", "pending")):
        pending = ctx.get("pending_invoices") or []
        reply += f" Pending verification: {len(pending)}. Committed cheques: {len(ctx.get('committed_cheques') or [])}."
    elif any(w in lower for w in ("postpone", "delay", "later", "next week", "පසු", "මඳ", "தள்ள")):
        reply += translate("mock_chat_postpone", lang)
        if n_bundles >= 1:
            actions = [{"action": "postpone_cheque", "cheque_group": 1, "days": 3}]
    elif any(w in lower for w in ("split", "separate", "own cheque", "වෙන්", "பிரி")):
        reply += translate("mock_chat_split", lang)
        if bundles and bundles[0].get("invoices"):
            inv_id = bundles[0]["invoices"][0].get("invoices_id")
            if inv_id:
                actions = [{"action": "split_invoice", "invoice_id": inv_id}]
    elif any(w in lower for w in ("date", "tuesday", "monday", "change", "bundle", "group", "දින", "தேதி")):
        reply += translate("mock_chat_date", lang)
    else:
        reply += translate("mock_chat_default", lang)

    return {"reply": reply, "proposed_actions": actions}


def mock_bundle_review(
    dealer_id: int,
    bundles: list,
    ceiling_lkr: float,
    validation_issues: list | None,
    lang: str = "en",
    trigger: str = "compute",
) -> dict:
    ctx = build_reviewer_context(
        dealer_id, bundles, ceiling_lkr, validation_issues, trigger=trigger
    )
    summary = ctx.get("liquidity_summary") or {}
    lag = int(
        summary.get("total_days_gained")
        if summary.get("total_days_gained") is not None
        else summary.get("total_days_gained_by_holiday_lag")
        or 0
    )
    max_days = summary.get("max_days_until_funding") or 0
    holidays = ctx.get("holidays_near_cheques") or []
    holiday_note = ""
    if holidays:
        h = holidays[0]
        holiday_note = f" Near {h['date']}: {h.get('description') or 'CBSL holiday'} (cheques {h.get('near_cheque_groups')})."

    if validation_issues or lag == 0:
        review = translate(
            "mock_review_suggest",
            lang,
            count=len(bundles),
            lag=lag,
            max_days=max_days,
            holiday_note=holiday_note,
        )
        verdict = "suggest_changes"
    else:
        review = translate(
            "mock_review_approve",
            lang,
            count=len(bundles),
            lag=lag,
            max_days=max_days,
            holiday_note=holiday_note,
        )
        verdict = "approve"

    if trigger == "preview":
        review = translate("mock_review_preview_intro", lang) + " " + review

    return {"review": review, "verdict": verdict}


def mock_apply_reviewer_suggestions(
    dealer_id: int,
    bundles: list,
    ceiling_lkr: float,
    validation_issues: list | None,
    review_text: str,
    lang: str = "en",
) -> dict:
    ctx = build_reviewer_context(
        dealer_id, bundles, ceiling_lkr, validation_issues, trigger="apply"
    )
    assignments: dict[str, int] = {}
    cheque_dates: dict[str, str] = {}
    for b in bundles:
        group = b.get("group")
        if group is not None and b.get("cheque_date"):
            cheque_dates[str(group)] = b["cheque_date"]
        for inv in b.get("invoices") or []:
            inv_id = inv.get("invoices_id")
            if inv_id is not None and group is not None:
                assignments[str(inv_id)] = int(group)

    actions: list[dict] = []
    if assignments:
        actions.append(
            {
                "action": "assign_invoices",
                "assignments": assignments,
                "cheque_dates": cheque_dates,
                "ceiling_lkr": ceiling_lkr,
            }
        )
        actions.append({"action": "recalculate_dates"})
    elif bundles:
        actions.append({"action": "postpone_cheque", "cheque_group": 1, "days": 3})
        actions.append({"action": "recalculate_dates"})

    lag = int(
        (ctx.get("liquidity_summary") or {}).get("total_days_gained")
        if (ctx.get("liquidity_summary") or {}).get("total_days_gained") is not None
        else (ctx.get("liquidity_summary") or {}).get("total_days_gained_by_holiday_lag")
        or 0
    )
    summary = translate(
        "mock_apply_review_summary",
        lang,
        count=len(bundles),
        lag=lag,
    )
    return {"proposed_actions": actions, "summary": summary}


BUNDLING_HINTS = (
    "bundle", "bundl", "divide", "split", "group", "postpone", "cheque date",
    "move invoice", "ceiling", "කණ්ඩායම", "චෙක්", "වෙන්", "குழு", "பிரி", "காசோலை",
)


def mock_guide_chat(
    user_message: str,
    page_path: str,
    history: list,
    lang: str = "en",
) -> dict:
    lower = user_message.lower()
    on_cheque = is_cheque_section(page_path)

    if any(w in lower for w in BUNDLING_HINTS):
        return {"reply": translate("guide_bundling_redirect", lang), "guide_actions": []}

    guide_actions: list = []
    if not on_cheque:
        guide_actions = infer_guide_actions(user_message, lang)

    if guide_actions:
        if guide_actions[0].get("action") == "logout":
            reply = translate("guide_action_logging_out", lang)
        else:
            target = guide_actions[0].get("target", "")
            reply = translate("guide_action_navigating", lang, target=target)
    elif any(w in lower for w in ("upload", "photo", "invoice", "ඡායා", "புகைப்பட")):
        reply = translate("mock_guide_upload", lang)
    elif any(w in lower for w in ("cheque", "check", "supplier", "dealer", "චෙක්", "காசோலை")):
        reply = translate("mock_guide_cheques_nav", lang)
    elif any(w in lower for w in ("cash", "bank", "balance", "deposit", "බැංකු", "வங்கி")):
        reply = translate("mock_guide_cash", lang)
    elif any(w in lower for w in ("language", "sinhala", "tamil", "english", "භාෂා", "மொழி")):
        reply = translate("mock_guide_language", lang)
    else:
        reply = translate("mock_guide_default", lang)

    if not guide_actions:
        intro = translate("mock_guide_intro", lang)
        reply = f"{intro} {reply}"

    return {"reply": reply, "guide_actions": guide_actions if not on_cheque else []}
