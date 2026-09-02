"""Build dealer payment pattern documents from committed cheque history."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from statistics import median

from config import Config
from db import repositories as repo


def _parse_date(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _aging_days(invoiced_date: str | None, clearance_date: str | None) -> int | None:
    inv = _parse_date(invoiced_date)
    clr = _parse_date(clearance_date)
    if not inv or not clr:
        return None
    return (clr - inv).days


def _distinct_invoice_ids(invoices: list[dict]) -> set[int]:
    return {int(i["invoices_id"]) for i in invoices if i.get("invoices_id") is not None}


def _bundling_behavior_label(bundled_count: int, unbundled_count: int) -> str:
    if bundled_count > 0 and unbundled_count > 0:
        return "mixed"
    if bundled_count > 0:
        return "frequently_bundled"
    if unbundled_count > 0:
        return "paid_individually"
    return "no_history"


def _invoice_label(inv: dict) -> str:
    no = inv.get("invoice_no") or "?"
    part_index = int(inv.get("part_index") or 1)
    part_count = int(inv.get("part_count") or 1)
    if part_count > 1:
        return f"Inv #{no} (part {part_index}/{part_count})"
    return f"Inv #{no}"


def _analyze_split_patterns(
    history: list[dict],
    *,
    large_bill_lkr: float,
) -> list[str]:
    """Detect large-bill split patterns across cheques."""
    by_invoice: dict[int, list[dict]] = defaultdict(list)
    for ch in history:
        clearance = ch.get("clearance_date")
        for inv in ch.get("invoices") or []:
            inv_id = inv.get("invoices_id")
            if inv_id is None:
                continue
            by_invoice[int(inv_id)].append(
                {
                    "cheque_id": ch.get("cheque_id"),
                    "clearance_date": clearance,
                    "part_index": int(inv.get("part_index") or 1),
                    "part_count": int(inv.get("part_count") or 1),
                    "total_amount": float(inv.get("total_amount") or 0),
                    "invoice_no": inv.get("invoice_no"),
                }
            )

    examples: list[tuple[int, int, float]] = []
    for rows in by_invoice.values():
        if len(rows) < 2:
            continue
        total_amount = max(r["total_amount"] for r in rows)
        if total_amount < large_bill_lkr:
            continue
        part_count = max(r["part_count"] for r in rows)
        if part_count < 2:
            continue
        dates = sorted(
            d
            for d in (_parse_date(r["clearance_date"]) for r in rows)
            if d is not None
        )
        if len(dates) < 2:
            continue
        gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        gap = int(median(gaps)) if gaps else 0
        examples.append((part_count, gap, total_amount))

    if len(examples) < 2:
        return []

    part_counts = [e[0] for e in examples]
    gaps = [e[1] for e in examples]
    typical_parts = int(round(median(part_counts)))
    typical_gap = int(round(median(gaps)))
    threshold_k = int(large_bill_lkr / 1000)
    return [
        f"Bills over {threshold_k}k LKR are usually split into {typical_parts} parts "
        f"with a {typical_gap}-day clearance gap."
    ]


def build_dealer_pattern_metadata(dealer_id: int) -> dict:
    """Metadata for vector store indexing."""
    doc = _analyze_history(dealer_id)
    return {
        "dealer_id": dealer_id,
        "updated_at": date.today().isoformat(),
        "bundling_behavior": doc.get("bundling_behavior", "no_history"),
    }


def build_dealer_pattern_document(dealer_id: int) -> str:
    """Format semantic payment history document for a dealer."""
    doc = _analyze_history(dealer_id)
    dealer = repo.get_dealer(dealer_id) or {}
    dealer_name = dealer.get("dealer_name") or f"Dealer {dealer_id}"

    if doc.get("bundling_behavior") == "no_history":
        return (
            f"Dealer: {dealer_name} (ID: {dealer_id})\n"
            "Bundling History: no_history\n\n"
            "No committed cheque payment history recorded yet."
        )

    lines = [
        f"Dealer: {dealer_name} (ID: {dealer_id})",
        f"Bundling History: {doc['bundling_behavior']}",
        "",
        "Aging Analysis:",
    ]

    if doc.get("bundled_avg_aging") is not None:
        lines.append(
            f"- Bundled Invoices Average Aging: {doc['bundled_avg_aging']:.0f} days "
            f"(calculated across {doc['bundled_cheque_count']} multi-invoice cheques, "
            f"{doc['bundled_invoice_count']} invoice rows)."
        )

    unbundled_lines = doc.get("unbundled_aging_lines") or []
    if unbundled_lines:
        lines.append(f"- Unbundled Invoice Records: {', '.join(unbundled_lines)}.")
    elif doc.get("bundling_behavior") == "paid_individually":
        lines.append("- Unbundled Invoice Records: none recorded.")

    lines.append("")
    pref = doc.get("preferred_account")
    if pref:
        lines.append(
            f"Preferred Paying Account: {pref['bank_name']} "
            f"(Acc ID: {pref['acc_id']}) used for {pref['count']} out of "
            f"{pref['total']} past cheques ({pref['pct']:.0f}%)."
        )
    else:
        lines.append("Preferred Paying Account: not enough history.")

    patterns = doc.get("payment_patterns") or []
    if patterns:
        lines.append("Payment Pattern: " + " ".join(patterns))

    return "\n".join(lines)


def _analyze_history(dealer_id: int) -> dict:
    history = repo.get_dealer_committed_payment_history(dealer_id)
    if not history:
        return {"bundling_behavior": "no_history"}

    bundled_cheques: list[dict] = []
    unbundled_records: list[dict] = []
    account_counts: Counter[int] = Counter()

    invoice_cheque_map: dict[int, set[int]] = defaultdict(set)

    for ch in history:
        acc_id = int(ch.get("user_bank_acc_id") or 0)
        if acc_id:
            account_counts[acc_id] += 1

        invoices = ch.get("invoices") or []
        distinct = _distinct_invoice_ids(invoices)
        for inv_id in distinct:
            invoice_cheque_map[inv_id].add(int(ch.get("cheque_id") or 0))

        if len(distinct) >= 2:
            bundled_cheques.append(ch)
        elif len(distinct) == 1:
            inv = invoices[0]
            unbundled_records.append({"cheque": ch, "invoice": inv})

    split_invoice_ids = {inv_id for inv_id, cids in invoice_cheque_map.items() if len(cids) >= 2}

    bundled_aging_values: list[int] = []
    for ch in bundled_cheques:
        clearance = ch.get("clearance_date")
        for inv in ch.get("invoices") or []:
            days = _aging_days(inv.get("invoiced_date"), clearance)
            if days is not None:
                bundled_aging_values.append(days)

    unbundled_aging_lines: list[str] = []
    for rec in unbundled_records:
        inv = rec["invoice"]
        ch = rec["cheque"]
        inv_id = int(inv.get("invoices_id") or 0)
        days = _aging_days(inv.get("invoiced_date"), ch.get("clearance_date"))
        if days is None:
            continue
        label = _invoice_label(inv)
        unbundled_aging_lines.append(f"{label} ({days} days aging)")

    bundled_count = len(bundled_cheques)
    unbundled_count = len(unbundled_records)
    behavior = _bundling_behavior_label(bundled_count, unbundled_count)

    preferred_account = None
    if account_counts:
        total = sum(account_counts.values())
        acc_id, count = account_counts.most_common(1)[0]
        acc = repo.get_bank_account(acc_id)
        preferred_account = {
            "acc_id": acc_id,
            "bank_name": (acc or {}).get("bank_name") or f"Account {acc_id}",
            "count": count,
            "total": total,
            "pct": (count / total) * 100 if total else 0,
        }

    large_bill_lkr = Config.pattern_large_bill_lkr()
    payment_patterns = _analyze_split_patterns(history, large_bill_lkr=large_bill_lkr)

    result: dict = {
        "bundling_behavior": behavior,
        "bundled_cheque_count": bundled_count,
        "unbundled_cheque_count": unbundled_count,
        "bundled_invoice_count": len(bundled_aging_values),
        "unbundled_aging_lines": unbundled_aging_lines,
        "preferred_account": preferred_account,
        "payment_patterns": payment_patterns,
        "split_invoice_ids": split_invoice_ids,
    }

    if bundled_aging_values:
        result["bundled_avg_aging"] = sum(bundled_aging_values) / len(bundled_aging_values)
    else:
        result["bundled_avg_aging"] = None

    return result
