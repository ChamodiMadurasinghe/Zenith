"""Unified WhatsApp outbound sender (Meta Cloud API default, Twilio optional, bridge fallback)."""

from __future__ import annotations

import requests

from config import Config


def send_whatsapp_message(to_phone: str, body: str):
    provider = Config.whatsapp_provider()
    if Config.use_whatsapp_mock():
        print(f"[whatsapp-mock:{provider}] to={to_phone}\n{body}")
        return {"mock": True, "to": to_phone, "body": body}

    if provider == "twilio":
        from core.twilio_client import send_twilio_whatsapp

        return send_twilio_whatsapp(to_phone, body)

    try:
        from core.meta_whatsapp import send_text_message

        return send_text_message(to_phone, body)
    except Exception as exc:
        bridge_url = Config.whatsapp_bridge_url().rstrip("/")
        secret = Config.whatsapp_bridge_secret()
        if not bridge_url or not secret:
            raise exc
        try:
            resp = requests.post(
                f"{bridge_url}/api/send",
                json={"to": to_phone, "body": body},
                headers={"X-Zenith-Bridge-Token": secret},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as bridge_exc:
            print(f"[whatsapp] Meta send failed ({exc}); bridge failed ({bridge_exc})")
            raise exc from bridge_exc
