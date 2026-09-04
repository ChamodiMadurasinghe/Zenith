from datetime import date, timedelta

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def parse_date(s: str) -> date:
    return date.fromisoformat(s)


def format_date(d: date) -> str:
    return d.isoformat()


def parse_impossible_days(value) -> str:
    """Normalize free text or checkbox values to canonical weekday names."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        raw_parts = [str(part) for part in value]
    else:
        raw_parts = str(value).split(",")
    selected = {part.strip().lower() for part in raw_parts if part and str(part).strip()}
    return ", ".join(day for day in WEEKDAYS if day.lower() in selected)


def impossible_days_from_form(form) -> str:
    """Read Never-pay-on days from checkboxes or a legacy text field."""
    if form.get("impossible_days_present"):
        return parse_impossible_days(form.getlist("impossible_days"))
    if hasattr(form, "getlist"):
        listed = form.getlist("impossible_days")
        if len(listed) > 1:
            return parse_impossible_days(listed)
    return parse_impossible_days(form.get("impossible_days", "Sunday"))


def is_impossible_day(d: date, impossible_days: str) -> bool:
    if not impossible_days:
        return False
    blocked = {day.strip() for day in parse_impossible_days(impossible_days).split(",") if day.strip()}
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
