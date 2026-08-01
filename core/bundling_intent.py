"""Detect bundling commands from chat and infer Python actions when the LLM omits JSON."""

import re

WORD_NUMBERS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}

BUNDLING_KEYWORDS = (
    "divide",
    "split",
    "bundle",
    "group",
    "cheque",
    "check",
    "rebundle",
    "re-bundle",
    "organize",
    "separate",
)

EXCEED_KEYWORDS = (
    "exceed",
    "upper limit",
    "upperlimit",
    "over limit",
    "above limit",
    "ok if",
    "it's ok",
    "its ok",
    "ignore limit",
    "ignore ceiling",
    "doesn't matter",
    "doesnt matter",
)


def is_bundling_request(message: str) -> bool:
    m = message.lower()
    return any(k in m for k in BUNDLING_KEYWORDS)


def allows_exceed_ceiling(message: str) -> bool:
    m = message.lower()
    return any(p in m for p in EXCEED_KEYWORDS)


def extract_cheque_count(message: str) -> int | None:
    m = message.lower()

    for word, num in WORD_NUMBERS.items():
        if re.search(rf"\b{word}\b", m) and re.search(r"\b(cheque|check|bundl|group|split|divide)\b", m):
            return num

    patterns = [
        r"(\d+)\s*(?:cheque|check|bundl|group)",
        r"(?:divide|split|bundle)[\s\w,.'\"-]{0,40}?(\d+)",
        r"(?:into|for|in)\s+(\d+)\s*(?:cheque|check|bundl|group)?",
    ]
    for pattern in patterns:
        match = re.search(pattern, m)
        if match:
            num = int(match.group(1))
            if 1 <= num <= 50:
                return num
    return None


def gather_invoice_ids_for_bundling(bundles: list, dealer_id: int) -> list[int]:
    ids: list[int] = []
    seen: set[int] = set()
    for bundle in bundles or []:
        for inv in bundle.get("invoices", []):
            inv_id = int(inv["invoices_id"])
            if inv_id not in seen:
                seen.add(inv_id)
                ids.append(inv_id)
    if ids:
        return ids

    from db import repositories as repo

    for inv in repo.get_verified_unassigned_invoices(dealer_id):
        inv_id = int(inv["invoices_id"])
        if inv_id not in seen:
            seen.add(inv_id)
            ids.append(inv_id)
    return ids


def normalize_proposed_actions(raw) -> list[dict]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        if raw.get("action"):
            return [raw]
        actions = []
        for value in raw.values():
            if isinstance(value, dict) and value.get("action"):
                actions.append(value)
        return actions
    return []


def infer_bundling_actions(message: str, bundles: list, dealer_id: int) -> list[dict]:
    if not is_bundling_request(message):
        return []

    num_cheques = extract_cheque_count(message)
    if not num_cheques:
        return []

    invoice_ids = gather_invoice_ids_for_bundling(bundles, dealer_id)
    if not invoice_ids:
        return []

    return [
        {
            "action": "divide_into_cheques",
            "num_cheques": num_cheques,
            "invoice_ids": invoice_ids,
            "allow_exceed_ceiling": allows_exceed_ceiling(message),
        }
    ]