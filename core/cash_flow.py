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


@dataclass
class DepositAlert:
    deposit_by_date: str
    amount_needed: float
    reason: str
    clearance_date: str
    cheque_ids: list = field(default_factory=list)


@dataclass
class CashFlowReport:
    account_id: int
    account_nickname: str
    current_balance: float
    min_buffer: float
    cheques_next_30_days: float
    timeline: list
    alerts: list
    liquidity_schedule: list = field(default_factory=list)


def build_cash_flow_projection(account_id: int, horizon_days: int = 60) -> CashFlowReport:
    account = repo.get_bank_account(account_id)
    if not account:
        raise ValueError(f"Account {account_id} not found")

    min_buffer = float(repo.get_setting("min_cash_buffer_lkr", str(Config.MIN_CASH_BUFFER_LKR)))
    holidays = repo.get_holidays()
    today = date.today()
    end = today + timedelta(days=horizon_days)

    pending_rows = repo.build_pending_rows_for_account(account_id)
    bank_context = repo.build_bank_context(account_id)
    liquidity_schedule = calculate_max_liquidity_schedule(pending_rows, holidays, bank_context)

    funding_by_cheque = {}
    for row in liquidity_schedule:
        for cid in row.get("Cheque_Ids", []):
            funding_by_cheque[cid] = row["Target_Funding_Date"]

    balance = account["available_balance"]
    events = []

    for ch in repo.get_upcoming_cheques(account_id):
        funding_date_str = funding_by_cheque.get(ch["cheque_id"]) or ch.get("predicted_clearance_date")
        if not funding_date_str:
            continue
        fd = parse_date(funding_date_str)
        if today <= fd <= end:
            events.append(
                (
                    fd,
                    f"Cheque #{ch['cheque_no']} clears",
                    -ch["amount_in_numerals"],
                    ch["cheque_id"],
                    funding_date_str,
                )
            )

    for pd in repo.get_planned_deposits(account_id):
        pd_date = parse_date(pd["planned_date"])
        if today <= pd_date <= end:
            events.append((pd_date, f"Planned deposit: {pd.get('notes') or 'deposit'}", pd["amount"], None, None))

    events.sort(key=lambda e: e[0])

    timeline = []
    running = balance
    cheques_30 = 0.0

    for ev_date, label, delta, _, _ in events:
        running += delta
        if (ev_date - today).days <= 30 and delta < 0:
            cheques_30 += abs(delta)
        timeline.append(
            CashFlowEvent(
                event_date=format_date(ev_date),
                label=label,
                amount_delta=delta,
                running_balance=running,
                below_buffer=running < min_buffer,
            )
        )

    alerts = []
    running_sim = balance
    for ev_date, label, delta, cheque_id, funding_str in events:
        if delta >= 0:
            running_sim += delta
            continue
        projected = running_sim + delta
        if projected < min_buffer:
            needed = min_buffer - projected
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
                )
            )
        running_sim += delta

    return CashFlowReport(
        account_id=account_id,
        account_nickname=account.get("nickname") or account["account_name"],
        current_balance=balance,
        min_buffer=min_buffer,
        cheques_next_30_days=cheques_30,
        timeline=timeline,
        alerts=alerts,
        liquidity_schedule=liquidity_schedule,
    )
