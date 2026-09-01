"""Probe Meta WhatsApp webhook path locally and via public tunnel."""

import requests

from config import Config
from db.connection import query


def main():
    base = Config.webhook_public_url()
    r = requests.get(
        f"{base}/webhook/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": Config.meta_verify_token(),
            "hub.challenge": "now",
        },
        timeout=20,
    )
    print("WEBHOOK_VERIFY", base, r.status_code, r.text)

    health = requests.get(f"{base}/webhook/whatsapp/health", timeout=20)
    print("HEALTH", health.status_code, health.text[:200])

    rows = query(
        "SELECT invoices_id, invoice_no, total_amount, location_path "
        "FROM invoices ORDER BY invoices_id DESC LIMIT 3"
    )
    print("TOP", [dict(x) for x in rows])

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "1740539786975638",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15552029450",
                                "phone_number_id": Config.meta_phone_number_id(),
                            },
                            "contacts": [
                                {"profile": {"name": "Test"}, "wa_id": "94771234567"}
                            ],
                            "messages": [
                                {
                                    "from": "94771234567",
                                    "id": "wamid.LOCALTEST",
                                    "timestamp": "1750000000",
                                    "type": "text",
                                    "text": {"body": "ping from diagnostic"},
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }
    r2 = requests.post(f"{base}/webhook/whatsapp", json=payload, timeout=60)
    print("PUBLIC_POST", r2.status_code, repr(r2.text[:120]))


if __name__ == "__main__":
    main()
