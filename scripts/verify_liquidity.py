"""Verify max-liquidity schedule scenarios from the implementation plan."""

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.dates import format_date
from core.liquidity_engine import (
    apply_liquidity_dates,
    calculate_max_liquidity_schedule,
    true_settlement_date,
    target_funding_date,
)


def test_saturday_roll():
    holidays = set()
    stated = date(2026, 4, 11)  # Saturday
    ts = true_settlement_date(stated, holidays)
    assert ts == date(2026, 4, 13), f"Expected Monday, got {ts}"
    assert (ts - stated).days == 2
    print("OK: Saturday stated date -> Monday settlement, days_gained=2")


def test_holiday_roll():
    holidays = {"2026-04-14"}
    stated = date(2026, 4, 14)
    ts = true_settlement_date(stated, holidays)
    assert ts > stated, f"Expected forward roll past holiday, got {ts}"
    print(f"OK: CBSL holiday {stated} -> {ts}")


def test_monday_no_gain():
    holidays = set()
    stated = date(2026, 4, 13)  # Monday
    ts = true_settlement_date(stated, holidays)
    assert ts == stated
    assert (ts - stated).days == 0
    print("OK: Monday stated date -> same day, days_gained=0")


def test_interbank_plus_one():
    holidays = set()
    stated = date(2026, 4, 13)
    tf = target_funding_date(stated, holidays, is_interbank=True)
    assert tf == date(2026, 4, 14), f"Expected Tuesday, got {tf}"
    print("OK: Interbank adds +1 business day")


def test_same_bank_no_extra():
    holidays = set()
    stated = date(2026, 4, 13)
    tf = target_funding_date(stated, holidays, is_interbank=False)
    assert tf == stated
    print("OK: Same-bank target funding = true settlement")


def test_schedule_grouping():
    holidays = set()
    rows = [
        {"stated_date": "2026-04-11", "amount": 100000, "cheque_id": 1, "dealer_id": 1, "status": "pending"},
        {"stated_date": "2026-04-11", "amount": 50000, "cheque_id": 2, "dealer_id": 1, "status": "pending"},
    ]
    schedule = calculate_max_liquidity_schedule(
        rows,
        holidays,
        {"user_bank_name": "Commercial Bank of Ceylon", "dealer_banks": {1: "Bank of Ceylon"}},
    )
    assert len(schedule) == 1
    assert schedule[0]["Total_Amount"] == 150000
    assert schedule[0]["Is_Interbank"] is True
    assert schedule[0]["Days_Gained_By_Holiday_Lag"] == 2
    print("OK: Schedule groups by stated date and flags interbank")


def test_apply_liquidity_dates():
    holidays = set()
    d = apply_liquidity_dates("2026-04-11", holidays, is_interbank=True)
    assert d["true_settlement_date"] == "2026-04-13"
    assert d["target_funding_date"] == "2026-04-14"
    assert d["days_gained_by_holiday_lag"] == 2
    print("OK: apply_liquidity_dates bundle helper")


if __name__ == "__main__":
    test_saturday_roll()
    test_holiday_roll()
    test_monday_no_gain()
    test_interbank_plus_one()
    test_same_bank_no_extra()
    test_schedule_grouping()
    test_apply_liquidity_dates()
    print("\nAll liquidity verification checks passed.")
