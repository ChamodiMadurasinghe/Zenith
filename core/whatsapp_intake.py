"""WhatsApp image inbox and Gemini extraction for pending invoices."""

from __future__ import annotations

import json
from datetime import date

from config import Config
from core.dates import format_date
from core.ingestion_helpers import dealer_setup_from_extraction
from db import repositories as repo


def _normalize_extracted(extracted: dict) -> dict:
    supplier = (extracted.get("supplier_name") or "").strip()
    invoice_no = (extracted.get("invoice_no") or "").strip()
    invoiced_date = extracted.get("invoiced_date")
    if not invoiced_date:
        invoiced_date = format_date(date.today())
    try:
        total_amount = float(extracted.get("total_amount") or 0)
    except (TypeError, ValueError):
        total_amount = 0.0
    try:
        credit_period_days = int(
            extracted.get("credit_period_days") or Config.DEFAULT_CREDIT_PERIOD_DAYS
        )
    except (TypeError, ValueError):
        credit_period_days = Config.DEFAULT_CREDIT_PERIOD_DAYS
    line_items = extracted.get("line_items") or []
    return {
        "supplier_name": supplier or "Unknown",
        "invoice_no": invoice_no or "PENDING",
        "invoiced_date": invoiced_date,
        "total_amount": total_amount,
        "credit_period_days": credit_period_days,
        "line_items": line_items,
        "date_was_missing": not extracted.get("invoiced_date"),
    }


def extract_image_to_pending_invoice(
    location_path: str,
    *,
    local_path: str | None = None,
    sender_phone: str | None = None,
    delivery_date: str | None = None,
) -> int:
    """Run Agent 1 (Gemini) on a stored image and save as pending verification."""
    from agents.anomaly import check_invoice_anomalies
    from agents.ingestion import extract_invoice

    image_path = local_path or str(Config.UPLOAD_FOLDER / location_path.split("/")[-1])
    raw = extract_invoice(image_path)
    extracted = _normalize_extracted(raw)
    dealer_setup = dealer_setup_from_extraction(raw)
    dealer = (
        repo.find_dealer_by_name(extracted["supplier_name"])
        if extracted["supplier_name"] != "Unknown"
        else None
    )
    dealer_id = dealer["dealer_id"] if dealer else repo.get_pending_supplier_dealer_id()

    try:
        anomalies = check_invoice_anomalies(extracted, dealer["dealer_id"] if dealer else None)
    except Exception:
        anomalies = []

    items = extracted["line_items"] or [
        {
            "item_code": "",
            "item_name": "WhatsApp intake",
            "item_qty": 1,
            "item_price": extracted["total_amount"] or 1,
            "item_discount": 0,
        }
    ]
    pending_payload = {
        **dealer_setup,
        "anomalies": anomalies,
        "whatsapp_sender": sender_phone,
        "source": "whatsapp",
    }
    delivery = (delivery_date or "").strip() or format_date(date.today())
    return repo.save_pending_invoice(
        {
            "invoice_no": extracted["invoice_no"],
            "invoiced_date": extracted["invoiced_date"],
            "delivery_date": delivery,
            "credit_period_days": extracted["credit_period_days"],
            "total_amount": extracted["total_amount"],
            "location_path": location_path,
        },
        items,
        dealer_id,
        pending_dealer_json=json.dumps(pending_payload),
    )


WHATSAPP_INBOX_REPLY = (
    "Photo received!\n\n"
    "Open the Zenith web app, go to Invoices → WhatsApp inbox, "
    "then tap Send to AI when you are ready to read the details."
)
