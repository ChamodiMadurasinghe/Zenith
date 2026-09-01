"""Optional Twilio WhatsApp sender (legacy provider)."""

from __future__ import annotations

from twilio.rest import Client

from config import Config
from core.meta_whatsapp import normalize_whatsapp_phone


def send_twilio_whatsapp(to_phone: str, body: str):
    sid = Config.twilio_account_sid()
    token = Config.twilio_auth_token()
    from_phone = Config.twilio_whatsapp_from()
    if not sid or not token or not from_phone:
        raise RuntimeError("Twilio credentials are not configured")
    e164 = normalize_whatsapp_phone(to_phone)
    to = e164 if e164.startswith("whatsapp:") else f"whatsapp:{e164}"
    client = Client(sid, token)
    return client.messages.create(from_=from_phone, to=to, body=body)


def send_whatsapp_message(to_phone: str, body: str):
    """Backward-compatible import path ÔÇö routes through unified sender."""
    from core.whatsapp_sender import send_whatsapp_message as send

    return send(to_phone, body)
