"""Lightweight Gemini vision check — is this image a business invoice/cheque?"""

from __future__ import annotations

from agents.base import generate_with_image
from config import Config

SYSTEM = """You classify business document photos for a Sri Lankan shop.
Return JSON with keys:
- is_invoice (bool): true if the image is a supplier invoice, bill, or payment cheque
- document_type (string): one of invoice, cheque, receipt, photo, sticker, other
- confidence (number 0-1)
- reason (short string)

Only set is_invoice true for supplier invoices, bills, or cheques used for payment."""


def classify_document(image_path: str) -> dict:
    if Config.use_fake_ai():
        return {
            "is_invoice": True,
            "document_type": "invoice",
            "confidence": 0.99,
            "reason": "mock classifier",
        }
    return generate_with_image(
        "Classify this image.",
        image_path,
        SYSTEM,
    )


def is_business_document(classification: dict) -> bool:
    if classification.get("is_invoice"):
        return True
    doc_type = (classification.get("document_type") or "").strip().lower()
    return doc_type in {"invoice", "cheque"}
