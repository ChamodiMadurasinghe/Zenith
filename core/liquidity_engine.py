"""Max-liquidity scheduling for Sri Lankan cheque clearing (CBSL / LankaPay).

Holiday source: ``cbsl_bank_holidays`` table (domain alias: cbsl_holidays).
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from core.dates import add_business_days, format_date, next_business_day, parse_date


def true_settlement_date(stated_date: date, holidays: set) -> date:
    """First processable banking day on or after the stated cheque date."""
    return next_business_day(stated_date, holidays, impossible_days="")


def target_funding_date(stated_date: date, holidays: set, *, is_interbank: bool) -> date:
    """Latest legal day funds must be available before debit clears."""
    settlement = true_settlement_date(stated_date, holidays)
    if is_interbank:
        return add_business_days(settlement, 1, holidays, impossible_days="")
    return settlement


def is_interbank(user_bank_name: Optional[str], dealer_preferred_bank_name: Optional[str]) -> bool:
    if not user_bank_name or not dealer_preferred_bank_name:
        return False
    return user_bank_name.strip().lower() != dealer_preferred_bank_name.strip().lower()


def _resolve_interbank(row: dict, bank_context: dict) -> bool:
    if row.get("is_interbank") is not None:
        return bool(row["is_interbank"])
    dealer_id = row.get("dealer_id")
    if dealer_id is None:
        return False
    dealer_banks = bank_context.get("dealer_banks", {})
    user_bank = bank_context.get("user_bank_name", "")
    dealer_bank = dealer_banks.get(dealer_id, "")
    return is_interbank(user_bank, dealer_bank)


@dataclass
class LiquidityScheduleRow:
    stated_date: str
    true_settlement_date: str
    target_funding_date: str
    total_amount: float
    days_gained_by_holiday_lag: int
    days_gained_total: int
    is_interbank: bool = False
    cheque_ids: list = field(default_factory=list)
    dealer_ids: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "Stated_Date": self.stated_date,
            "True_Settlement_Date": self.true_settlement_date,
            "Target_Funding_Date": self.target_funding_date,
            "Total_Amount": round(self.total_amount, 2),
            "Days_Gained_By_Holiday_Lag": self.days_gained_by_holiday_lag,
            "Days_Gained_Total": self.days_gained_total,
            "Is_Interbank": self.is_interbank,
            "Cheque_Ids": self.cheque_ids,
            "Dealer_Ids": self.dealer_ids,
        }


def holiday_lag_days(stated: date, true_settlement: date) -> int:
    """Calendar days from stated date to first banking settlement (weekends/CBSL only)."""
    return max(0, (true_settlement - stated).days)


def float_days_gained(stated: date, target: date) -> int:
    """Calendar days the merchant can keep funds from stated date until funding day."""
    return max(0, (target - stated).days)


def apply_liquidity_dates(
    stated_date_str: str,
    holidays: set,
    *,
    is_interbank: bool,
) -> dict:
    """Compute settlement fields for a single stated cheque date."""
    stated = parse_date(stated_date_str)
    true_settlement = true_settlement_date(stated, holidays)
    target = target_funding_date(stated, holidays, is_interbank=is_interbank)
    return {
        "true_settlement_date": format_date(true_settlement),
        "target_funding_date": format_date(target),
        # Weekend/CBSL roll only (stated → true settlement)
        "days_gained_by_holiday_lag": holiday_lag_days(stated, true_settlement),
        # Full float to "Keep money until" (holiday lag + interbank business-day shift)
        "days_gained_total": float_days_gained(stated, target),
        "is_interbank": is_interbank,
        "predicted_clearance_date": format_date(target),
    }


def calculate_max_liquidity_schedule(
    pending_rows: list,
    holidays: set,
    bank_context: dict | None = None,
) -> list[dict]:
    """Group pending rows by stated date and return max-liquidity schedule JSON."""
    bank_context = bank_context or {}
    groups: dict[str, dict] = {}

    for row in pending_rows:
        if row.get("status") and row["status"] != "pending":
            continue
        stated = row["stated_date"]
        amount = float(row.get("amount") or row.get("total_amount") or 0)
        if stated not in groups:
            groups[stated] = {
                "amount": 0.0,
                "cheque_ids": [],
                "dealer_ids": set(),
                "is_interbank": False,
            }
        g = groups[stated]
        g["amount"] += amount
        if row.get("cheque_id"):
            g["cheque_ids"].append(row["cheque_id"])
        if row.get("dealer_id"):
            g["dealer_ids"].add(row["dealer_id"])
        if _resolve_interbank(row, bank_context):
            g["is_interbank"] = True

    schedule = []
    for stated_str in sorted(groups.keys()):
        g = groups[stated_str]
        if not g["is_interbank"] and g["dealer_ids"]:
            for dealer_id in g["dealer_ids"]:
                if _resolve_interbank({"dealer_id": dealer_id}, bank_context):
                    g["is_interbank"] = True
                    break

        stated = parse_date(stated_str)
        true_settlement = true_settlement_date(stated, holidays)
        target = target_funding_date(stated, holidays, is_interbank=g["is_interbank"])
        schedule.append(
            LiquidityScheduleRow(
                stated_date=stated_str,
                true_settlement_date=format_date(true_settlement),
                target_funding_date=format_date(target),
                total_amount=g["amount"],
                days_gained_by_holiday_lag=holiday_lag_days(stated, true_settlement),
                days_gained_total=float_days_gained(stated, target),
                is_interbank=g["is_interbank"],
                cheque_ids=sorted(set(g["cheque_ids"])),
                dealer_ids=sorted(g["dealer_ids"]),
            ).to_dict()
        )

    return schedule
