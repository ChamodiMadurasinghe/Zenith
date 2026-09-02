from dataclasses import dataclass, field
from datetime import date, timedelta

from config import Config
from core.dates import format_date, parse_date
from core.liquidity_engine import calculate_max_liquidity_schedule
from db import repositories as repo


@dataclass
class CashFlowEvent:
    event_date: str
    label: str
    amount_delta: float
    running_balance: float
    below_buffer: bool
    in_overdraft: bool = False
    exceeds_overdraft: bool = False


@dataclass
class DepositAlert:
    deposit_by_date: str
    amount_needed: float
    reason: str
    clearance_date: str
    cheque_ids: list = field(default_factory=list)
    severity: str = "buffer"  # "buffer" | "overdraft"


@dataclass
class ChequeClearanceRow:
    cheque_id: int
    cheque_no: str
    dealer_name: str
    cheque_date: str
    clearance_date: str
    amount: float
    running_balance: float
    in_overdraft: bool
    exceeds_overdraft: bool
    below_buffer: bool


@dataclass
class CashFlowReport:
    account_id: int
    account_nickname: str
    current_balance: float
    overdraft_limit: float
    usable_funds: float
    min_buffer: float
    cheques_next_30_days: float
    timeline: list
    alerts: list
    liquidity_schedule: list = field(default_factory=list)
    cheque_timetable: list = field(default_factory=list)


def overdraft_floor(overdraft_limit: float) -> float:
    return -max(0.0, float(overdraft_limit or 0))


def usable_funds(balance: float, overdraft_limit: float) -> float:
    return float(balance or 0) + max(0.0, float(overdraft_limit or 0))


def classify_balance(running: float, overdraft_limit: float, min_buffer: float) -> tuple[bool, bool, bool]:
    floor = overdraft_floor(overdraft_limit)
    exceeds_overdraft = running < floor
    in_overdraft = running < 0 and not exceeds_overdraft
    below_buffer = running < min_buffer
    return in_overdraft, exceeds_overdraft, below_buffer


def _funding_dates_for_account(account_id: int) -> tuple[dict, list]:
    holidays = repo.get_holidays()
    pending_rows = repo.build_pending_rows_for_account(account_id)
    bank_context = repo.build_bank_context(account_id)
    liquidity_schedule = calculate_max_liquidity_schedule(pending_rows, holidays, bank_context)
    funding_by_cheque = {}
    for row in liquidity_schedule:
        for cid in row.get("Cheque_Ids", []):
            funding_by_cheque[cid] = row["Target_Funding_Date"]
    return funding_by_cheque, liquidity_schedule


def _cheque_clearance_str(ch: dict, funding_by_cheque: dict) -> str | None:
    return (
        funding_by_cheque.get(ch["cheque_id"])
        or ch.get("predicted_clearance_date")
        or ch.get("cheque_date")
    )


def _event_sort_key(event: tuple) -> tuple:
    ev_date, _label, delta, _cid, _funding, _kind, seq = event
    # Deposits before cheque outflows on the same day so the cash is there to cover them.
    kind_order = 0 if delta >= 0 else 1
    return (ev_date, kind_order, seq)


def _collect_events(
    account_id: int,
    funding_by_cheque: dict,
    today: date,
    end: date | None,
    extra_cheques: list | None = None,
) -> list:
    """Unified (date, label, delta, cheque_id, funding_str, meta, seq) events."""
    events = []
    seq = 0

    for ch in repo.get_upcoming_cheques(account_id):
        funding_date_str = _cheque_clearance_str(ch, funding_by_cheque)
        if not funding_date_str:
            continue
        fd = parse_date(funding_date_str)
        if fd < today:
            continue
        if end is not None and fd > end:
            continue
        seq += 1
        events.append(
            (
                fd,
                f"Cheque #{ch['cheque_no']} clears",
                -float(ch["amount_in_numerals"] or 0),
                ch["cheque_id"],
                funding_date_str,
                {
                    "kind": "cheque",
                    "cheque_id": ch["cheque_id"],
                    "cheque_no": ch.get("cheque_no") or "",
                    "dealer_name": ch.get("dealer_name") or "",
                    "cheque_date": ch.get("cheque_date") or "",
                    "amount": float(ch["amount_in_numerals"] or 0),
                },
                seq,
            )
        )

    for pd in repo.get_planned_deposits(account_id):
        pd_date = parse_date(pd["planned_date"])
        if pd_date < today:
            continue
        if end is not None and pd_date > end:
            continue
        seq += 1
        events.append(
            (
                pd_date,
                f"Planned deposit: {pd.get('notes') or 'deposit'}",
                float(pd["amount"] or 0),
                None,
                None,
                {"kind": "deposit"},
                seq,
            )
        )

    for extra in extra_cheques or []:
        amount = float(extra.get("amount") or extra.get("total_lkr") or 0)
        date_str = (
            extra.get("clearance_date")
            or extra.get("predicted_clearance_date")
            or extra.get("target_funding_date")
            or extra.get("cheque_date")
        )
        if amount <= 0 or not date_str:
            continue
        fd = parse_date(date_str)
        if fd < today:
            continue
        if end is not None and fd > end:
            continue
        seq += 1
        label = extra.get("label") or f"New cheque {extra.get('cheque_no') or ''}".strip()
        events.append(
            (
                fd,
                label,
                -amount,
                None,
                date_str,
                {
                    "kind": "extra_cheque",
                    "cheque_no": extra.get("cheque_no") or "",
                    "amount": amount,
                },
                seq,
            )
        )

    events.sort(key=_event_sort_key)
    return events


def _walk_balances(balance: float, overdraft_limit: float, min_buffer: float, events: list):
    running = float(balance)
    timeline = []
    cheque_timetable = []
    alerts = []
    cheques_30 = 0.0
    today = date.today()
    worst_balance = running
    exceeds_any = running < overdraft_floor(overdraft_limit)

    for ev_date, label, delta, cheque_id, funding_str, meta, _seq in events:
        running += delta
        worst_balance = min(worst_balance, running)
        in_od, exceeds_od, below_buf = classify_balance(running, overdraft_limit, min_buffer)
        if exceeds_od:
            exceeds_any = True
        if (ev_date - today).days <= 30 and delta < 0:
            cheques_30 += abs(delta)
        timeline.append(
            CashFlowEvent(
                event_date=format_date(ev_date),
                label=label,
                amount_delta=delta,
                running_balance=running,
                below_buffer=below_buf,
                in_overdraft=in_od,
                exceeds_overdraft=exceeds_od,
            )
        )
        if meta.get("kind") in ("cheque", "extra_cheque") and delta < 0:
            cheque_timetable.append(
                ChequeClearanceRow(
                    cheque_id=int(meta.get("cheque_id") or 0),
                    cheque_no=meta.get("cheque_no") or "",
                    dealer_name=meta.get("dealer_name") or "",
                    cheque_date=meta.get("cheque_date") or "",
                    clearance_date=format_date(ev_date),
                    amount=float(meta.get("amount") or abs(delta)),
                    running_balance=running,
                    in_overdraft=in_od,
                    exceeds_overdraft=exceeds_od,
                    below_buffer=below_buf,
                )
            )
        if delta < 0:
            floor = overdraft_floor(overdraft_limit)
            if running < floor:
                needed = floor - running
                deposit_by = parse_date(funding_str) if funding_str else ev_date
                if deposit_by < today:
                    deposit_by = today
                alerts.append(
                    DepositAlert(
                        deposit_by_date=format_date(deposit_by),
                        amount_needed=round(needed, 2),
                        reason=label,
                        clearance_date=format_date(ev_date),
                        cheque_ids=[cheque_id] if cheque_id else [],
                        severity="overdraft",
                    )
                )
            elif running >= 0 and running < min_buffer:
                needed = min_buffer - running
                deposit_by = parse_date(funding_str) if funding_str else ev_date
                if deposit_by < today:
                    deposit_by = today
                alerts.append(
                    DepositAlert(
                        deposit_by_date=format_date(deposit_by),
                        amount_needed=round(needed, 2),
                        reason=label,
                        clearance_date=format_date(ev_date),
                        cheque_ids=[cheque_id] if cheque_id else [],
                        severity="buffer",
                    )
                )

    return timeline, cheque_timetable, alerts, cheques_30, worst_balance, exceeds_any


def build_cash_flow_projection(
    account_id: int,
    horizon_days: int = 60,
    extra_cheques: list | None = None,
) -> CashFlowReport:
    account = repo.get_bank_account(account_id)
    if not account:
        raise ValueError(f"Account {account_id} not found")

    min_buffer = float(repo.get_setting("min_cash_buffer_lkr", str(Config.MIN_CASH_BUFFER_LKR)))
    today = date.today()
    end = today + timedelta(days=horizon_days)
    overdraft_limit = float(account.get("overdraft_limit") or 0)
    balance = float(account["available_balance"] or 0)

    funding_by_cheque, liquidity_schedule = _funding_dates_for_account(account_id)
    all_events = _collect_events(account_id, funding_by_cheque, today, None, extra_cheques)
    horizon_events = [ev for ev in all_events if ev[0] <= end]
    timeline, _, _, cheques_30, _, _ = _walk_balances(
        balance, overdraft_limit, min_buffer, horizon_events
    )
    _, cheque_timetable, alerts, _, _worst, _exceeds = _walk_balances(
        balance, overdraft_limit, min_buffer, all_events
    )

    return CashFlowReport(
        account_id=account_id,
        account_nickname=account.get("nickname") or account["account_name"],
        current_balance=balance,
        overdraft_limit=overdraft_limit,
        usable_funds=usable_funds(balance, overdraft_limit),
        min_buffer=min_buffer,
        cheques_next_30_days=cheques_30,
        timeline=timeline,
        alerts=alerts,
        liquidity_schedule=liquidity_schedule,
        cheque_timetable=cheque_timetable,
    )


def simulate_extra_cheques(account_id: int, extra_cheques: list, horizon_days: int = 365) -> dict:
    """Project whether adding extra_cheques would push the account past overdraft."""
    account = repo.get_bank_account(account_id)
    if not account:
        return {
            "account_id": account_id,
            "exceeds_overdraft": False,
            "worst_balance": 0.0,
            "overdraft_limit": 0.0,
            "usable_funds": 0.0,
            "current_balance": 0.0,
        }
    report = build_cash_flow_projection(account_id, horizon_days=horizon_days, extra_cheques=extra_cheques)
    worst = report.current_balance
    exceeds = False
    for row in report.cheque_timetable:
        worst = min(worst, row.running_balance)
        if row.exceeds_overdraft:
            exceeds = True
    for ev in report.timeline:
        worst = min(worst, ev.running_balance)
        if ev.exceeds_overdraft:
            exceeds = True
    return {
        "account_id": account_id,
        "exceeds_overdraft": exceeds,
        "worst_balance": round(worst, 2),
        "overdraft_limit": report.overdraft_limit,
        "usable_funds": report.usable_funds,
        "current_balance": report.current_balance,
    }
