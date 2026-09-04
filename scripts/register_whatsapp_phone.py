"""Register the Meta WhatsApp Cloud API phone number using .env credentials.

Usage:
  1. Set META_WHATSAPP_TOKEN, META_PHONE_NUMBER_ID, META_PHONE_PIN in .env
  2. python scripts/register_whatsapp_phone.py
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from config import Config


def main() -> int:
    token = Config.meta_whatsapp_token()
    phone_id = Config.meta_phone_number_id()
    pin = Config.meta_phone_pin()
    graph = Config.meta_graph_version()

    if not token:
        print("Missing META_WHATSAPP_TOKEN")
        return 1
    if not phone_id:
        print("Missing META_PHONE_NUMBER_ID")
        return 1
    if not pin or len(pin) != 6 or not pin.isdigit():
        print("Set META_PHONE_PIN to the 6-digit WhatsApp two-step PIN in .env")
        return 1

    url = f"https://graph.facebook.com/{graph}/{phone_id}/register"
    body = json.dumps({"messaging_product": "whatsapp", "pin": pin}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    print(f"Registering phone_number_id={phone_id} via {graph} …")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            print("OK", resp.status, resp.read().decode()[:500])
            return 0
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        print("FAIL", exc.code, detail[:800])
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
