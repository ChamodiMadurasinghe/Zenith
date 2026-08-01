import json
import re

from agents.base import generate_text
from config import Config
from core.app_guide import build_guide_context
from core.guide_actions import (
    build_nav_catalog,
    infer_guide_actions,
    is_cheque_section,
    normalize_guide_actions,
)
from core.i18n import translate

GUIDE_SYSTEM_BASE = """You are the Zenith Guide — a patient user-manual and technical helper for a Sri Lankan hardware merchant using the Zenith web app.
Your users are often middle-aged and not very technical. Use short numbered steps, plain language, and a respectful tone.

You help with:
- Navigating the app (Invoices, Cheques, Bank Balance, Reports)
- Explaining what each screen and button does
- Troubleshooting common problems (upload quality, login, language, pending invoices)
- General business workflow advice within the app

You must NEVER:
- Bundle cheques, split invoices, set cheque dates, move invoices between groups, or commit cheques
- Use proposed_actions or any Agent 2 bundling commands

Cheque bundling is EXCLUSIVELY done by Agent 2 (Cheque Assistant) on the supplier's Cheques page (right-hand panel).
If the user asks to bundle, divide, split, group, postpone, or date cheques, politely refuse and direct them to Agent 2.

Ground every answer in the app knowledge context provided."""

GUIDE_ACTIONS_PROMPT = """
On this page you MAY perform safe app actions for the user.
When they ask to go to a section or log out, give a brief friendly confirmation and append:

```json
{"guide_actions": [{"action": "navigate", "target": "cheques"}]}
```

Use only navigate (with target) or logout. Never bundle cheques via guide_actions."""

GUIDE_CHEQUE_PAGE_PROMPT = """
You are on the Cheques section. Do NOT emit guide_actions — the user is already here.
Explain the screen and direct bundling tasks to the Cheque Assistant (Agent 2) on the right."""

LANG_INSTRUCTIONS = {
    "en": "Always respond in English.",
    "si": "Always respond in Sinhala (සිංහල). Use simple, clear Sinhala suitable for a Sri Lankan merchant.",
    "ta": "Always respond in Tamil (தமிழ்). Use simple, clear Tamil suitable for a Sri Lankan merchant.",
}

BUNDLING_KEYWORDS = re.compile(
    r"\b(bundle|bundl|divide|split|group|cheque date|postpone|move invoice|"
    r"recalculate|ceiling|num cheques|කණ්ඩායම|වෙන්|දින|"
    r"குழு|பிரி|தேதி)\b",
    re.IGNORECASE,
)

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", re.IGNORECASE)


def _lang_instruction(lang: str) -> str:
    return LANG_INSTRUCTIONS.get(lang, LANG_INSTRUCTIONS["en"])


def _bundling_redirect(lang: str) -> str:
    return translate("guide_bundling_redirect", lang)


def _extract_guide_actions(reply: str) -> tuple[str, list]:
    actions: list = []
    match = _JSON_BLOCK.search(reply or "")
    if not match:
        return (reply or "").strip(), actions
    try:
        parsed = json.loads(match.group(1))
        actions = normalize_guide_actions(parsed.get("guide_actions", parsed))
        reply = (reply[: match.start()] + reply[match.end() :]).strip()
    except json.JSONDecodeError:
        pass
    return reply, actions


def _build_system(page_path: str, lang: str) -> str:
    parts = [GUIDE_SYSTEM_BASE, _lang_instruction(lang)]
    if is_cheque_section(page_path):
        parts.append(GUIDE_CHEQUE_PAGE_PROMPT)
    else:
        parts.append(GUIDE_ACTIONS_PROMPT)
        parts.append(build_nav_catalog())
    return "\n\n".join(parts)


def guide_chat(
    user_message: str,
    history: list,
    page_path: str,
    lang: str = "en",
) -> dict:
    on_cheque = is_cheque_section(page_path)

    if BUNDLING_KEYWORDS.search(user_message):
        return {"reply": _bundling_redirect(lang), "guide_actions": []}

    system = _build_system(page_path, lang)
    context = build_guide_context(page_path, lang)
    hist_text = "\n".join(f"{m['role']}: {m['content']}" for m in history[-8:])
    prompt = (
        f"App knowledge:\n{context}\n\n"
        f"Recent chat:\n{hist_text}\n\n"
        f"User: {user_message}"
    )

    reply = generate_text(
        prompt,
        system,
        provider="openai",
        model=Config.openai_chat_model(),
    )
    reply, actions = _extract_guide_actions(reply)

    if not on_cheque and not actions:
        actions = infer_guide_actions(user_message, lang)

    if not reply:
        reply = translate("guide_welcome", lang)

    if not on_cheque:
        return {"reply": reply, "guide_actions": actions}
    return {"reply": reply, "guide_actions": []}
