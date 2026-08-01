ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
]
TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _under_thousand(n: int) -> str:
    if n == 0:
        return ""
    if n < 20:
        return ONES[n]
    if n < 100:
        return f"{TENS[n // 10]} {ONES[n % 10]}".strip()
    return f"{ONES[n // 100]} Hundred {_under_thousand(n % 100)}".strip()


def amount_to_words(amount: float) -> str:
    rupees = int(amount)
    cents = round((amount - rupees) * 100)
    if rupees == 0:
        words = "Zero"
    else:
        parts = []
        millions = rupees // 1_000_000
        thousands = (rupees % 1_000_000) // 1_000
        remainder = rupees % 1_000
        if millions:
            parts.append(f"{_under_thousand(millions)} Million")
        if thousands:
            parts.append(f"{_under_thousand(thousands)} Thousand")
        if remainder:
            parts.append(_under_thousand(remainder))
        words = " ".join(parts)
    result = f"{words} Rupees"
    if cents:
        result += f" and {_under_thousand(cents)} Cents"
    return result + " Only"
