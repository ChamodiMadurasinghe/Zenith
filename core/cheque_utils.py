"""Cheque-specific helpers: bank code resolution and amount-in-words formatting."""

from __future__ import annotations

from num2words import num2words

BANK_NAME_TO_CODE: dict[str, str] = {
    "commercial bank of ceylon": "COMB",
    "commercial bank": "COMB",
    "comb": "COMB",
    "hatton national bank": "HNB",
    "hnb": "HNB",
    "sampath bank": "SAMPATH",
    "sampath": "SAMPATH",
    "bank of ceylon": "BOC",
    "boc": "BOC",
    "seylan bank": "SEYLAN",
    "seylan": "SEYLAN",
}

BANK_CODE_ALIASES: dict[str, tuple[str, ...]] = {
    "COMB": ("commercial",),
    "HNB": ("hatton",),
    "SAMPATH": ("sampath",),
    "BOC": ("bank of ceylon", "boc"),
    "SEYLAN": ("seylan",),
}


def resolve_bank_code(bank_name: str | None) -> str | None:
    """Map a user-facing bank name to a template bank_code."""
    if not bank_name:
        return None
    normalized = bank_name.strip().lower()
    if not normalized:
        return None
    if normalized in BANK_NAME_TO_CODE:
        return BANK_NAME_TO_CODE[normalized]
    for code, aliases in BANK_CODE_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            return code
    return None


def format_cheque_amount_in_words(amount: float) -> str:
    """Convert LKR amount to cheque text, e.g. 'One Hundred ... And 50/100 Cents Only ***'."""
    if amount < 0:
        raise ValueError("Cheque amount cannot be negative")

    rounded = round(float(amount), 2)
    rupees = int(rounded)
    cents = int(round((rounded - rupees) * 100))
    if cents >= 100:
        rupees += 1
        cents = 0

    if rupees == 0:
        words = "Zero"
    else:
        words = num2words(rupees, lang="en").title().replace(" And ", " ")

    result = f"{words} Rupees"
    if cents > 0:
        result += f" And {cents}/100 Cents"
    return result + " Only ***"
