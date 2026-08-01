import json
import re

from agents.base import generate_json, generate_text
from config import Config
from core.bundling_intent import infer_bundling_actions, is_bundling_request, normalize_proposed_actions
from core.chat_context import build_bundling_chat_context

DEALER_SETUP_SYSTEM = """You help set up a new supplier (dealer) for a Sri Lankan hardware business.
Given extracted supplier name, suggest friendly defaults for dealer_strictness (High/Medium/Low),
casual_days (integer), and impossible_days (comma-separated weekdays).
Return JSON: {dealer_name, dealer_email, dealer_telno, dealer_address, dealer_strictness,
casual_days, impossible_days, account_name, bank_name, branch_name, welcome_message}."""

BUNDLING_SYSTEM = """You are a supportive cheque-bundling assistant for a Sri Lankan merchant.
You receive full JSON context: dealer profile, bank details, invoice lists (ready, pending, committed),
the current Python-computed bundle groups, LKR ceiling, and the bundling algorithm rules.

Always ground answers in that context — cite invoice numbers, amounts, due dates, and cheque groups when relevant.

CRITICAL: When the user asks to bundle, divide, split, or group invoices into cheques, you MUST include a
```json ... ``` block with proposed_actions. Never say "hold on" or "let me calculate" without that JSON block.
Python applies your JSON immediately and updates the cheques on screen.

When the user requests changes, include a JSON block at the end inside ```json ... ``` with key proposed_actions (array).
Your proposals are applied by Python, then verified. List every issue clearly in your reply if verification fails.
The user may still preview and write cheques after acknowledging warnings — do not refuse; explain risks instead.

Actions:
- divide_into_cheques {action, num_cheques, invoice_ids: [...], allow_exceed_ceiling: true/false}
- create_bundles {action, groups: [{invoice_ids: [1,2], cheque_date: "YYYY-MM-DD"}, ...]}
- assign_invoices {action, assignments: {"invoice_id": group_no, ...}, cheque_dates: {"1": "YYYY-MM-DD", ...}}
- set_cheque_date {action, cheque_group, date}
- move_invoice {action, invoice_id, to_group}
- postpone_cheque {action, cheque_group, days}
- split_invoice {action, invoice_id}
- recalculate_dates {action}

Use divide_into_cheques when the user wants N cheques (e.g. "divide into 5 cheques").
Set allow_exceed_ceiling true when the user says exceeding the limit is OK.
Use invoice_ids from current_bundles and/or ready_invoices. Every invoice in the bundle request should appear once.
When you finish proposing a bundle layout, say bundling is complete and tell the user to review cheques on the left.

Be concise. Never return an empty message — always give a helpful text reply before any JSON block."""

ACTIONS_SYSTEM = """You output ONLY valid JSON for cheque bundling actions.
Return: {"proposed_actions": [ ... ]}
Use divide_into_cheques, create_bundles, assign_invoices, move_invoice, set_cheque_date, split_invoice, postpone_cheque, or recalculate_dates.
Never wrap in markdown. Never add commentary."""

LANG_INSTRUCTIONS = {
    "en": "Always respond in English.",
    "si": "Always respond in Sinhala (සිංහල). Use simple, clear Sinhala suitable for a Sri Lankan merchant.",
    "ta": "Always respond in Tamil (தமிழ்). Use simple, clear Tamil suitable for a Sri Lankan merchant.",
}

EMPTY_REPLY_FALLBACK = "I'm here to help with cheque bundling for this supplier. Ask about their invoices, current groups, or dates."


def _lang_instruction(lang: str) -> str:
    return LANG_INSTRUCTIONS.get(lang, LANG_INSTRUCTIONS["en"])


def _normalize_actions(raw) -> list[dict]:
    return normalize_proposed_actions(raw)


def _extract_actions(reply: str) -> tuple[str, list]:
    actions: list = []

    for pattern in (r"```json\s*(\{.*\})\s*```", r"```\s*(\{.*\})\s*```"):
        match = re.search(pattern, reply, re.DOTALL)
        if not match:
            continue
        try:
            parsed = json.loads(match.group(1))
            actions = _normalize_actions(parsed.get("proposed_actions", parsed))
            reply = reply[: match.start()].strip()
            return reply, actions
        except json.JSONDecodeError:
            continue

    match = re.search(r'"proposed_actions"\s*:\s*(\{.*\}|\[.*\])', reply, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(1))
            actions = _normalize_actions(parsed)
            reply = re.sub(r"\{[^{}]*\"proposed_actions\"[^{}]*\}", "", reply, flags=re.DOTALL).strip()
            return reply, actions
        except json.JSONDecodeError:
            pass

    return reply, []


def _generate_actions_fallback(
    user_message: str,
    dealer_id: int,
    bundle_state: list,
    ceiling_lkr: float,
    lang: str,
) -> list:
    context = build_bundling_chat_context(dealer_id, bundle_state, ceiling_lkr)
    context_json = json.dumps(context, default=str, indent=2)
    prompt = (
        f"Context:\n{context_json}\n\n"
        f"User request: {user_message}\n\n"
        "Return proposed_actions to fulfil this bundling request."
    )
    try:
        parsed = generate_json(
            prompt,
            ACTIONS_SYSTEM + "\n" + _lang_instruction(lang),
            provider="openai",
            model=Config.openai_chat_model(),
        )
        return _normalize_actions(parsed.get("proposed_actions", parsed))
    except Exception:
        return []


def suggest_dealer_setup(supplier_name: str) -> dict:
    return generate_json(
        f"New supplier detected: {supplier_name}. Suggest dealer setup fields.",
        DEALER_SETUP_SYSTEM,
        provider="openai",
        model=Config.openai_chat_model(),
    )


def bundling_chat(
    user_message: str,
    dealer_id: int,
    bundle_state: list,
    dealer: dict,
    history: list,
    ceiling_lkr: float,
    lang: str = "en",
) -> dict:
    system = BUNDLING_SYSTEM + "\n\n" + _lang_instruction(lang)
    context = build_bundling_chat_context(dealer_id, bundle_state, ceiling_lkr)
    context_json = json.dumps(context, default=str, indent=2)
    hist_text = "\n".join(f"{m['role']}: {m['content']}" for m in history[-6:])
    prompt = (
        f"Context (dealer, invoices, bundles, rules):\n{context_json}\n\n"
        f"Recent chat:\n{hist_text}\n\n"
        f"User: {user_message}"
    )
    reply = generate_text(
        prompt,
        system,
        provider="openai",
        model=Config.openai_chat_model(),
    )

    reply, actions = _extract_actions(reply)

    if not actions and is_bundling_request(user_message):
        actions = _generate_actions_fallback(
            user_message, dealer_id, bundle_state, ceiling_lkr, lang
        )
    if not actions and is_bundling_request(user_message):
        actions = infer_bundling_actions(user_message, bundle_state, dealer_id)

    if not reply.strip():
        reply = EMPTY_REPLY_FALLBACK

    return {"reply": reply, "proposed_actions": actions}
