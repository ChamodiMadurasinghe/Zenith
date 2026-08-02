from datetime import date, timedelta

from config import Config
from core.cheque_batcher import audit_bundle_day_limits
from core.dates import add_business_days, format_date, parse_date
from core.liquidity_engine import apply_liquidity_dates, is_interbank
from db import repositories as repo


def invoice_due_date(invoice: dict) -> date:
    inv_date = parse_date(invoice["invoiced_date"])
    return inv_date + timedelta(days=int(invoice["credit_period_days"]))


def _merchant_bank_name(dealer_id: int | None = None) -> str:
    acc_id = repo.paying_account_id_for_dealer(dealer_id)
    acc = repo.get_bank_account(acc_id)
    return acc["bank_name"] if acc else ""


def enrich_bundle_liquidity(bundle: dict, dealer_id: int, holidays: set) -> dict:
    dealer_bank = repo.get_dealer_preferred_bank(dealer_id)
    interbank = is_interbank(
        _merchant_bank_name(dealer_id),
        dealer_bank["bank_name"] if dealer_bank else "",
    )
    dates = apply_liquidity_dates(bundle["cheque_date"], holidays, is_interbank=interbank)
    bundle.update(dates)
    return bundle


def recalculate_all_bundles(bundles: list, dealer_id: int) -> list:
    holidays = repo.get_holidays()
    for b in bundles:
        enrich_bundle_liquidity(b, dealer_id, holidays)
    return bundles


def compute_bundles(dealer_id: int, invoice_ids: list, ceiling_lkr: float) -> list:
    dealer = repo.get_dealer(dealer_id)
    holidays = repo.get_holidays()
    impossible = dealer.get("impossible_days", "") if dealer else ""
    casual = int(dealer.get("casual_days") or 0)
    today = date.today()
    account_id = repo.paying_account_id_for_dealer(dealer_id)

    from db.connection import query_one

    invoices = []
    for inv_id in invoice_ids:
        inv = query_one("SELECT * FROM invoices WHERE invoices_id = ?", (inv_id,))
        if inv:
            invoices.append(inv)

    invoices.sort(key=invoice_due_date)

    bundles = []
    current = {"invoices": [], "total": 0.0}

    for inv in invoices:
        amt = float(inv["total_amount"])
        if amt > ceiling_lkr:
            if current["invoices"]:
                bundles.append(current)
                current = {"invoices": [], "total": 0.0}
            bundles.append({"invoices": [inv], "total": amt})
            continue
        if current["total"] + amt > ceiling_lkr:
            bundles.append(current)
            current = {"invoices": [inv], "total": amt}
        else:
            current["invoices"].append(inv)
            current["total"] += amt

    if current["invoices"]:
        bundles.append(current)

    result = []
    for i, bundle in enumerate(bundles):
        if not bundle["invoices"]:
            continue
        last_due = max(invoice_due_date(inv) for inv in bundle["invoices"])
        cheque_date = add_business_days(last_due, casual, holidays, impossible)
        if cheque_date < today:
            cheque_date = add_business_days(today, 1, holidays, impossible)
        entry = {
            "group": i + 1,
            "invoices": bundle["invoices"],
            "total_lkr": bundle["total"],
            "cheque_date": format_date(cheque_date),
        }
        enrich_bundle_liquidity(entry, dealer_id, holidays)
        result.append(entry)

    audit_bundle_day_limits(
        result, casual_limit=Config.CASUAL_DAILY_LIMIT_LKR, account_id=account_id
    )
    return result


def _default_empty_cheque_date(
    today: date, casual: int, holidays: set, impossible: str
) -> str:
    cd = add_business_days(today, 1, holidays, impossible)
    if casual:
        cd = add_business_days(cd, casual, holidays, impossible)
    return format_date(cd)


def build_bundles_from_assignments(
    dealer_id: int,
    invoice_assignments: dict,
    cheque_dates: dict,
    ceiling_lkr: float,
    enforce_ceiling: bool = True,
    empty_groups: list | None = None,
    invoice_parts: dict | None = None,
) -> list:
    """Build bundles from manual invoice-to-group assignments.

    invoice_assignments keys may be \"12\" or \"12:1\" (split part).
    invoice_parts maps those keys to amount/part metadata.
    """
    from db.connection import query_one

    from core.invoice_parts import hydrate_invoice_from_meta, parse_part_key

    parts_map = {str(k): v for k, v in (invoice_parts or {}).items()}
    groups: dict[int, list] = {}
    for inv_key, group_no in invoice_assignments.items():
        key = str(inv_key)
        inv_id, _part_idx = parse_part_key(key)
        group_no = int(group_no)
        row = query_one("SELECT * FROM invoices WHERE invoices_id = ?", (inv_id,))
        if not row:
            continue
        meta = parts_map.get(key) or {}
        inv = hydrate_invoice_from_meta(row, meta) if meta.get("part_count") else dict(row)
        groups.setdefault(group_no, []).append(inv)

    empty_set = {int(g) for g in (empty_groups or [])}
    all_group_nos = set(groups.keys()) | empty_set

    holidays = repo.get_holidays()
    dealer = repo.get_dealer(dealer_id)
    impossible = dealer.get("impossible_days", "") if dealer else ""
    casual = int(dealer.get("casual_days") or 0)
    today = date.today()

    result = []
    for idx, group_no in enumerate(sorted(all_group_nos)):
        invs = groups.get(group_no, [])
        if not invs and group_no not in empty_set:
            continue
        total = sum(float(inv["total_amount"]) for inv in invs)
        if invs and enforce_ceiling and total > ceiling_lkr:
            continue
        if str(group_no) in cheque_dates:
            cheque_date_str = cheque_dates[str(group_no)]
        elif group_no in cheque_dates:
            cheque_date_str = cheque_dates[group_no]
        elif invs:
            last_due = max(invoice_due_date(inv) for inv in invs)
            cd = add_business_days(last_due, casual, holidays, impossible)
            if cd < today:
                cd = add_business_days(today, 1, holidays, impossible)
            cheque_date_str = format_date(cd)
        else:
            cheque_date_str = _default_empty_cheque_date(today, casual, holidays, impossible)
        entry = {
            "group": idx + 1,
            "invoices": invs,
            "total_lkr": total,
            "cheque_date": cheque_date_str,
        }
        enrich_bundle_liquidity(entry, dealer_id, holidays)
        result.append(entry)
    audit_bundle_day_limits(
        result,
        casual_limit=Config.CASUAL_DAILY_LIMIT_LKR,
        account_id=repo.paying_account_id_for_dealer(dealer_id),
    )
    return result


def divide_invoices_into_cheques(
    dealer_id: int,
    invoice_ids: list,
    num_cheques: int,
    ceiling_lkr: float,
    allow_exceed_ceiling: bool = False,
) -> list:
    """Split invoices into N cheque groups, balancing totals across groups."""
    from db.connection import query_one

    invoices = []
    for inv_id in invoice_ids:
        inv = query_one("SELECT * FROM invoices WHERE invoices_id = ?", (int(inv_id),))
        if inv:
            invoices.append(inv)
    if not invoices:
        return []

    num_cheques = max(1, min(int(num_cheques), len(invoices)))
    invoices.sort(key=lambda inv: float(inv["total_amount"]), reverse=True)

    groups: list[dict] = [{"invoices": [], "total": 0.0} for _ in range(num_cheques)]
    for inv in invoices:
        target = min(groups, key=lambda g: g["total"])
        target["invoices"].append(inv)
        target["total"] += float(inv["total_amount"])

    assignments: dict[str, int] = {}
    for group_no, group in enumerate(groups, start=1):
        for inv in group["invoices"]:
            assignments[str(inv["invoices_id"])] = group_no

    effective_ceiling = ceiling_lkr if not allow_exceed_ceiling else max(
        ceiling_lkr, sum(float(inv["total_amount"]) for inv in invoices)
    )
    return build_bundles_from_assignments(
        dealer_id,
        assignments,
        {},
        effective_ceiling,
        enforce_ceiling=not allow_exceed_ceiling,
    )
