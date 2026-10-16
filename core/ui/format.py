"""Formatting helpers for the simple UI. Registered as Jinja filters in routes/simple.py."""

from __future__ import annotations

from datetime import date

from core.i18n import translate


def long_date(d: date, lang: str | None = None) -> str:
    """"Wednesday, 14 October" in the current language."""
    return translate(
        "s_long_date",
        lang,
        weekday=translate(f"s_weekday_{d.weekday()}", lang),
        day=d.day,
        month=translate(f"s_month_{d.month}", lang),
    )


def initials(name: str | None) -> str:
    """"Perera Hardware (Pvt) Ltd" → "PH". Ignores bracketed words; "?" when empty."""
    words = [w for w in (name or "").replace("(", " (").split() if w[:1].isalnum()]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[1][0]).upper()
