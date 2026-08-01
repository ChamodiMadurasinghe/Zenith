"""Shared helpers for invoice/cheque extraction and dealer setup."""

PENDING_SUPPLIER_NAME = "Pending Supplier"

_DEALER_DEFAULTS = {
    "dealer_strictness": "Medium",
    "casual_days": 3,
    "impossible_days": "Sunday",
}


def _clean(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def dealer_setup_from_extraction(extracted: dict) -> dict:
    """Map Gemini supplier_* fields to dealer_setup keys used by templates."""
    supplier_name = _clean(extracted.get("supplier_name"))
    setup = {
        "dealer_name": supplier_name,
        "dealer_email": _clean(extracted.get("supplier_email")),
        "dealer_telno": _clean(extracted.get("supplier_phone")),
        "dealer_address": _clean(extracted.get("supplier_address")),
        "bank_name": _clean(extracted.get("supplier_bank_name")),
        "account_name": _clean(extracted.get("supplier_account_name")) or supplier_name,
        "branch_name": _clean(extracted.get("supplier_branch")),
    }
    setup.update(_DEALER_DEFAULTS)
    return setup


def merge_dealer_setup(primary: dict, secondary: dict | None) -> dict:
    """Merge two dealer_setup dicts; primary (invoice extraction) wins when set."""
    merged = dict(_DEALER_DEFAULTS)
    if secondary:
        merged.update({k: v for k, v in secondary.items() if v not in (None, "")})
    merged.update({k: v for k, v in primary.items() if v not in (None, "")})
    if not merged.get("account_name"):
        merged["account_name"] = merged.get("dealer_name") or ""
    return merged
