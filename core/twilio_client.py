from __future__ import annotations

from twilio.rest import Client

from config import Config


def send_whatsapp_message(to_phone: str, body: str):
    sid = Config.twilio_account_sid()
    token = Config.twilio_auth_token()
    from_phone = Config.twilio_whatsapp_from()
    if not sid or not token or not from_phone:
        raise RuntimeError("Twilio credentials are not configured")
    client = Client(sid, token)
    return client.messages.create(from_=from_phone, to=to_phone, body=body)
