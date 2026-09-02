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


def _form_at(values: list, index: int, default: str = "") -> str:
    if index < len(values):
        return values[index]
    return default


def coerce_item_qty(value) -> int:
    try:
        return max(0, int(float(value if value not in (None, "") else 1)))
    except (TypeError, ValueError):
        return 1


def coerce_item_money(value, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def compute_item_line_total(qty, unit_price, discount_pct) -> float:
    total = float(qty or 0) * float(unit_price or 0)
    disc = float(discount_pct or 0)
    if disc > 0:
        total *= max(0.0, 1.0 - disc / 100.0)
    return round(total, 2)


def normalize_line_item(item: dict) -> dict:
    qty = coerce_item_qty(item.get("item_qty"))
    price = coerce_item_money(item.get("item_price"))
    disc = coerce_item_money(item.get("item_discount"))
    mrp = coerce_item_money(item.get("item_mrp"))
    raw_total = item.get("item_line_total")
    line_total = (
        compute_item_line_total(qty, price, disc)
        if raw_total in (None, "")
        else coerce_item_money(raw_total)
    )
    return {
        "item_code": _clean(item.get("item_code")),
        "item_name": _clean(item.get("item_name")),
        "item_qty": qty,
        "item_price": price,
        "item_discount": disc,
        "item_mrp": mrp,
        "item_line_total": line_total,
    }


def parse_items_from_form(form) -> list[dict]:
    """Read invoice line rows from a save/verify form (code, qty, MRP, price, discount, total)."""
    codes = form.getlist("item_code")
    names = form.getlist("item_name")
    qtys = form.getlist("item_qty")
    prices = form.getlist("item_price")
    discounts = form.getlist("item_discount")
    mrps = form.getlist("item_mrp")
    totals = form.getlist("item_line_total")
    n = max(len(codes), len(names), len(qtys), len(prices), len(discounts), len(mrps), len(totals), 0)
    items = []
    for i in range(n):
        code = _form_at(codes, i).strip()
        name = _form_at(names, i).strip()
        if not code and not name:
            continue
        items.append(
            normalize_line_item(
                {
                    "item_code": code,
                    "item_name": name,
                    "item_qty": _form_at(qtys, i, "1"),
                    "item_price": _form_at(prices, i, "0"),
                    "item_discount": _form_at(discounts, i, "0"),
                    "item_mrp": _form_at(mrps, i, "0"),
                    "item_line_total": _form_at(totals, i, ""),
                }
            )
        )
    return items


def merge_dealer_setup(primary: dict, secondary: dict | None) -> dict:
    """Merge two dealer_setup dicts; primary (invoice extraction) wins when set."""
    merged = dict(_DEALER_DEFAULTS)
    if secondary:
        merged.update({k: v for k, v in secondary.items() if v not in (None, "")})
    merged.update({k: v for k, v in primary.items() if v not in (None, "")})
    if not merged.get("account_name"):
        merged["account_name"] = merged.get("dealer_name") or ""
    return merged
