from __future__ import annotations

from datetime import date, timedelta

from core.dates import parse_date
from db import repositories as repo

_COLD_START_THRESHOLD = 3
_PRICE_SPIKE_RATIO = 2.0
_PRICE_MIN_SAMPLES = 2
_QTY_MIN_SAMPLES = 2
_REORDER_WITHIN_DAYS = 30
_MATH_TOLERANCE_RATIO = 0.005
_MATH_TOLERANCE_ABS = 1.0


def _to_float(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _line_total(item: dict, *, apply_discount: bool = True) -> float:
    qty = _to_float(item.get("item_qty"))
    price = _to_float(item.get("item_price"))
    total = qty * price
    if apply_discount:
        disc = _to_float(item.get("item_discount"))
        if disc > 0:
            total *= max(0.0, 1.0 - disc / 100.0)
    return round(total, 2)


def _math_close(a: float, b: float) -> bool:
    if abs(a - b) <= _MATH_TOLERANCE_ABS:
        return True
    if b == 0:
        return a == 0
    return abs(a - b) / abs(b) <= _MATH_TOLERANCE_RATIO


def _finding(
    code: str,
    severity: str,
    message: str,
    *,
    needs_confirmation: bool = False,
    blocking: bool = False,
    chat_line: str | None = None,
) -> dict:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "needs_confirmation": needs_confirmation,
        "blocking": blocking,
        "chat_line": chat_line or message,
    }


def _math_audit_flags(extracted: dict) -> list[dict]:
    flags: list[dict] = []
    line_items = extracted.get("line_items") or []
    header_total = _to_float(extracted.get("total_amount"))

    if not line_items:
        return flags

    with_discount = sum(_line_total(it, apply_discount=True) for it in line_items)
    without_discount = sum(_line_total(it, apply_discount=False) for it in line_items)

    if header_total > 0 and not _math_close(with_discount, header_total):
        if any(_to_float(it.get("item_discount")) > 0 for it in line_items):
            if _math_close(without_discount, header_total):
                flags.append(
                    _finding(
                        "possible_missing_discount",
                        "medium",
                        "Line items show discounts but the invoice total looks like discount was not applied.",
                        needs_confirmation=True,
                        chat_line=(
                            "Some lines have a discount, but the total matches the pre-discount sum. "
                            "Please check the supplier applied the discount correctly."
                        ),
                    )
                )
            else:
                flags.append(
                    _finding(
                        "math_mismatch",
                        "high",
                        (
                            f"Line items sum to Rs. {with_discount:,.2f} (with discounts) "
                            f"but invoice total is Rs. {header_total:,.2f}."
                        ),
                        needs_confirmation=True,
                        chat_line=(
                            f"The maths does not add up — lines total about Rs. {with_discount:,.2f} "
                            f"but the invoice says Rs. {header_total:,.2f}. Please check before approving."
                        ),
                    )
                )
        else:
            flags.append(
                _finding(
                    "math_mismatch",
                    "high",
                    (
                        f"Line items sum to Rs. {with_discount:,.2f} "
                        f"but invoice total is Rs. {header_total:,.2f}."
                    ),
                    needs_confirmation=True,
                    chat_line=(
                        f"The line totals (Rs. {with_discount:,.2f}) do not match "
                        f"the invoice total (Rs. {header_total:,.2f}). Please double-check."
                    ),
                )
            )
    return flags


def _date_anomaly_flags(invoiced_date: str | None) -> list[dict]:
    if not invoiced_date:
        return []
    flags = []
    try:
        dt = parse_date(invoiced_date)
    except Exception:
        return [
            _finding(
                "bad_date",
                "high",
                "Invoice date format is invalid.",
            )
        ]

    today = date.today()
    if dt > today + timedelta(days=30):
        flags.append(
            _finding(
                "future_date",
                "high",
                "Invoice date is more than 30 days in the future.",
            )
        )
    if dt < today - timedelta(days=365):
        flags.append(
            _finding(
                "stale_date",
                "medium",
                "Invoice date is older than one year.",
            )
        )
    return flags


def _item_history_flags(
    dealer_id: int,
    item: dict,
    *,
    exclude_invoice_id: int | None = None,
) -> list[dict]:
    flags: list[dict] = []
    code = (item.get("item_code") or "").strip()
    name = (item.get("item_name") or "").strip()
    label = name or code or "item"
    if not code and not name:
        return flags

    qty = int(_to_float(item.get("item_qty")) or 0)
    price = _to_float(item.get("item_price"))

    stats = repo.get_dealer_item_history_stats(
        dealer_id, item_code=code or None, item_name=name or None
    )
    sample_count = int(stats.get("sample_count") or 0)
    avg_price = _to_float(stats.get("avg_price"))
    avg_qty = _to_float(stats.get("avg_qty"))
    max_qty = _to_float(stats.get("max_qty"))

    if sample_count >= _PRICE_MIN_SAMPLES and avg_price > 0 and price > avg_price * _PRICE_SPIKE_RATIO:
        flags.append(
            _finding(
                "item_price_spike",
                "medium",
                (
                    f"{label}: unit price Rs. {price:,.2f} is more than "
                    f"{_PRICE_SPIKE_RATIO:.0f}× the usual Rs. {avg_price:,.2f}."
                ),
                needs_confirmation=True,
                chat_line=(
                    f"{label} is priced higher than usual for this supplier "
                    f"(now Rs. {price:,.2f} vs about Rs. {avg_price:,.2f}). Worth a quick check."
                ),
            )
        )

    if sample_count >= _QTY_MIN_SAMPLES and avg_qty > 0:
        if qty >= avg_qty * 2 or (max_qty > 0 and qty > max_qty):
            usual = int(round(avg_qty))
            flags.append(
                _finding(
                    "qty_unusual",
                    "medium",
                    f"{label}: quantity {qty} vs usual ~{usual} per invoice from this supplier.",
                    needs_confirmation=True,
                    chat_line=(
                        f"You usually order about {usual} {label} on each invoice from this supplier — "
                        f"this one has {qty}. Please confirm that is correct."
                    ),
                )
            )

    recent = repo.find_recent_item_orders(
        dealer_id,
        item_code=code or None,
        item_name=name or None,
        within_days=_REORDER_WITHIN_DAYS,
        exclude_invoice_id=exclude_invoice_id,
    )
    if recent:
        prev = recent[0]
        inv_no = prev.get("invoice_no") or "?"
        inv_date = prev.get("invoiced_date") or "?"
        flags.append(
            _finding(
                "item_reordered_soon",
                "low",
                f"{label} was on invoice #{inv_no} on {inv_date} — confirm this repeat order is intended.",
                needs_confirmation=True,
                chat_line=(
                    f"{label} was ordered recently on invoice #{inv_no} ({inv_date}). "
                    f"Is this second order meant to be on the same invoice cycle?"
                ),
            )
        )

    return flags


def _line_item_flags(
    dealer_id: int,
    line_items: list,
    *,
    exclude_invoice_id: int | None = None,
) -> list[dict]:
    flags: list[dict] = []
    for item in line_items or []:
        flags.extend(
            _item_history_flags(dealer_id, item, exclude_invoice_id=exclude_invoice_id)
        )
    return flags


def _collect_findings(
    extracted: dict,
    dealer_id: int | None,
    *,
    exclude_invoice_id: int | None = None,
) -> list[dict]:
    findings: list[dict] = []
    invoice_no = (extracted.get("invoice_no") or "").strip()
    supplier_name = (extracted.get("supplier_name") or "").strip()
    amount = _to_float(extracted.get("total_amount"))

    findings.extend(_math_audit_flags(extracted))

    if supplier_name and amount <= 0:
        findings.append(
            _finding(
                "missing_amount",
                "high",
                "Supplier detected but invoice amount is missing or zero.",
            )
        )

    findings.extend(_date_anomaly_flags(extracted.get("invoiced_date")))

    if not dealer_id:
        if supplier_name:
            findings.append(
                _finding(
                    "unknown_dealer",
                    "low",
                    "Supplier is not matched to a known dealer yet — review line items carefully.",
                    chat_line="I could not match this supplier yet — please pick the correct dealer before approving.",
                )
            )
        return findings

    if invoice_no:
        existing = repo.find_invoice_by_no_and_dealer(
            invoice_no, dealer_id, exclude_invoice_id=exclude_invoice_id
        )
        if existing:
            findings.append(
                _finding(
                    "duplicate_invoice_no",
                    "high",
                    f"Invoice number {invoice_no} already exists for this dealer.",
                    blocking=True,
                    chat_line=(
                        f"Invoice number {invoice_no} already exists for this dealer — "
                        "unlike other warnings, this cannot be confirmed through. "
                        "Please change the invoice number before saving."
                    ),
                )
            )

    stats = repo.get_dealer_invoice_stats(dealer_id)
    invoice_count = int(stats.get("count") or 0)
    avg_amount = _to_float(stats.get("avg_amount"))
    if invoice_count >= _COLD_START_THRESHOLD and avg_amount > 0 and amount > avg_amount * 3:
        findings.append(
            _finding(
                "amount_outlier",
                "medium",
                "Invoice amount is more than 3x this dealer's historical average.",
                needs_confirmation=True,
                chat_line=(
                    f"This invoice total (Rs. {amount:,.2f}) is much higher than usual "
                    f"for this supplier (avg about Rs. {avg_amount:,.2f})."
                ),
            )
        )

    findings.extend(
        _line_item_flags(
            dealer_id,
            extracted.get("line_items") or [],
            exclude_invoice_id=exclude_invoice_id,
        )
    )

    return findings


def _flags_to_risk(flags: list[dict]) -> str:
    if any(f.get("severity") == "high" for f in flags):
        return "HIGH"
    if any(f.get("severity") == "medium" for f in flags):
        return "MEDIUM"
    return "LOW"


def _has_history_for_items(dealer_id: int, line_items: list) -> bool:
    for item in line_items or []:
        code = (item.get("item_code") or "").strip()
        name = (item.get("item_name") or "").strip()
        if not code and not name:
            continue
        stats = repo.get_dealer_item_history_stats(
            dealer_id, item_code=code or None, item_name=name or None
        )
        if int(stats.get("sample_count") or 0) >= _QTY_MIN_SAMPLES:
            return True
    return False


def _build_remark(status: str, findings: list[dict], dealer_id: int | None) -> str:
    if status == "GOOD_TO_GO":
        return "Nothing unusual stood out on this invoice."
    if status == "INSUFFICIENT_DATA" and not findings:
        if not dealer_id:
            return "Limited supplier history — please review amounts and line items yourself."
        return (
            "Not enough past invoices to compare every line item yet — "
            "math and basic checks still ran."
        )
    messages = [f.get("message", "") for f in findings if f.get("message")]
    if not messages:
        return "Some checks flagged possible issues — please review before approving."
    return " ".join(messages[:3])


def build_agent2_chat_messages(audit: dict) -> list[dict]:
    """Rule-based friendly chat lines for the verify review panel."""
    status = audit.get("status") or "GOOD_TO_GO"
    findings = audit.get("findings") or []
    messages: list[dict] = []

    messages.append(
        {
            "role": "agent2",
            "content": (
                "Hi — I checked this invoice against your past orders and the line-item maths."
            ),
        }
    )

    if status == "GOOD_TO_GO":
        messages.append(
            {
                "role": "agent2",
                "content": "Everything looks normal. Still give the image a quick look before you approve.",
            }
        )
        return messages

    if status == "INSUFFICIENT_DATA" and not findings:
        messages.append(
            {
                "role": "agent2",
                "content": (
                    "We do not have much history for this supplier yet, so I could not compare "
                    "quantities to past orders. Please verify amounts yourself."
                ),
            }
        )
        return messages

    blocking_lines = [f for f in findings if f.get("blocking")]
    confirm_lines = [f for f in findings if f.get("needs_confirmation") and not f.get("blocking")]
    other_lines = [f for f in findings if not f.get("needs_confirmation") and not f.get("blocking")]

    for f in blocking_lines:
        messages.append({"role": "agent2", "content": f.get("chat_line") or f.get("message", "")})

    for f in confirm_lines[:5]:
        messages.append({"role": "agent2", "content": f.get("chat_line") or f.get("message", "")})

    for f in other_lines[:3]:
        messages.append({"role": "agent2", "content": f.get("message", "")})

    if confirm_lines:
        messages.append(
            {
                "role": "agent2",
                "content": (
                    "Those are warnings only — you can still approve if everything is correct. "
                    "Tick confirm matches when you are satisfied."
                ),
            }
        )

    if blocking_lines:
        messages.append(
            {
                "role": "agent2",
                "content": (
                    "The invoice number issue above is a hard stop — confirm matches will not "
                    "let it through until the invoice number is changed."
                ),
            }
        )

    return messages


def _resolve_status(findings: list[dict], dealer_id: int | None, extracted: dict) -> str:
    if findings:
        return "ISSUE_DETECTED"
    if dealer_id:
        inv_count = int((repo.get_dealer_invoice_stats(dealer_id) or {}).get("count") or 0)
        line_items = extracted.get("line_items") or []
        if inv_count < _COLD_START_THRESHOLD and not _has_history_for_items(dealer_id, line_items):
            return "INSUFFICIENT_DATA"
    return "GOOD_TO_GO"


def audit_invoice(
    extracted: dict,
    dealer_id: int | None,
    *,
    exclude_invoice_id: int | None = None,
) -> dict:
    """Agent 2 contract: status, risk_level, remark, findings, chat_messages."""
    findings = _collect_findings(
        extracted, dealer_id, exclude_invoice_id=exclude_invoice_id
    )
    status = _resolve_status(findings, dealer_id, extracted)
    risk = "LOW" if status in ("GOOD_TO_GO", "INSUFFICIENT_DATA") else _flags_to_risk(findings)
    if status == "ISSUE_DETECTED":
        risk = _flags_to_risk(findings)

    audit = {
        "status": status,
        "risk_level": risk,
        "remark": _build_remark(status, findings, dealer_id),
        "findings": findings,
    }
    audit["chat_messages"] = build_agent2_chat_messages(audit)
    return audit


def check_invoice_anomalies(
    extracted: dict,
    dealer_id: int | None,
    *,
    exclude_invoice_id: int | None = None,
) -> list[dict]:
    """Backward-compatible list for UI bullet lists and integrations."""
    findings = _collect_findings(
        extracted, dealer_id, exclude_invoice_id=exclude_invoice_id
    )
    return [
        {
            "code": f.get("code"),
            "severity": f.get("severity"),
            "message": f.get("message"),
            "blocking": f.get("blocking", False),
        }
        for f in findings
    ]
