"""Calendar preset ranges for list filters (week / month)."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

from core.dates import format_date

PRESET_THIS_WEEK = "this_week"
PRESET_LAST_WEEK = "last_week"
PRESET_THIS_MONTH = "this_month"
PRESET_LAST_MONTH = "last_month"
PRESET_CUSTOM = "custom"
PRESET_ALL = "all"

WEEK_MONTH_PRESETS = frozenset(
    {PRESET_THIS_WEEK, PRESET_LAST_WEEK, PRESET_THIS_MONTH, PRESET_LAST_MONTH}
)


def _monday_of_week(d: date) -> date:
    return d - timedelta(days=d.weekday())


def preset_date_range(
    preset: str,
    today: date | None = None,
) -> tuple[date | None, date | None]:
    """Return (start, end) inclusive for a named preset.

    `custom` / `all` / empty → (None, None) — caller supplies explicit dates for custom.
    """
    today = today or date.today()
    key = (preset or "").strip().lower()
    if key in ("", PRESET_ALL, PRESET_CUSTOM):
        return None, None

    if key == PRESET_THIS_WEEK:
        start = _monday_of_week(today)
        return start, start + timedelta(days=6)

    if key == PRESET_LAST_WEEK:
        this_monday = _monday_of_week(today)
        start = this_monday - timedelta(days=7)
        return start, start + timedelta(days=6)

    if key == PRESET_THIS_MONTH:
        start = today.replace(day=1)
        last_day = monthrange(today.year, today.month)[1]
        return start, today.replace(day=last_day)

    if key == PRESET_LAST_MONTH:
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        start = last_prev.replace(day=1)
        return start, last_prev

    return None, None


def preset_date_strings(
    preset: str,
    today: date | None = None,
) -> tuple[str | None, str | None]:
    start, end = preset_date_range(preset, today=today)
    return (
        format_date(start) if start else None,
        format_date(end) if end else None,
    )
