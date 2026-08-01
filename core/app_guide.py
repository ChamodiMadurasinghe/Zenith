"""Structured app knowledge for the Zenith Guide agent (no bundling logic)."""

import re

from core.i18n import translate

NAV_SECTIONS = """
Main menu (top of every page after sign-in):
- Invoices (/): upload or enter supplier invoices
- Cheques (/bundling): pick a supplier to write cheques
- Bank Balance (/cash-flow): update bank balance and plan deposits
- Reports (/analytics): business summaries after cheques are written
- Language bar (very top): switch English, Sinhala, or Tamil
"""

WORKFLOWS = """
Typical workflow:
1. Add supplier (if new) — from Invoices page or when reviewing an invoice
2. Upload invoice photo or enter manually — check details, then save
3. Open Cheques — pick the supplier
4. On the supplier Cheques page: tick invoices, set max amount per cheque
5. Use the Cheque Assistant (Agent 2) panel on the RIGHT to group/split/date cheques — only Agent 2 can do bundling
6. Preview cheques, acknowledge any warnings, then commit
7. Check Reports and Bank Balance for cash planning
"""

TROUBLESHOOTING = """
Common issues:
- Blurry invoice photo: retake with good light, flat surface, all corners visible
- Session expired: sign in again
- Invoice waiting for check: open it from the Invoices dashboard and verify
- Can't write cheques: supplier bank details may be incomplete — open supplier Details tab
- Language wrong: use the language buttons at the very top
- Demo mode (USE_FAKE_AI): bundling chat uses sample replies; Guide still helps with navigation
"""

AGENT2_NOTE = """
IMPORTANT — Cheque bundling is ONLY done by Agent 2 (Cheque Assistant):
- Location: supplier Cheques page, right-hand chat panel
- The floating Zenith Guide (this agent) must NEVER bundle, split, date, or move invoices
- If user asks to bundle: tell them to open Cheques → pick supplier → use Cheque Assistant on the right
"""

PAGE_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"^/review/"), "review", "guide_page_tip_review"),
    (re.compile(r"^/invoice/.+/verify"), "verify", "guide_page_tip_review"),
    (re.compile(r"^/invoice/manual"), "manual", "guide_page_tip_upload"),
    (re.compile(r"^/dealers/\d+/cheques"), "dealer_cheques", "guide_page_tip_cheques"),
    (re.compile(r"^/bundling"), "cheques", "guide_page_tip_cheques"),
    (re.compile(r"^/cash-flow"), "cash_flow", "guide_page_tip_cash"),
    (re.compile(r"^/analytics"), "analytics", "guide_page_tip_analytics"),
    (re.compile(r"^/dealers"), "dealer", "guide_page_tip_dealer"),
    (re.compile(r"^/$"), "upload", "guide_page_tip_upload"),
]

PAGE_GUIDE: dict[str, str] = {
    "upload": """
Page: Invoices (dashboard)
- Upload invoice photo (JPG/PNG) — AI reads supplier, number, amount
- Or enter invoice manually without a photo
- Add new supplier from here or during review
- Pending items need your check before cheques can use them
""",
    "review": """
Page: Review / verify invoice
- Compare photo (if any) with extracted fields
- Fix mistakes before saving
- Register new supplier inline if needed
- Tick confirmation before verify
""",
    "cheques": """
Page: Cheques home
- Grid of suppliers with ready / waiting / on-cheque counts
- Click a supplier to open their cheque workspace
""",
    "dealer_cheques": """
Page: Supplier cheque workspace
- Left: select invoices, ceiling, bundle editor, preview & commit
- Right: Cheque Assistant (Agent 2) — ONLY place to bundle/split/date cheques via chat
- This Guide explains buttons and steps; Agent 2 performs bundling
""",
    "cash_flow": """
Page: Bank Balance
- Set current account balance
- Add planned deposits and mark complete
- 60-day timeline and liquidity alerts
""",
    "analytics": """
Page: Reports
- Metrics after cheques are committed
- Latest analyst commentary (Agent 3)
""",
    "dealer": """
Page: Supplier management
- Add or edit supplier name, contact, strictness
- Bank account details required before cheques
- Details tab vs Cheques tab on supplier hub
""",
}


def detect_page_section(page_path: str) -> str:
    path = (page_path or "/").split("?")[0] or "/"
    for pattern, section, _ in PAGE_PATTERNS:
        if pattern.search(path):
            return section
    return "default"


def page_tip_key(page_path: str) -> str:
    path = (page_path or "/").split("?")[0] or "/"
    for pattern, _, key in PAGE_PATTERNS:
        if pattern.search(path):
            return key
    return "guide_page_tip_default"


def guide_welcome_for_path(page_path: str, lang: str | None = None) -> str:
    return translate(page_tip_key(page_path), lang)


def build_guide_context(page_path: str, lang: str | None = None) -> str:
    section = detect_page_section(page_path)
    page_block = PAGE_GUIDE.get(section, "")
    tip = guide_welcome_for_path(page_path, lang)
    help_keys = ("help_tip_upload", "help_tip_cheques", "help_tip_cash")
    tips = "\n".join(f"- {translate(k, lang)}" for k in help_keys)

    return f"""{NAV_SECTIONS}

{WORKFLOWS}

{AGENT2_NOTE}

Current page path: {page_path or "/"}
Current section: {section}
Page tip for user: {tip}

{page_block}

Inline help tips from the app:
{tips}

{TROUBLESHOOTING}
"""
