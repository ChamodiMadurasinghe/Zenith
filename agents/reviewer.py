import json
import re

from agents.base import generate_json, generate_text
from core.bundling_intent import normalize_proposed_actions
from config import Config
from core.reviewer_context import build_reviewer_context

REVIEWER_SYSTEM = """You are Agent 4: a friendly payment coach for a Sri Lankan hardware shop owner.
Your job is to explain the cheque plan in VERY SIMPLE words — like a patient teacher talking to someone
who is new to cheques and cash flow. No banking jargon unless you explain it in one plain line.

You receive JSON with the dealer, invoices, proposed cheques, liquidity dates, holidays, validation issues,
and Agent 3's strategy summary.

Write for shop owners with limited finance knowledge:
- Short sentences. Everyday words. Warm and informal (not stiff or corporate).
- Use real numbers from the context (Rs. amounts, dates, "X extra days") and say what they mean in plain terms.
- Example plain line: "Your money stays in your account until 15 Sept — that's about 12 extra days."
- If interbank cheques are used, explain simply: "Different bank cheque takes a bit longer to clear, so cash stays longer."

Structure:
1. First line ONLY: VERDICT: approve OR VERDICT: suggest_changes
2. Then 3–5 short paragraphs covering:
   - What cheques we are writing and for which invoices
   - How long money stays in the shop account and why that helps
   - Why we split cheques or picked a bank (if relevant)
   - Anything worth double-checking (gentle, not scary)

Rules:
- Use ONLY facts from the context JSON. Never invent invoice numbers, amounts, or dates.
- Do NOT output JSON in the review text.
- Do NOT recalculate or change the plan — only explain it."""

LANG_INSTRUCTIONS = {
    "en": (
        "Write the ENTIRE review in informal, friendly English — like explaining to a friend who runs a shop. "
        "Avoid words like 'liquidity', 'settlement', 'SLIPS' unless you immediately explain them simply."
    ),
    "si": (
        "සම්පූර්ණ සමාලෝචනය සිංහලෙන් ලියන්න. සරල, කතා කරන භාෂාව — වෙළඳසැලක් පවත්වන මිතුරෙකුට පැහැදිලි කරනවා වගේ. "
        "නිල බැංකු වචන වලින් වළකින්න."
    ),
    "ta": (
        "முழு விமர்சனத்தையும் தமிழில் எழுதுங்கள். எளிய, பேச்சு தமிழ் — கடை நடத்தும் நண்பருக்கு விளக்குவது போல. "
        "அதிகாரப்பூர்வ வங்கி சொற்களைத் தவிர்க்கவும்."
    ),
}

APPLY_LANG = {
    "en": "Write summary in simple informal English.",
    "si": "Write summary in simple spoken Sinhala.",
    "ta": "Write summary in simple spoken Tamil.",
}

REVIEWER_APPLY_SYSTEM = """You are a Sri Lankan shop owner implementing your own payment review for cheque bundles.
Output ONLY valid JSON with keys proposed_actions (array) and summary (short string for the merchant in simple words).

Goal: maximize legal cheque float — keep cash in the merchant bank until the latest target_funding_date.

Implement the review text you previously gave. You may fully rebuild invoice-to-cheque assignments.

Actions (same as bundling assistant):
- assign_invoices {action, assignments: {"invoice_id": group_no, ...}, cheque_dates: {"1": "YYYY-MM-DD", ...}}
- create_bundles {action, groups: [{invoice_ids: [...], cheque_date: "YYYY-MM-DD"}, ...]}
- divide_into_cheques {action, num_cheques, invoice_ids: [...], allow_exceed_ceiling: false}
- set_cheque_date {action, cheque_group, date}
- move_invoice {action, invoice_id, to_group}
- postpone_cheque {action, cheque_group, days}
- split_invoice {action, invoice_id} OR {action, invoice_id, num_parts: N} OR {action, invoice_id, amounts: [...]}
  (use num_parts/amounts to pay one invoice across multiple cheques as ·1 ·2 parts)
- recalculate_dates {action}

Rules:
- Every invoice in current_bundles must appear in the final layout (as a whole invoice OR as a complete set of split parts ·1..·N summing to the original total).
- Prefer assign_invoices with a complete assignments map when regrouping.
- When you suggested splitting an invoice, emit split_invoice with num_parts (or amounts).
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
    strategist_context: dict | None = None,
) -> dict:
    ctx = build_reviewer_context(
        dealer_id,
        bundles,
        ceiling_lkr,
        validation_issues,
        trigger=trigger,
        strategist_context=strategist_context,
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
        provider="gemini",
        model=Config.gemini_text_model(),
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
        provider="gemini",
        model=Config.gemini_text_model(),
    )
    actions = normalize_proposed_actions(raw.get("proposed_actions", raw))
    summary = (raw.get("summary") or "").strip()
    if not summary:
        summary = "Applied your payment suggestions to the cheque groups."
    return {"proposed_actions": actions, "summary": summary}
