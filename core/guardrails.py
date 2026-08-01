import copy
from dataclasses import dataclass
from datetime import date, timedelta

from config import Config
from core.bundling import (
    build_bundles_from_assignments,
    divide_invoices_into_cheques,
    enrich_bundle_liquidity,
    invoice_due_date,
    recalculate_all_bundles,
)
from core.cheque_batcher import audit_bundle_day_limits
from core.dates import add_business_days, format_date, parse_date
from db import repositories as repo


@dataclass
class GuardrailResult:
    passed: bool
    message: str = ""


def build_invoice_lookup(bundles: list, dealer_id: int) -> dict:
    lookup = {}
    for bundle in bundles or []:
        for inv in bundle.get("invoices", []):
            lookup[int(inv["invoices_id"])] = inv
    for inv in repo.get_verified_unassigned_invoices(dealer_id):
        lookup[int(inv["invoices_id"])] = inv
    return lookup


def collect_bundle_issues(
    state: dict,
    dealer_id: int,
    ceiling_lkr: float,
    allow_exceed_ceiling: bool = False,
) -> list[str]:
    """Return every validation issue for the current bundle proposal."""
    issues: list[str] = []
    today = date.today()
    bundles = state.get("bundles") or []
    seen_invoices: dict[int, int] = {}

    if not bundles:
        issues.append("No cheques proposed yet.")
        return issues

    for bundle in bundles:
        group = bundle.get("group", "?")
        invoices = bundle.get("invoices") or []
        if not invoices:
            issues.append(f"Cheque {group}: has no invoices assigned.")
            continue

        total = sum(float(inv["total_amount"]) for inv in invoices)
        if not allow_exceed_ceiling and total > ceiling_lkr:
            issues.append(
                f"Cheque {group}: total Rs. {total:,.2f} exceeds the Rs. {ceiling_lkr:,.2f} ceiling."
            )

        cheque_date_str = bundle.get("cheque_date")
        if not cheque_date_str:
            issues.append(f"Cheque {group}: missing cheque date.")
        else:
            try:
                cheque_date = parse_date(cheque_date_str)
                if cheque_date < today:
                    issues.append(
                        f"Cheque {group}: stated date {cheque_date_str} is in the past."
                    )
            except (TypeError, ValueError):
                issues.append(f"Cheque {group}: invalid cheque date '{cheque_date_str}'.")

        fund_by = bundle.get("target_funding_date") or bundle.get("predicted_clearance_date")
        if fund_by:
            try:
                if parse_date(fund_by) < today:
                    issues.append(
                        f"Cheque {group}: funds must be available by {fund_by} (that date has already passed)."
                    )
            except (TypeError, ValueError):
                issues.append(f"Cheque {group}: invalid funding date '{fund_by}'.")

        for inv in invoices:
            inv_id = int(inv["invoices_id"])
            inv_no = inv.get("invoice_no") or inv_id
            if inv_id in seen_invoices:
                issues.append(
                    f"Invoice {inv_no} appears in both cheque {seen_invoices[inv_id]} and cheque {group}."
                )
            seen_invoices[inv_id] = group

            if inv.get("cheque_id"):
                issues.append(f"Invoice {inv_no} is already on committed cheque #{inv.get('cheque_id')}.")

    # Zenith-1 casual daily limit audit (deposit_timetable day exposure)
    audits = audit_bundle_day_limits(
        bundles, casual_limit=Config.CASUAL_DAILY_LIMIT_LKR
    )
    for audit in audits:
        if audit.get("verdict") == "LIMIT_BREACH_WARNING":
            group = audit.get("group", "?")
            issues.append(
                f"Cheque {group}: day exposure Rs. {audit['total_day_exposure']:,.2f} "
                f"on {audit.get('calculated_settlement_date')} exceeds casual daily "
                f"limit Rs. {audit['casual_limit']:,.2f}."
            )

    return issues


def validate_bundle_state(
    state: dict,
    dealer_id: int,
    ceiling_lkr: float,
    allow_exceed_ceiling: bool = False,
) -> GuardrailResult:
    issues = collect_bundle_issues(state, dealer_id, ceiling_lkr, allow_exceed_ceiling)
    if issues:
        return GuardrailResult(False, issues[0])
    return GuardrailResult(True)


def _recalc_bundle(bundle: dict, dealer_id: int):
    holidays = repo.get_holidays()
    enrich_bundle_liquidity(bundle, dealer_id, holidays)


def _default_cheque_date(invoices: list, dealer_id: int) -> str:
    dealer = repo.get_dealer(dealer_id) or {}
    holidays = repo.get_holidays()
    impossible = dealer.get("impossible_days", "")
    casual = int(dealer.get("casual_days") or 0)
    today = date.today()
    last_due = max(invoice_due_date(inv) for inv in invoices)
    cheque_date = add_business_days(last_due, casual, holidays, impossible)
    if cheque_date < today:
        cheque_date = add_business_days(today, 1, holidays, impossible)
    return format_date(cheque_date)


def apply_action(
    state: dict,
    action: dict,
    invoice_lookup: dict,
    dealer_id: int = None,
    ceiling_lkr: float = None,
) -> GuardrailResult:
    action_type = action.get("action")
    bundles = state.get("bundles", [])

    if action_type == "divide_into_cheques":
        if dealer_id is None:
            return GuardrailResult(False, "divide_into_cheques requires dealer context.")
        num_cheques = int(action.get("num_cheques") or action.get("count") or 1)
        allow_exceed = bool(action.get("allow_exceed_ceiling"))
        invoice_ids = action.get("invoice_ids") or []
        if not invoice_ids:
            invoice_ids = list(invoice_lookup.keys())
        if not invoice_ids:
            return GuardrailResult(False, "divide_into_cheques: no invoices to bundle.")
        state["bundles"] = divide_invoices_into_cheques(
            dealer_id,
            invoice_ids,
            num_cheques,
            float(ceiling_lkr or 500000),
            allow_exceed_ceiling=allow_exceed,
        )
        state["allow_exceed_ceiling"] = allow_exceed
        if not state["bundles"]:
            return GuardrailResult(False, "divide_into_cheques: could not build cheque groups.")
        return GuardrailResult(True)

    if action_type == "assign_invoices":
        assignments = action.get("assignments") or {}
        if not assignments:
            return GuardrailResult(False, "assign_invoices requires an assignments object.")
        if dealer_id is None:
            return GuardrailResult(False, "assign_invoices requires dealer context.")
        ceiling = float(action.get("ceiling_lkr") or ceiling_lkr or 500000)
        cheque_dates = action.get("cheque_dates") or {}
        state["bundles"] = build_bundles_from_assignments(
            dealer_id, assignments, cheque_dates, ceiling
        )
        return GuardrailResult(True)

    if action_type == "create_bundles":
        groups = action.get("groups") or []
        if not groups:
            return GuardrailResult(False, "create_bundles requires a groups array.")
        if dealer_id is None:
            return GuardrailResult(False, "create_bundles requires dealer context.")
        new_bundles = []
        for i, group in enumerate(groups):
            inv_ids = group.get("invoice_ids") or []
            invs = []
            missing = []
            for raw_id in inv_ids:
                inv_id = int(raw_id)
                inv = invoice_lookup.get(inv_id)
                if inv:
                    invs.append(inv)
                else:
                    missing.append(inv_id)
            if missing:
                return GuardrailResult(
                    False, f"create_bundles: invoice(s) not found: {', '.join(str(x) for x in missing)}"
                )
            if not invs:
                return GuardrailResult(False, f"create_bundles: group {i + 1} has no invoices.")
            total = sum(float(inv["total_amount"]) for inv in invs)
            cheque_date = group.get("cheque_date") or _default_cheque_date(invs, dealer_id)
            entry = {
                "group": i + 1,
                "invoices": invs,
                "total_lkr": total,
                "cheque_date": cheque_date,
            }
            _recalc_bundle(entry, dealer_id)
            new_bundles.append(entry)
        state["bundles"] = new_bundles
        return GuardrailResult(True)

    if action_type == "set_cheque_date":
        idx = int(action.get("cheque_group", 1)) - 1
        if idx < 0 or idx >= len(bundles):
            return GuardrailResult(False, "Invalid cheque group index")
        bundles[idx]["cheque_date"] = action["date"]
        if dealer_id:
            _recalc_bundle(bundles[idx], dealer_id)
        elif action.get("predicted_clearance_date"):
            bundles[idx]["predicted_clearance_date"] = action["predicted_clearance_date"]
        return GuardrailResult(True)

    if action_type == "move_invoice":
        inv_id = int(action["invoice_id"])
        to_group = int(action.get("to_group", 1)) - 1
        inv = invoice_lookup.get(inv_id)
        if not inv:
            return GuardrailResult(False, f"Invoice {inv_id} not found")
        for bundle in bundles:
            bundle["invoices"] = [i for i in bundle.get("invoices", []) if i["invoices_id"] != inv_id]
            bundle["total_lkr"] = sum(float(i["total_amount"]) for i in bundle["invoices"])
        while to_group >= len(bundles):
            bundles.append(
                {
                    "group": len(bundles) + 1,
                    "invoices": [],
                    "total_lkr": 0.0,
                    "cheque_date": bundles[0]["cheque_date"] if bundles else "",
                }
            )
        bundles[to_group]["invoices"].append(inv)
        bundles[to_group]["total_lkr"] = sum(float(i["total_amount"]) for i in bundles[to_group]["invoices"])
        bundles[:] = [b for b in bundles if b.get("invoices")]
        for i, b in enumerate(bundles):
            b["group"] = i + 1
            if dealer_id:
                _recalc_bundle(b, dealer_id)
        return GuardrailResult(True)

    if action_type == "postpone_cheque":
        idx = int(action.get("cheque_group", 1)) - 1
        days = int(action.get("days", 1))
        cd = parse_date(bundles[idx]["cheque_date"]) + timedelta(days=days)
        bundles[idx]["cheque_date"] = cd.isoformat()
        if dealer_id:
            _recalc_bundle(bundles[idx], dealer_id)
        return GuardrailResult(True)

    if action_type == "split_invoice":
        inv_id = int(action["invoice_id"])
        inv = invoice_lookup.get(inv_id)
        if not inv:
            return GuardrailResult(False, f"Invoice {inv_id} not found")
        source_idx = None
        for i, bundle in enumerate(bundles):
            if any(i2["invoices_id"] == inv_id for i2 in bundle.get("invoices", [])):
                source_idx = i
                bundle["invoices"] = [i2 for i2 in bundle["invoices"] if i2["invoices_id"] != inv_id]
                bundle["total_lkr"] = sum(float(i2["total_amount"]) for i2 in bundle["invoices"])
                break
        if source_idx is None:
            return GuardrailResult(False, f"Invoice {inv_id} not in any bundle")
        new_group = {
            "group": len(bundles) + 1,
            "invoices": [inv],
            "total_lkr": float(inv["total_amount"]),
            "cheque_date": bundles[source_idx]["cheque_date"],
        }
        if dealer_id:
            _recalc_bundle(new_group, dealer_id)
        bundles.append(new_group)
        bundles[:] = [b for b in bundles if b.get("invoices")]
        for i, b in enumerate(bundles):
            b["group"] = i + 1
        return GuardrailResult(True)

    if action_type == "recalculate_dates":
        if dealer_id:
            recalculate_all_bundles(bundles, dealer_id)
        return GuardrailResult(True)

    return GuardrailResult(False, f"Unknown action: {action_type}")


def apply_proposed_actions(
    bundles: list,
    actions: list,
    dealer_id: int,
    ceiling_lkr: float,
) -> tuple[list, list[str], bool]:
    """Apply AI/Python actions, verify, return (bundles, issues, allow_exceed_ceiling)."""
    invoice_lookup = build_invoice_lookup(bundles, dealer_id)
    state = {"bundles": copy.deepcopy(bundles)}
    action_errors: list[str] = []
    allow_exceed = False

    for action in actions or []:
        if action.get("allow_exceed_ceiling"):
            allow_exceed = True
        result = apply_action(
            state,
            action,
            invoice_lookup,
            dealer_id=dealer_id,
            ceiling_lkr=ceiling_lkr,
        )
        if not result.passed:
            action_errors.append(result.message)
        if state.get("allow_exceed_ceiling"):
            allow_exceed = True

    bundles_out = state["bundles"] if actions else bundles
    allow_exceed = allow_exceed or bool(state.get("allow_exceed_ceiling"))

    validation_issues = collect_bundle_issues(
        {"bundles": bundles_out},
        dealer_id,
        ceiling_lkr,
        allow_exceed_ceiling=allow_exceed,
    )
    all_issues: list[str] = []
    seen = set()
    for issue in action_errors + validation_issues:
        if issue not in seen:
            seen.add(issue)
            all_issues.append(issue)
    return bundles_out, all_issues, allow_exceed
