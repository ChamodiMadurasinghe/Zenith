from datetime import date, timedelta

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def parse_date(s: str) -> date:
    return date.fromisoformat(s)


def format_date(d: date) -> str:
    return d.isoformat()


def is_impossible_day(d: date, impossible_days: str) -> bool:
    if not impossible_days:
        return False
    blocked = {day.strip() for day in impossible_days.split(",")}
    return WEEKDAYS[d.weekday()] in blocked


def next_business_day(start: date, holidays: set, impossible_days: str = "") -> date:
    d = start
    while d.weekday() >= 5 or format_date(d) in holidays or is_impossible_day(d, impossible_days):
        d += timedelta(days=1)
    return d


def add_business_days(start: date, days: int, holidays: set, impossible_days: str = "") -> date:
    d = start
    added = 0
    while added < days:
        d += timedelta(days=1)
        if d.weekday() < 5 and format_date(d) not in holidays and not is_impossible_day(d, impossible_days):
            added += 1
    return d


def estimate_clearance(cheque_date: date, holidays: set, impossible_days: str = "") -> date:
    return add_business_days(cheque_date, 3, holidays, impossible_days)
