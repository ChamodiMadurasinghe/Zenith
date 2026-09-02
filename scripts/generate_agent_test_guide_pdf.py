"""
Generate teammate Agent testing guide (PDF) + sample invoice images.

Usage:
  python scripts/generate_agent_test_guide_pdf.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image as RLImage,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
OUT_PDF = ROOT / "docs" / "Agent_Testing_Guide.pdf"
SAMPLES = ROOT / "docs" / "agent_test_samples"


def _font(size: int = 18):
    for name in ("arial.ttf", "Arial.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _draw_invoice(
    path: Path,
    *,
    title: str,
    supplier: str,
    invoice_no: str,
    inv_date: str,
    lines: list[tuple[str, str, float, float, float]],
    total: float,
    note: str = "",
):
    """lines: (code, name, qty, unit_price, discount_pct)"""
    img = Image.new("RGB", (900, 1200), "white")
    d = ImageDraw.Draw(img)
    f_title = _font(32)
    f = _font(20)
    f_sm = _font(16)

    y = 40
    d.text((40, y), supplier, fill=(20, 40, 80), font=f_title)
    y += 50
    d.text((40, y), title, fill=(80, 80, 80), font=f_sm)
    y += 40
    d.line((40, y, 860, y), fill=(200, 200, 200), width=2)
    y += 20
    d.text((40, y), f"Invoice No: {invoice_no}", fill=(0, 0, 0), font=f)
    d.text((480, y), f"Date: {inv_date}", fill=(0, 0, 0), font=f)
    y += 50
    d.text((40, y), "Bill To: Zenith Test Shop (Pvt) Ltd", fill=(0, 0, 0), font=f)
    y += 45
    d.rectangle((40, y, 860, y + 36), fill=(30, 60, 110))
    headers = [("Code", 50), ("Item", 160), ("Qty", 430), ("Unit Rs.", 520), ("Disc%", 670), ("Amount", 760)]
    for label, x in headers:
        d.text((x, y + 8), label, fill="white", font=f_sm)
    y += 40

    for code, name, qty, price, disc in lines:
        amt = qty * price * (1 - disc / 100.0)
        d.text((50, y), code, fill=(0, 0, 0), font=f_sm)
        d.text((160, y), name, fill=(0, 0, 0), font=f_sm)
        d.text((430, y), f"{qty:g}", fill=(0, 0, 0), font=f_sm)
        d.text((520, y), f"{price:,.2f}", fill=(0, 0, 0), font=f_sm)
        d.text((670, y), f"{disc:g}", fill=(0, 0, 0), font=f_sm)
        d.text((760, y), f"{amt:,.2f}", fill=(0, 0, 0), font=f_sm)
        y += 34
        d.line((40, y - 4, 860, y - 4), fill=(230, 230, 230), width=1)

    y += 20
    d.text((560, y), f"TOTAL: Rs. {total:,.2f}", fill=(0, 0, 0), font=f_title)
    if note:
        y += 60
        d.text((40, y), note, fill=(120, 40, 40), font=f_sm)

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def make_sample_images() -> dict[str, Path]:
    from datetime import date, timedelta

    files = {}
    files["clean"] = SAMPLES / "01_clean_invoice.png"
    _draw_invoice(
        files["clean"],
        title="TAX INVOICE",
        supplier="City Mart Suppliers",
        invoice_no="CM-TEST-1001",
        inv_date="2026-09-01",
        lines=[
            ("TOFFEE-01", "Milk Toffees 50g", 10, 100.0, 0),
            ("TEA-02", "Ceylon Tea 200g", 5, 450.0, 0),
        ],
        total=3250.0,
        note="Agent 1 happy path + Agent 2 GOOD_TO_GO (after history).",
    )

    files["math"] = SAMPLES / "02_math_mismatch.png"
    _draw_invoice(
        files["math"],
        title="TAX INVOICE — MATH ERROR",
        supplier="City Mart Suppliers",
        invoice_no="CM-TEST-1002",
        inv_date="2026-09-01",
        lines=[("WIRE-01", "Copper Wire 1mm", 2, 400.0, 0)],
        total=1000.0,
        note="Lines=800 header=1000 → math_mismatch",
    )

    files["discount"] = SAMPLES / "03_missing_discount.png"
    _draw_invoice(
        files["discount"],
        title="TAX INVOICE — DISCOUNT NOT IN TOTAL",
        supplier="City Mart Suppliers",
        invoice_no="CM-TEST-1003",
        inv_date="2026-09-01",
        lines=[("SKU-D1", "Discounted Goods", 10, 100.0, 10)],
        total=1000.0,
        note="Disc 10% but total=1000 → possible_missing_discount",
    )

    files["qty"] = SAMPLES / "04_qty_unusual_toffees.png"
    _draw_invoice(
        files["qty"],
        title="TAX INVOICE — QTY SPIKE",
        supplier="City Mart Suppliers",
        invoice_no="CM-TEST-1004",
        inv_date="2026-09-01",
        lines=[("TOFFEE-01", "Milk Toffees 50g", 20, 100.0, 0)],
        total=2000.0,
        note="After ~10 toffees history → qty_unusual",
    )

    files["messy"] = SAMPLES / "05_messy_handwritten_style.png"
    img = Image.new("RGB", (900, 1100), (252, 250, 240))
    d = ImageDraw.Draw(img)
    f = _font(22)
    f_sm = _font(18)
    d.text((60, 50), "ABANS PLC - COLOMBO", fill=(40, 40, 40), font=_font(28))
    d.text((60, 100), "Invoice: AB-77821", fill=(40, 40, 40), font=f)
    d.text((520, 100), "Date 28/08/2026", fill=(40, 40, 40), font=f)
    d.text((60, 160), "Item: LED Bulb 9W x 12 @ Rs.850", fill=(20, 20, 20), font=f)
    d.text((60, 210), "Item: Extension Cord 5m x 3 @ Rs.1,250", fill=(20, 20, 20), font=f)
    d.text((60, 280), "TOTAL DUE  Rs. 13,950.00", fill=(0, 0, 0), font=_font(26))
    d.text((60, 360), "(Photo / upload for OCR stress test)", fill=(100, 100, 100), font=f_sm)
    files["messy"].parent.mkdir(parents=True, exist_ok=True)
    img.save(files["messy"])

    future = (date.today() + timedelta(days=60)).isoformat()
    files["future"] = SAMPLES / "06_future_date.png"
    _draw_invoice(
        files["future"],
        title="TAX INVOICE — FUTURE DATE",
        supplier="City Mart Suppliers",
        invoice_no="CM-TEST-1006",
        inv_date=future,
        lines=[("TEA-02", "Ceylon Tea 200g", 2, 450.0, 0)],
        total=900.0,
        note=f"Date {future} → Agent 2 future_date",
    )

    files["price"] = SAMPLES / "07_price_spike.png"
    _draw_invoice(
        files["price"],
        title="TAX INVOICE — PRICE SPIKE",
        supplier="City Mart Suppliers",
        invoice_no="CM-TEST-1007",
        inv_date="2026-09-01",
        lines=[("TOFFEE-01", "Milk Toffees 50g", 10, 250.0, 0)],
        total=2500.0,
        note="After history @ Rs.100 → item_price_spike",
    )

    files["outlier"] = SAMPLES / "08_amount_outlier.png"
    _draw_invoice(
        files["outlier"],
        title="TAX INVOICE — HUGE TOTAL",
        supplier="City Mart Suppliers",
        invoice_no="CM-TEST-1008",
        inv_date="2026-09-01",
        lines=[("BULK-01", "Bulk Order Pack", 1, 50000.0, 0)],
        total=50000.0,
        note="If dealer avg ~10k → amount_outlier (>3x)",
    )

    files["zero"] = SAMPLES / "09_missing_amount.png"
    _draw_invoice(
        files["zero"],
        title="TAX INVOICE — ZERO TOTAL",
        supplier="Unknown New Dealer Co",
        invoice_no="CM-TEST-1009",
        inv_date="2026-09-01",
        lines=[("X-1", "Mystery Item", 1, 0.0, 0)],
        total=0.0,
        note="missing_amount + often unknown_dealer",
    )

    # Bundling helper sheet (not OCR — numbers for Agent 3/4 setup)
    files["bundle_sheet"] = SAMPLES / "10_bundling_setup_sheet.png"
    img = Image.new("RGB", (1000, 1400), "white")
    d = ImageDraw.Draw(img)
    y = 40
    d.text((40, y), "AGENT 3 / 4 BUNDLING SETUP SHEET", fill=(20, 40, 80), font=_font(28))
    y += 50
    d.text((40, y), "Create & VERIFY these 3 invoices for ONE dealer (e.g. City Mart).", fill=(0, 0, 0), font=_font(18))
    y += 40
    rows = [
        "Inv CM-B1  | amount 180,000 | invoiced today-40d | credit 30d",
        "Inv CM-B2  | amount 220,000 | invoiced today-20d | credit 30d",
        "Inv CM-B3  | amount 160,000 | invoiced today-5d  | credit 30d",
        "",
        "Cash flow: bank account balance >= 100,000 (or OD).",
        "Ceiling: set bundling ceiling to 250,000 LKR for split test.",
        "Then Bundling → dealer → Compute (Agent 3) → Review (Agent 4).",
        "",
        "INTERBANK test: dealer preferred bank = Commercial,",
        "  paying account bank = Sampath (or different) → clearing INTERBANK.",
        "CEILING test: set ceiling 200,000 with invoices totaling 560,000",
        "  → expect multiple cheques / guardrail warning if one exceeds.",
        "HOLIDAY test: put a cheque date on a Sunday or CBSL holiday",
        "  → expect shift / warning from guardrails / float logic.",
        "Agent 4: switch UI lang EN → SI → TA and re-open review.",
    ]
    for line in rows:
        d.text((40, y), line, fill=(30, 30, 30), font=_font(17))
        y += 32
    img.save(files["bundle_sheet"])
    return files


def _styles():
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "T",
            parent=base["Title"],
            fontSize=20,
            spaceAfter=8,
            textColor=colors.HexColor("#1a3358"),
        ),
        "h1": ParagraphStyle(
            "H1",
            parent=base["Heading1"],
            fontSize=14,
            spaceBefore=14,
            spaceAfter=6,
            textColor=colors.HexColor("#1a3358"),
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontSize=12,
            spaceBefore=10,
            spaceAfter=4,
            textColor=colors.HexColor("#2c4a6e"),
        ),
        "body": ParagraphStyle(
            "B",
            parent=base["BodyText"],
            fontSize=9.5,
            leading=13,
            spaceAfter=4,
        ),
        "small": ParagraphStyle(
            "S",
            parent=base["BodyText"],
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#444444"),
        ),
        "pass": ParagraphStyle(
            "P",
            parent=base["BodyText"],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#0d6b3a"),
            leftIndent=8,
        ),
        "fail": ParagraphStyle(
            "F",
            parent=base["BodyText"],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#8a1f1f"),
            leftIndent=8,
        ),
        "center": ParagraphStyle("C", parent=base["Normal"], alignment=TA_CENTER, fontSize=9),
    }
    return styles


def _table(data, col_widths=None):
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3358")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("LEADING", (0, 0), (-1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8d0dc")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7fa")]),
            ]
        )
    )
    return t


def build_pdf(sample_files: dict[str, Path]):
    styles = _styles()
    story = []
    W = A4[0] - 36 * mm

    story.append(Paragraph("Zenith / ChequeMate — Agent Testing Guide", styles["title"]))
    story.append(
        Paragraph(
            "For teammates: concrete examples to confirm Agents 1–4 work in the running app. "
            "Soft-warn only for Agent 2 — you can still verify after reading warnings.",
            styles["body"],
        )
    )
    story.append(
        Paragraph(
            "Generated for local QA. App: http://127.0.0.1:5000 · Sample images: docs/agent_test_samples/",
            styles["small"],
        )
    )

    story.append(Paragraph("0. Before you start", styles["h1"]))
    story.append(
        ListFlowable(
            [
                ListItem(Paragraph("Start app: <font face='Courier'>python app.py</font>", styles["body"])),
                ListItem(
                    Paragraph(
                        "Log in with the password from <font face='Courier'>.env</font> (<font face='Courier'>APP_PASSWORD</font>).",
                        styles["body"],
                    )
                ),
                ListItem(
                    Paragraph(
                        "Confirm <font face='Courier'>USE_FAKE_AI=false</font> and <font face='Courier'>GEMINI_API_KEY</font> is set "
                        "(Agents 1, 3, 4). Agent 2 is SQLite/rules only — no Gemini.",
                        styles["body"],
                    )
                ),
                ListItem(
                    Paragraph(
                        "Optional seed history (helps Agent 2 qty/reorder tests): "
                        "<font face='Courier'>python scripts/seed_sample_invoices.py</font>",
                        styles["body"],
                    )
                ),
            ],
            bulletType="bullet",
            leftIndent=12,
        )
    )

    story.append(Paragraph("1. Quick map — which screen tests which agent?", styles["h1"]))
    story.append(
        _table(
            [
                ["Agent", "What it does", "Where to look", "AI?"],
                ["1 Vision", "OCR invoice fields from photo/PDF", "Upload → Review draft", "Gemini"],
                ["2 Anomaly", "Math, discount, qty, reorder, chat panel", "Review / Verify page (top card)", "Rules/DB"],
                ["3 Strategist", "Propose cheque splits & dates", "Bundling → Compute / AI plan", "Gemini"],
                ["4 Reviewer", "Plain-language teacher explanation", "Bundling chat / review panel", "Gemini"],
            ],
            col_widths=[W * 0.16, W * 0.32, W * 0.32, W * 0.2],
        )
    )

    # --- Agent 1 ---
    story.append(Paragraph("2. Agent 1 — Vision (OCR)", styles["h1"]))
    story.append(
        Paragraph(
            "<b>How:</b> Invoices → Upload → choose a sample PNG from <font face='Courier'>docs/agent_test_samples/</font> "
            "→ open the review draft.",
            styles["body"],
        )
    )
    story.append(Paragraph("Test cases", styles["h2"]))
    story.append(
        _table(
            [
                ["ID", "Upload this", "Expect on review form", "Pass if…"],
                [
                    "A1-1",
                    "01_clean_invoice.png",
                    "Supplier ≈ City Mart; Inv CM-TEST-1001; date 2026-09-01; "
                    "lines TOFFEE-01 qty 10 @ 100, TEA-02 qty 5 @ 450; total ≈ 3250",
                    "Key fields filled; total within ~Rs. 1–50 of 3250",
                ],
                [
                    "A1-2",
                    "05_messy_handwritten_style.png",
                    "Abans; AB-77821; total ≈ 13950; two line items roughly correct",
                    "Invoice no + total captured; lines mostly usable",
                ],
                [
                    "A1-3",
                    "Any non-invoice photo (selfie / random)",
                    "Reject or weak extraction + warning",
                    "App does not silently invent a perfect invoice",
                ],
            ],
            col_widths=[W * 0.08, W * 0.22, W * 0.42, W * 0.28],
        )
    )
    story.append(Paragraph("PASS: Fields editable and close to sample. FAIL: Blank form or wildly wrong total.", styles["pass"]))

    story.append(Spacer(1, 6))
    story.append(
        Paragraph(
            "Sample PNGs in <font face='Courier'>docs/agent_test_samples/</font> "
            "(01–09 invoices + 10 bundling setup sheet).",
            styles["small"],
        )
    )
    preview_row = []
    for key in ("clean", "math", "qty"):
        p = sample_files.get(key)
        if p and p.exists():
            preview_row.append(RLImage(str(p), width=48 * mm, height=64 * mm, kind="proportional"))
    if preview_row:
        story.append(Spacer(1, 4))
        story.append(Table([preview_row], colWidths=[W / 3.0] * len(preview_row)))

    # --- Agent 2 ---
    story.append(PageBreak())
    story.append(Paragraph("3. Agent 2 — Anomaly audit (chat panel) — expanded", styles["h1"]))
    story.append(
        Paragraph(
            "<b>How:</b> After Agent 1, stay on <b>Review</b> or open <b>Verify</b>. Agent 2 card shows "
            "status badge + chat bubbles + findings. Soft warn only — confirm-matches checkbox still saves.",
            styles["body"],
        )
    )
    story.append(
        Paragraph(
            "Automated check (dev): <font face='Courier'>python -m unittest agents.tests.test_anomaly_audit -q</font>",
            styles["small"],
        )
    )

    story.append(Paragraph("3.1 Always-on (no / little history)", styles["h2"]))
    story.append(
        _table(
            [
                ["ID", "Setup", "Expect code / status", "Pass if…"],
                [
                    "A2-1",
                    "Upload 02_math_mismatch.png (or qty2×400 total1000)",
                    "math_mismatch · ISSUE_DETECTED · HIGH",
                    "Chat mentions line vs header total",
                ],
                [
                    "A2-2",
                    "Upload 03_missing_discount.png",
                    "possible_missing_discount",
                    "Warns discount may not be in total",
                ],
                [
                    "A2-3",
                    "Upload 06_future_date.png (or date = today+60d)",
                    "future_date · HIGH",
                    "Flags date &gt; 30 days ahead",
                ],
                [
                    "A2-4",
                    "On review set invoiced_date to today−400 days",
                    "stale_date · MEDIUM",
                    "Warns invoice older than 1 year",
                ],
                [
                    "A2-5",
                    "Upload 09_missing_amount.png (total 0 + supplier name)",
                    "missing_amount · HIGH",
                    "Blocks silent zero-amount approve cue",
                ],
                [
                    "A2-6",
                    "Unknown supplier name, dealer not matched (dealer_id empty)",
                    "unknown_dealer · LOW",
                    "Asks to pick correct dealer",
                ],
                [
                    "A2-7",
                    "Verify CM-TEST-1001; re-upload same invoice no + dealer",
                    "duplicate_invoice_no · HIGH",
                    "Warns number already exists",
                ],
                [
                    "A2-8",
                    "New dealer; clean math; no item history",
                    "INSUFFICIENT_DATA or GOOD_TO_GO; chat still present",
                    "Panel does not crash / blank forever",
                ],
            ],
            col_widths=[W * 0.1, W * 0.34, W * 0.28, W * 0.28],
        )
    )

    story.append(Paragraph("3.2 History-dependent (seed City Mart + TOFFEE-01 ≈ qty 10 @ 100)", styles["h2"]))
    story.append(
        Paragraph(
            "Seed: verify 3–8 invoices for <b>City Mart Suppliers</b> with <font face='Courier'>TOFFEE-01</font> "
            "qty≈10 price≈100. Optional: <font face='Courier'>python scripts/seed_sample_invoices.py</font> then adjust.",
            styles["body"],
        )
    )
    story.append(
        _table(
            [
                ["ID", "Action", "Expect", "Pass if…"],
                [
                    "A2-9",
                    "Upload 04_qty_unusual_toffees.png (qty 20)",
                    "qty_unusual · MEDIUM · needs_confirmation",
                    "Chat ≈ usually ~10, this has 20",
                ],
                [
                    "A2-10",
                    "Upload 07_price_spike.png (price 250 after avg 100)",
                    "item_price_spike",
                    "Mentions unusual unit price",
                ],
                [
                    "A2-11",
                    "Upload 08_amount_outlier.png if dealer avg ≪ 50k (≥3 prior invoices)",
                    "amount_outlier",
                    "Total much higher than dealer average",
                ],
                [
                    "A2-12",
                    "Verify invoice with TOFFEE-01; within 30 days upload another with TOFFEE-01",
                    "item_reordered_soon · LOW",
                    "Mentions prior invoice # / date",
                ],
                [
                    "A2-13",
                    "Combine: qty 20 + recent reorder on same item",
                    "Both qty_unusual and item_reordered_soon",
                    "Multiple chat bubbles / findings listed",
                ],
                [
                    "A2-14 Soft warn",
                    "Any ISSUE_DETECTED → tick confirm matches → verify",
                    "Save OK — no per-finding hard block",
                    "Invoice verified=1",
                ],
                [
                    "A2-15 UI",
                    "Open review when status ≠ GOOD_TO_GO",
                    "Chat auto-expands (agent2_review.js)",
                    "Bubbles visible without hunting",
                ],
            ],
            col_widths=[W * 0.12, W * 0.34, W * 0.28, W * 0.26],
        )
    )

    story.append(Paragraph("3.3 Quick type-in matrix (no photo)", styles["h2"]))
    story.append(
        _table(
            [
                ["Scenario", "Line / header values", "Expected code"],
                ["Math", "qty2 price400 disc0 · total 1000", "math_mismatch"],
                ["Discount", "qty10 price100 disc10 · total 1000", "possible_missing_discount"],
                ["Qty*", "TOFFEE-01 qty20 price100 · total 2000", "qty_unusual"],
                ["Price*", "TOFFEE-01 qty10 price250 · total 2500", "item_price_spike"],
                ["Future", "date = today+60 · total matches lines", "future_date"],
                ["Stale", "date = today−400 · total matches lines", "stale_date"],
                ["Zero amt", "supplier set · total 0", "missing_amount"],
                ["Clean", "qty10 price100 · total 1000", "GOOD_TO_GO / INSUFFICIENT_DATA"],
            ],
            col_widths=[W * 0.18, W * 0.52, W * 0.3],
        )
    )

    # --- Agent 3 ---
    story.append(PageBreak())
    story.append(Paragraph("4. Agent 3 — Strategist (cheque plan) — expanded", styles["h1"]))
    story.append(
        Paragraph(
            "<b>How:</b> Verify invoices → <b>Bundling</b> → pick dealer → set ceiling → <b>Compute</b> "
            "(<font face='Courier'>POST /bundling/&lt;dealer_id&gt;/compute</font>). "
            "Uses Gemini strategist; on failure falls back to Python <font face='Courier'>compute_bundles</font>. "
            "Setup sheet: <font face='Courier'>10_bundling_setup_sheet.png</font>.",
            styles["body"],
        )
    )
    story.append(
        Paragraph(
            "Automated check: <font face='Courier'>python -m unittest agents.tests.test_strategist agents.tests.test_strategist_dates -q</font>",
            styles["small"],
        )
    )
    story.append(
        _table(
            [
                ["ID", "Setup", "Expect", "Pass if…"],
                [
                    "A3-1 Happy",
                    "3 verified invoices (CM-B1/B2/B3 from setup sheet); ceiling 500k; balance OK",
                    "proposed_cheques with amounts, dates, account ids; strategy_summary",
                    "UI shows cheque groups covering all selected invoices",
                ],
                [
                    "A3-2 Ceiling split",
                    "Same 3 invoices (~560k) with ceiling <b>200,000</b>",
                    "Multiple cheques under ceiling OR clear split reasoning",
                    "No single cheque casually above ceiling without warning",
                ],
                [
                    "A3-3 Guardrail exceed",
                    "Force one group above ceiling (drag / edit) then validate",
                    "Guardrail issue: exceeds ceiling",
                    "Warning visible before commit",
                ],
                [
                    "A3-4 Interbank",
                    "Dealer bank ≠ paying account bank",
                    "clearing_type INTERBANK on relevant cheque(s)",
                    "Interbank / float note in plan or liquidity enrichment",
                ],
                [
                    "A3-5 Intrabank",
                    "Dealer preferred bank = paying account bank",
                    "INTRABANK (or not marked interbank)",
                    "No false interbank flag",
                ],
                [
                    "A3-6 Holiday / weekend float",
                    "Target date on Sunday or CBSL holiday (see Cash flow holidays)",
                    "Date shifted to business day / float suggestion",
                    "Not left on a known holiday without note",
                ],
                [
                    "A3-7 Empty selection",
                    "Compute with no invoices selected",
                    "Friendly empty plan / no crash",
                    "Clear message, page usable",
                ],
                [
                    "A3-8 Fallback",
                    "Optional: bad GEMINI key or USE_FAKE_AI=true",
                    "Mock or Python fallback still returns cheques",
                    "Bundling page does not 500",
                ],
                [
                    "A3-9 Amount conservation",
                    "After compute, sum cheque amounts ≈ sum invoice amounts",
                    "Within small rounding",
                    "No silent drop of an invoice amount",
                ],
                [
                    "A3-10 Account pick",
                    "≥2 shop bank accounts; compute",
                    "selected_shop_account_id present on cheques",
                    "Uses a real account id from Cash flow",
                ],
            ],
            col_widths=[W * 0.12, W * 0.34, W * 0.28, W * 0.26],
        )
    )

    # --- Agent 4 ---
    story.append(Paragraph("5. Agent 4 — Reviewer (teacher tone) — expanded", styles["h1"]))
    story.append(
        Paragraph(
            "<b>How:</b> After Agent 3 compute, open bundling <b>review / chat</b> panel (Agent 4 runs on compute/preview). "
            "First line of model output is <font face='Courier'>VERDICT: approve</font> or "
            "<font face='Courier'>VERDICT: suggest_changes</font>; UI shows plain-language teacher explanation.",
            styles["body"],
        )
    )
    story.append(
        _table(
            [
                ["ID", "Action", "Expect", "Pass if…"],
                [
                    "A4-1 EN approve path",
                    "Healthy plan, UI English, trigger compute",
                    "Verdict approve (or suggest_changes with reasons); informal EN prose",
                    "Shop owner can understand dates/amounts",
                ],
                [
                    "A4-2 Suggest changes",
                    "Tight cash / ceiling issues in validation_issues",
                    "VERDICT suggest_changes + concrete advice",
                    "Does not blindly approve a broken plan",
                ],
                [
                    "A4-3 Sinhala",
                    "Set UI lang <b>si</b> → re-run review",
                    "Review text in Sinhala (or mostly SI)",
                    "Not pure English when UI is SI",
                ],
                [
                    "A4-4 Tamil",
                    "Set UI lang <b>ta</b> → re-run review",
                    "Review text in Tamil (or mostly TA)",
                    "Not pure English when UI is TA",
                ],
                [
                    "A4-5 Mentions plan facts",
                    "Note cheque dates & totals from Agent 3",
                    "Review references those numbers / counts",
                    "Not a generic unrelated essay",
                ],
                [
                    "A4-6 Preview trigger",
                    "If UI has preview review without commit",
                    "Review still returns; no crash",
                    "trigger=preview path works",
                ],
                [
                    "A4-7 Apply suggestions (optional)",
                    "If Apply suggestions button exists after suggest_changes",
                    "proposed_actions / updated groups",
                    "Actions applied or clear failure message",
                ],
                [
                    "A4-8 Gemini required",
                    "USE_FAKE_AI=false + valid GEMINI_API_KEY",
                    "Real Gemini text (not empty)",
                    "Provider gemini; no silent blank panel",
                ],
            ],
            col_widths=[W * 0.14, W * 0.32, W * 0.28, W * 0.26],
        )
    )

    # --- E2E ---
    story.append(Paragraph("6. End-to-end smoke (45 minutes)", styles["h1"]))
    story.append(
        ListFlowable(
            [
                ListItem(Paragraph("A1: Upload 01_clean → fields OK.", styles["body"])),
                ListItem(Paragraph("A2: Upload 02_math → math_mismatch chat; still verify with confirm.", styles["body"])),
                ListItem(Paragraph("A2: Seed toffees → upload 04_qty → qty_unusual.", styles["body"])),
                ListItem(Paragraph("Create CM-B1/B2/B3 (sheet 10) → verify all three.", styles["body"])),
                ListItem(Paragraph("A3: Bundling compute ceiling 200k → multi-cheque plan.", styles["body"])),
                ListItem(Paragraph("A4: Read EN review; switch SI or TA; confirm language shift.", styles["body"])),
                ListItem(Paragraph("Optional commit only on a disposable test DB.", styles["body"])),
            ],
            bulletType="1",
            leftIndent=14,
        )
    )

    story.append(Paragraph("7. Sign-off checklist", styles["h1"]))
    story.append(
        _table(
            [
                ["#", "Check", "Tester", "Pass?"],
                ["1", "A1 OCR 01_clean", "", "☐"],
                ["2", "A2 math_mismatch 02", "", "☐"],
                ["3", "A2 missing discount 03", "", "☐"],
                ["4", "A2 future_date 06", "", "☐"],
                ["5", "A2 qty_unusual 04 (history)", "", "☐"],
                ["6", "A2 price_spike 07 (history)", "", "☐"],
                ["7", "A2 reorder within 30d", "", "☐"],
                ["8", "A2 soft-warn verify allowed", "", "☐"],
                ["9", "A3 happy compute", "", "☐"],
                ["10", "A3 ceiling split 200k", "", "☐"],
                ["11", "A3 interbank when banks differ", "", "☐"],
                ["12", "A3 amount conservation", "", "☐"],
                ["13", "A4 EN review + verdict", "", "☐"],
                ["14", "A4 suggest_changes on risky plan", "", "☐"],
                ["15", "A4 SI or TA language", "", "☐"],
                ["16", "Unit tests green (anomaly+strategist)", "", "☐"],
            ],
            col_widths=[W * 0.08, W * 0.52, W * 0.2, W * 0.2],
        )
    )

    story.append(Spacer(1, 12))
    story.append(
        Paragraph(
            "Notes / bugs found: ________________________________________________________________",
            styles["body"],
        )
    )
    story.append(
        Paragraph(
            "________________________________________________________________________________",
            styles["body"],
        )
    )
    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            "WhatsApp inbox-v2 unchanged: Inbox → Send to AI → same Verify + Agent 2 panel. "
            "Regenerate this PDF: <font face='Courier'>python scripts/generate_agent_test_guide_pdf.py</font>",
            styles["small"],
        )
    )

    OUT_PDF.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUT_PDF),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="Zenith Agent Testing Guide",
        author="Zenith QA",
    )
    doc.build(story)
    return OUT_PDF


def main():
    samples = make_sample_images()
    pdf = build_pdf(samples)
    print(f"Wrote {pdf}")
    print(f"Samples in {SAMPLES}")
    for p in samples.values():
        print(f"  - {p.name}")


if __name__ == "__main__":
    main()
