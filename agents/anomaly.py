from __future__ import annotations

from datetime import date, timedelta

from core.dates import parse_date
from db import repositories as repo


def _to_float(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _date_anomaly_flags(invoiced_date: str | None) -> list[dict]:
    if not invoiced_date:
        return []
    flags = []
    try:
        dt = parse_date(invoiced_date)
    except Exception:
        return [{"code": "bad_date", "severity": "high", "message": "Invoice date format is invalid."}]

    today = date.today()
    if dt > today + timedelta(days=30):
        flags.append(
            {
                "code": "future_date",
                "severity": "high",
                "message": "Invoice date is more than 30 days in the future.",
            }
        )
    if dt < today - timedelta(days=365):
        flags.append(
            {
                "code": "stale_date",
                "severity": "medium",
                "message": "Invoice date is older than one year.",
            }
        )
    return flags


def check_invoice_anomalies(extracted: dict, dealer_id: int | None) -> list[dict]:
    anomalies: list[dict] = []
    invoice_no = (extracted.get("invoice_no") or "").strip()
    supplier_name = (extracted.get("supplier_name") or "").strip()
    amount = _to_float(extracted.get("total_amount"))

    if supplier_name and amount <= 0:
        anomalies.append(
            {
                "code": "missing_amount",
                "severity": "high",
                "message": "Supplier detected but invoice amount is missing or zero.",
            }
        )

    anomalies.extend(_date_anomaly_flags(extracted.get("invoiced_date")))

    if dealer_id and invoice_no:
        existing = repo.find_invoice_by_no_and_dealer(invoice_no, dealer_id)
        if existing:
            anomalies.append(
                {
                    "code": "duplicate_invoice_no",
                    "severity": "high",
                    "message": f"Invoice number {invoice_no} already exists for this dealer.",
                }
            )
        stats = repo.get_dealer_invoice_stats(dealer_id)
        avg_amount = _to_float(stats.get("avg_amount"))
        if avg_amount > 0 and amount > avg_amount * 3:
            anomalies.append(
                {
                    "code": "amount_outlier",
                    "severity": "medium",
                    "message": "Invoice amount is more than 3x this dealer's historical average.",
                }
            )

    return anomalies
