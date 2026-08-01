"""Unified WhatsApp outbound sender (Meta Cloud API default, Twilio optional)."""

from __future__ import annotations

from config import Config


def send_whatsapp_message(to_phone: str, body: str):
    provider = Config.whatsapp_provider()
    if Config.use_whatsapp_mock():
        print(f"[whatsapp-mock:{provider}] to={to_phone}\n{body}")
        return {"mock": True, "to": to_phone, "body": body}

    if provider == "twilio":
        from core.twilio_client import send_twilio_whatsapp

        return send_twilio_whatsapp(to_phone, body)

    from core.meta_whatsapp import send_text_message

    return send_text_message(to_phone, body)
