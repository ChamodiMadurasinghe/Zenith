"""Invoice amount parts for multi-cheque payment of one invoice."""

from __future__ import annotations

import copy
from typing import Any


def is_split_part(inv: dict | None) -> bool:
    if not inv:
        return False
    return int(inv.get("part_count") or 1) > 1 and inv.get("part_index") is not None


def part_key(inv: dict) -> str:
    iid = int(inv["invoices_id"])
    if is_split_part(inv):
        return f"{iid}:{int(inv['part_index'])}"
    return str(iid)


def parse_part_key(key: str | int) -> tuple[int, int | None]:
    s = str(key)
    if ":" in s:
        left, right = s.split(":", 1)
        return int(left), int(right)
    return int(s), None


def display_invoice_no(inv: dict) -> str:
    base = (inv.get("invoice_no") or f"#{inv.get('invoices_id')}").strip()
    if is_split_part(inv):
        return f"{base} · {int(inv['part_index'])}"
    return base


def original_amount(inv: dict) -> float:
    if inv.get("original_amount") is not None:
        return float(inv["original_amount"])
    return float(inv.get("total_amount") or 0)


def apply_part_fields(inv: dict, *, amount: float, part_index: int, part_count: int, original: float) -> dict:
    out = dict(inv)
    out["total_amount"] = round(float(amount), 2)
    out["part_index"] = int(part_index)
    out["part_count"] = int(part_count)
    out["original_amount"] = round(float(original), 2)
    out["invoice_no_display"] = display_invoice_no(out)
    return out


def equal_part_amounts(total: float, num_parts: int) -> list[float]:
    n = int(num_parts)
    if n < 2:
        raise ValueError("num_parts must be at least 2")
    total = round(float(total), 2)
    base = round(total / n, 2)
    amounts = [base] * n
    # Fix rounding on last part so sum matches
    amounts[-1] = round(total - sum(amounts[:-1]), 2)
    if any(a <= 0 for a in amounts):
        raise ValueError("Part amounts must be positive")
    return amounts


def make_split_parts(inv: dict, amounts: list[float]) -> list[dict]:
    amounts = [round(float(a), 2) for a in amounts]
    if len(amounts) < 2:
        raise ValueError("Need at least two part amounts")
    if any(a <= 0 for a in amounts):
        raise ValueError("Each part amount must be greater than zero")
    orig = original_amount(inv) if is_split_part(inv) else float(inv["total_amount"])
    if abs(sum(amounts) - orig) > 0.02:
        raise ValueError(
            f"Part amounts Rs. {sum(amounts):,.2f} must equal invoice total Rs. {orig:,.2f}"
        )
    parts = []
    for i, amt in enumerate(amounts, start=1):
        parts.append(apply_part_fields(inv, amount=amt, part_index=i, part_count=len(amounts), original=orig))
    return parts


def find_invoice_in_bundles(
    bundles: list,
    invoice_id: int,
    part_index: int | None = None,
) -> tuple[int, int, dict] | None:
    """Return (bundle_idx, invoice_idx, inv) or None."""
    for bi, bundle in enumerate(bundles or []):
        for ii, inv in enumerate(bundle.get("invoices") or []):
            if int(inv["invoices_id"]) != int(invoice_id):
                continue
            if part_index is None:
                return bi, ii, inv
            if is_split_part(inv) and int(inv.get("part_index") or 0) == int(part_index):
                return bi, ii, inv
            if not is_split_part(inv) and part_index in (None, 0, 1):
                return bi, ii, inv
    return None


def collect_parts_of_invoice(bundles: list, invoice_id: int) -> list[dict]:
    found = []
    for bundle in bundles or []:
        for inv in bundle.get("invoices") or []:
            if int(inv["invoices_id"]) == int(invoice_id):
                found.append(inv)
    return found


def remove_invoice_occurrences(
    bundles: list,
    invoice_id: int,
    part_index: int | None = None,
) -> dict | None:
    """Remove matching invoice/part from bundles. Returns one removed copy (or None)."""
    removed = None
    for bundle in bundles or []:
        kept = []
        for inv in bundle.get("invoices") or []:
            if int(inv["invoices_id"]) != int(invoice_id):
                kept.append(inv)
                continue
            if part_index is not None:
                if is_split_part(inv) and int(inv.get("part_index") or 0) == int(part_index):
                    removed = inv
                    continue
                if not is_split_part(inv) and int(part_index) == 1:
                    removed = inv
                    continue
                kept.append(inv)
            else:
                removed = inv
                # drop all parts of this invoice when part_index is None
        bundle["invoices"] = kept
        bundle["total_lkr"] = sum(float(i["total_amount"]) for i in kept)
    return removed


def slim_invoice_meta(inv: dict) -> dict[str, Any]:
    meta: dict[str, Any] = {"invoices_id": int(inv["invoices_id"])}
    if is_split_part(inv):
        meta.update(
            {
                "total_amount": float(inv["total_amount"]),
                "part_index": int(inv["part_index"]),
                "part_count": int(inv["part_count"]),
                "original_amount": original_amount(inv),
                "invoice_no": inv.get("invoice_no"),
            }
        )
    return meta


def hydrate_invoice_from_meta(row: dict, meta: dict) -> dict:
    inv = dict(row)
    if meta.get("part_count") and int(meta["part_count"]) > 1:
        return apply_part_fields(
            inv,
            amount=float(meta["total_amount"]),
            part_index=int(meta["part_index"]),
            part_count=int(meta["part_count"]),
            original=float(meta.get("original_amount") or row["total_amount"]),
        )
    return inv


def parts_payload_from_bundles(bundles: list) -> dict[str, dict]:
    """Map part_key → meta for manual rebuild."""
    out = {}
    for bundle in bundles or []:
        for inv in bundle.get("invoices") or []:
            if is_split_part(inv):
                out[part_key(inv)] = slim_invoice_meta(inv)
    return out
