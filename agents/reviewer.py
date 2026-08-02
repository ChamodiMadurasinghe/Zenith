import json
import re

from agents.base import generate_json, generate_text
from core.bundling_intent import normalize_proposed_actions
from config import Config
from core.reviewer_context import build_reviewer_context

REVIEWER_SYSTEM = """You are a Sri Lankan SME hardware shop owner reviewing cheque bundles proposed by Python software.
Your PRIMARY objective is to maximize legal cheque float — keep the merchant's cash in their bank account as long as possible
before funds must be available (target_funding_date).

You receive full JSON context: dealer profile, supplier bank, merchant bank balance, LKR ceiling per cheque,
all invoices, Python's proposed bundles, per-cheque liquidity metrics, CBSL holidays near cheque dates, and validation issues.

Evaluate using:
- stated cheque date vs true_settlement_date vs target_funding_date
- days_gained_by_holiday_lag (extra float from stated date to Keep money until — weekends/holidays + interbank)
- is_interbank (+1 business day when merchant bank differs from supplier bank)
- dealer casual_days and impossible_days
- whether the LKR ceiling forced earlier funding than necessary
- supplier strictness when suggesting aggressive date moves

Rules:
- Cite specific invoice numbers, amounts, cheque groups, and dates from the context only.
- If Python's plan already maximizes float, explain WHY (holiday lag, interbank delay, grouping under ceiling).
- If changes could gain more days, give concrete suggestions (split/postpone/align with holiday) — text only, no JSON actions.
- Start your reply with exactly one line: VERDICT: approve OR VERDICT: suggest_changes
- Then write 2–5 short paragraphs for the merchant.
- Never invent data not in the context."""

LANG_INSTRUCTIONS = {
    "en": "Write the review in English.",
    "si": "Write the review in Sinhala (සිංහල). Use clear, practical Sinhala for a Sri Lankan merchant.",
    "ta": "Write the review in Tamil (தமிழ்). Use clear, practical Tamil for a Sri Lankan merchant.",
}

APPLY_LANG = {
    "en": "Write summary in English.",
    "si": "Write summary in Sinhala.",
    "ta": "Write summary in Tamil.",
}

REVIEWER_APPLY_SYSTEM = """You are a Sri Lankan SME owner implementing your own liquidity review for cheque bundles.
Output ONLY valid JSON with keys proposed_actions (array) and summary (short string for the merchant).

Goal: maximize legal cheque float — keep cash in the merchant bank until the latest target_funding_date.

Implement the review text you previously gave. You may fully rebuild invoice-to-cheque assignments.

Actions (same as bundling assistant):
- assign_invoices {action, assignments: {"invoice_id": group_no, ...}, cheque_dates: {"1": "YYYY-MM-DD", ...}}
- create_bundles {action, groups: [{invoice_ids: [...], cheque_date: "YYYY-MM-DD"}, ...]}
- divide_into_cheques {action, num_cheques, invoice_ids: [...], allow_exceed_ceiling: false}
- set_cheque_date {action, cheque_group, date}
- move_invoice {action, invoice_id, to_group}
- postpone_cheque {action, cheque_group, days}
- split_invoice {action, invoice_id}
- recalculate_dates {action}

Rules:
- Every invoice in current_bundles must appear exactly once in the final layout.
- Prefer assign_invoices with a complete assignments map when regrouping.
- Align stated dates with nearby CBSL holidays when it gains float.
- Respect ceiling_lkr unless allow_exceed_ceiling is true.
- Use only invoice_ids and dates from the context JSON.
- No markdown. No text outside the JSON object."""


def _parse_verdict(text: str) -> str:
    match = re.search(r"VERDICT:\s*(approve|suggest_changes)", text, re.IGNORECASE)
    if match:
        return match.group(1).lower()
    lower = text.lower()
    if any(w in lower for w in ("suggest", "change", "postpone", "split", "improve", "could gain")):
        return "suggest_changes"
    return "approve"


def _strip_verdict_line(text: str) -> str:
    return re.sub(r"^VERDICT:\s*(approve|suggest_changes)\s*\n?", "", text.strip(), flags=re.IGNORECASE).strip()


def review_bundles(
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
    lang_note = LANG_INSTRUCTIONS.get(lang, LANG_INSTRUCTIONS["en"])
    prompt = (
        f"{lang_note}\n\n"
        f"Review trigger: {trigger}\n\n"
        f"Context JSON:\n{json.dumps(ctx, indent=2, default=str)}"
    )
    raw = generate_text(
        prompt,
        REVIEWER_SYSTEM,
        provider="openai",
        model=Config.openai_chat_model(),
    )
    verdict = _parse_verdict(raw)
    review = _strip_verdict_line(raw)
    if not review:
        review = raw.strip()
    return {"review": review, "verdict": verdict}


def apply_reviewer_suggestions(
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
    lang_note = APPLY_LANG.get(lang, APPLY_LANG["en"])
    prompt = (
        f"{lang_note}\n\n"
        f"Your prior review to implement:\n{review_text}\n\n"
        f"Context JSON:\n{json.dumps(ctx, indent=2, default=str)}"
    )
    raw = generate_json(
        prompt,
        REVIEWER_APPLY_SYSTEM,
        provider="openai",
        model=Config.openai_chat_model(),
    )
    actions = normalize_proposed_actions(raw.get("proposed_actions", raw))
    summary = (raw.get("summary") or "").strip()
    if not summary:
        summary = "Applied SME liquidity suggestions to your cheque groups."
    return {"proposed_actions": actions, "summary": summary}
