from __future__ import annotations

import json

from agents.dealer_onboarding import (
    build_onboarding_prompt,
    parse_onboarding_reply,
    register_dealer_from_setup,
)
from db import repositories as repo

STATE_IDLE = "idle"
STATE_AWAITING_DEALER_CONFIRM = "awaiting_dealer_confirm"


def get_session(phone: str) -> dict:
    return repo.get_whatsapp_session(phone)


def save_session(phone: str, state: str, context: dict):
    repo.upsert_whatsapp_session(phone, state, context)


def clear_session(phone: str):
    repo.clear_whatsapp_session(phone)


def begin_dealer_confirmation(phone: str, dealer_setup: dict, invoice_id: int | None = None) -> str:
    context = {"dealer_setup": dealer_setup, "invoice_id": invoice_id}
    save_session(phone, STATE_AWAITING_DEALER_CONFIRM, context)
    return build_onboarding_prompt(dealer_setup)


def handle_text_reply(phone: str, body: str) -> str | None:
    sess = get_session(phone)
    state = sess.get("state", STATE_IDLE)
    if state != STATE_AWAITING_DEALER_CONFIRM:
        return None

    decision = parse_onboarding_reply(body)
    if decision == "unknown":
        return "Please reply YES to register dealer, or NO to keep pending."
    if decision == "reject":
        clear_session(phone)
        return "Okay, dealer was not registered. Invoice stays pending for web verification."

    setup = sess.get("context", {}).get("dealer_setup") or {}
    if not setup.get("dealer_name"):
        clear_session(phone)
        return "Dealer details are missing. Please verify from web dashboard."
    try:
        dealer_id = register_dealer_from_setup(setup)
        invoice_id = sess.get("context", {}).get("invoice_id")
        if invoice_id:
            repo.update_invoice_dealer_id(int(invoice_id), dealer_id)
    except Exception as exc:
        clear_session(phone)
        return f"Could not register dealer: {exc}"
    clear_session(phone)
    return f"Dealer registered successfully (ID {dealer_id})."
