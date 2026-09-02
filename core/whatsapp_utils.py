"""Shared WhatsApp phone normalization for local bridge intake."""

from __future__ import annotations


def normalize_whatsapp_phone(phone: str) -> str:
    """Canonical +E.164 style used for sessions and allow-lists."""
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if not digits:
        return (phone or "").strip()
    # Sri Lanka local mobile: 0771234567 → 94771234567
    if digits.startswith("0") and len(digits) == 10:
        digits = "94" + digits[1:]
    return f"+{digits}"
