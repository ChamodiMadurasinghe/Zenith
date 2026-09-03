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
    footer: str = "",
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
    if footer:
        y += 40
        for i, line in enumerate(footer.split("\n")):
            d.text((40, y + i * 26), line, fill=(40, 40, 40), font=f_sm)

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

    files["mrp"] = SAMPLES / "11_mrp_vs_sell.png"
    _draw_invoice(
        files["mrp"],
        title="TAX INVOICE — MRP vs SELLING PRICE",
        supplier="City Mart Suppliers",
        invoice_no="CM-TEST-1011",
        inv_date="2026-09-01",
        lines=[("RICE-10", "Nadu Rice 10kg", 4, 1850.0, 0)],
        total=7400.0,
        note="Printed MRP 2,200 | Sell 1,850 — OCR should fill item_mrp and item_price.",
        footer="MRP Rs. 2,200.00   Unit sell Rs. 1,850.00   Line total Rs. 7,400.00",
    )

    files["bank"] = SAMPLES / "12_supplier_bank_footer.png"
    _draw_invoice(
        files["bank"],
        title="TAX INVOICE — SUPPLIER BANK",
        supplier="Lanka Hardware Traders",
        invoice_no="LH-4412",
        inv_date="2026-08-15",
        lines=[("BOLT-M8", "Hex Bolt M8", 100, 25.0, 0)],
        total=2500.0,
        note="OCR should pick bank fields from footer.",
        footer="Acc: LANKA HARDWARE TRADERS\nBank: Commercial Bank of Ceylon  Branch: Pettah\nA/C 1234567890  Tel 011-2345678  email sales@lankahw.lk",
    )

    files["credit"] = SAMPLES / "13_credit_period.png"
    _draw_invoice(
        files["credit"],
        title="TAX INVOICE — CREDIT 45 DAYS",
        supplier="City Mart Suppliers",
        invoice_no="CM-TEST-1013",
        inv_date="2026-09-01",
        lines=[("TEA-02", "Ceylon Tea 200g", 8, 450.0, 0)],
        total=3600.0,
        note="Payment terms: Net 45 days → credit_period_days ≈ 45.",
        footer="Payment: Net 45 days from invoice date. Cheques payable to City Mart Suppliers.",
    )

    files["twodisc"] = SAMPLES / "14_two_discount_lines.png"
    _draw_invoice(
        files["twodisc"],
        title="TAX INVOICE — TWO DISCOUNTED LINES",
        supplier="City Mart Suppliers",
        invoice_no="CM-TEST-1014",
        inv_date="2026-09-01",
        lines=[
            ("SKU-A", "Carton A", 5, 200.0, 5),
            ("SKU-B", "Carton B", 2, 500.0, 10),
        ],
        total=1850.0,
        note="5×200×0.95 + 2×500×0.90 = 950+900 = 1850. Header must match.",
    )

    files["phone_photo"] = SAMPLES / "15_phone_photo_glare.png"
    img = Image.new("RGB", (900, 1100), (35, 32, 28))
    d = ImageDraw.Draw(img)
    d.rectangle((80, 70, 820, 980), fill=(245, 242, 230))
    d.ellipse((620, 90, 780, 220), fill=(255, 255, 240))
    f = _font(20)
    d.text((110, 120), "SOFTLOGIC RETAIL", fill=(30, 30, 30), font=_font(26))
    d.text((110, 170), "Inv SL-9901    12 Aug 2026", fill=(40, 40, 40), font=f)
    d.text((110, 230), "Mouse wireless x 2  @ 3,450", fill=(20, 20, 20), font=f)
    d.text((110, 270), "USB hub x 1         @ 1,890", fill=(20, 20, 20), font=f)
    d.text((110, 340), "TOTAL  Rs. 8,790.00", fill=(0, 0, 0), font=_font(24))
    d.text((110, 420), "(Simulate phone photo + glare for OCR)", fill=(90, 90, 90), font=_font(16))
    files["phone_photo"].parent.mkdir(parents=True, exist_ok=True)
    img.save(files["phone_photo"])

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
        "ex": ParagraphStyle(
            "EX",
            parent=base["BodyText"],
            fontSize=8.5,
            leading=11.5,
            leftIndent=6,
            backColor=colors.HexColor("#eef3f8"),
            borderPadding=4,
            spaceAfter=6,
        ),
    }
    return styles


def _cell(text, styles, key="small"):
    return Paragraph(str(text).replace("\n", "<br/>"), styles[key])


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
    s = styles

    def header_row(cells):
        hdr = ParagraphStyle(
            "TH",
            parent=s["small"],
            textColor=colors.white,
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
        )
        return [Paragraph(str(c), hdr) for c in cells]

    def T(headers, rows, widths):
        data = [header_row(headers)]
        for r in rows:
            data.append([_cell(c, s) for c in r])
        return _table(data, col_widths=widths)

    story.append(Paragraph("Zenith / ChequeMate — Agent Testing Guide", styles["title"]))
    story.append(
        Paragraph(
            "Hands-on QA book for teammates. Each case has a <b>setup</b>, <b>exact numbers</b>, "
            "<b>what the screen should show</b>, and a pass/fail line. "
            "Agent 2 is soft-warn only — you can still verify after reading warnings.",
            styles["body"],
        )
    )
    story.append(
        Paragraph(
            "App: http://127.0.0.1:5000 · Samples: docs/agent_test_samples/ (01–15) · "
            "Regenerate: python scripts/generate_agent_test_guide_pdf.py",
            styles["small"],
        )
    )

    story.append(Paragraph("0. Before you start", styles["h1"]))
    story.append(
        ListFlowable(
            [
                ListItem(Paragraph("Start app: <font face='Courier'>python app.py</font> then log in with <font face='Courier'>APP_PASSWORD</font> from .env.", styles["body"])),
                ListItem(Paragraph("<b>Real OCR / Agents 3–4:</b> USE_FAKE_AI=false and a working GEMINI_API_KEY. If you see 403 PERMISSION_DENIED, Gemini is blocked — fix the key/project; code is fine.", styles["body"])),
                ListItem(Paragraph("<b>Bundling chat</b> (the chat box on Bundling) uses OPENAI_API_KEY. It can work even when Gemini OCR fails.", styles["body"])),
                ListItem(Paragraph("<b>Agent 2</b> is Python + SQLite only — no API key.", styles["body"])),
                ListItem(Paragraph("Optional history seed: <font face='Courier'>python scripts/seed_sample_invoices.py</font> (helps qty/price/reorder tests).", styles["body"])),
                ListItem(Paragraph("Use a throwaway local DB for verify/commit tests. Do not commit real cheques on production data.", styles["body"])),
            ],
            bulletType="bullet",
            leftIndent=12,
        )
    )

    story.append(Paragraph("1. Quick map — what to click", styles["h1"]))
    story.append(
        T(
            ["Piece", "Job", "Where", "Needs"],
            [
                ["Agent 1 Vision", "OCR fields from photo/PDF", "Invoices → Upload → Review draft", "Gemini"],
                ["WhatsApp inbox", "Photo wait, then same OCR", "Invoices → WhatsApp photos → Send to AI", "Meta webhook + Gemini"],
                ["Agent 2 Anomaly", "Math, dates, qty, price, reorder", "Review / Verify (top chat card)", "Rules/DB only"],
                ["Agent 3 Strategist", "Propose cheque splits & dates", "Bundling → dealer → Compute", "Gemini (Python fallback)"],
                ["Agent 4 Reviewer", "Plain-language plan explanation", "Bundling review after compute", "Gemini"],
                ["Bundling assistant", "Chat: split / date / ceiling", "Bundling page chat", "OpenAI"],
                ["App Guide", "How-to helper (not bundling)", "Floating widget (non-cheque pages)", "OpenAI/text"],
            ],
            [W * 0.18, W * 0.30, W * 0.32, W * 0.20],
        )
    )

    story.append(Paragraph("Lifecycle reminder", styles["h2"]))
    story.append(
        Paragraph(
            "Intake (upload or WhatsApp) → Agent 1 OCR → Agent 2 audit → <b>human Verify</b> → "
            "Agent 3 plan → guardrails (holidays, ceiling) → Agent 4 review → optional Commit cheques.",
            styles["body"],
        )
    )

    # --- Agent 1 ---
    story.append(Paragraph("2. Agent 1 — Vision (OCR)", styles["h1"]))
    story.append(
        Paragraph(
            "<b>How:</b> Invoices → Upload → pick a PNG from docs/agent_test_samples/ → wait for review. "
            "On WhatsApp: photo lands in <b>WhatsApp photos</b> first; click <b>Send to AI</b> (OCR does not run on webhook receive).",
            styles["body"],
        )
    )

    story.append(Paragraph("2.1 Worked example — clean invoice (01_clean_invoice.png)", styles["h2"]))
    story.append(
        Paragraph(
            "<b>Printed:</b> City Mart Suppliers · CM-TEST-1001 · 2026-09-01 · "
            "TOFFEE-01 qty 10 @ Rs.100 · TEA-02 qty 5 @ Rs.450 · TOTAL Rs. 3,250.00",
            styles["body"],
        )
    )
    story.append(
        Paragraph(
            "<b>Arithmetic:</b> 10 × 100 = 1,000; 5 × 450 = 2,250; 1,000 + 2,250 = <b>3,250</b>. "
            "Review form should be within about Rs. 50 of that total. Line names/codes may vary slightly (OCR).",
            styles["body"],
        )
    )
    story.append(
        Paragraph(
            "<b>PASS:</b> Supplier contains City Mart; invoice no contains 1001; two lines; total near 3250. "
            "<b>FAIL:</b> Blank form, total 0, or a totally different supplier invented.",
            styles["pass"],
        )
    )

    story.append(Paragraph("2.2 Worked example — math trap (02_math_mismatch.png)", styles["h2"]))
    story.append(
        Paragraph(
            "Line: WIRE-01 qty 2 @ Rs.400 → line amount <b>800</b>. Header TOTAL is printed as <b>1,000</b>. "
            "Agent 1 should still extract both numbers. Agent 2 (next section) then flags math_mismatch. "
            "Do not “fix” the total in your head — leave OCR as-is so Agent 2 can fire.",
            styles["body"],
        )
    )

    story.append(Paragraph("2.3 Worked example — MRP vs sell (11_mrp_vs_sell.png)", styles["h2"]))
    story.append(
        Paragraph(
            "Rice 10kg × 4. Footer says MRP 2,200 and sell 1,850. Line total 4 × 1,850 = <b>7,400</b>. "
            "On review, <b>MRP</b> ≈ 2200, <b>Single price</b> ≈ 1850, <b>Total price</b> ≈ 7400. "
            "PASS if selling price is not overwritten with MRP.",
            styles["body"],
        )
    )

    story.append(Paragraph("2.4 Upload / photo test cases", styles["h2"]))
    story.append(
        T(
            ["ID", "File", "Expect on review", "Pass if"],
            [
                ["A1-1", "01_clean_invoice.png", "City Mart; CM-TEST-1001; 2026-09-01; TOFFEE qty10 @100; TEA qty5 @450; total ≈3250", "Key fields filled; total within ~Rs.50 of 3250"],
                ["A1-2", "05_messy_handwritten_style.png", "Abans / AB-77821; two items (bulb ~12×850, cord ~3×1250); total ≈13950", "Invoice no + total captured; lines usable"],
                ["A1-3", "15_phone_photo_glare.png", "Softlogic; SL-9901; total ≈8790; mouse ×2 and USB hub", "Reads through glare; does not invent extra SKUs"],
                ["A1-4", "11_mrp_vs_sell.png", "item_mrp ≈2200; item_price ≈1850; qty 4; total ≈7400", "MRP and sell not swapped"],
                ["A1-5", "12_supplier_bank_footer.png", "Lanka Hardware; LH-4412; bank Commercial / Pettah; phone/email if visible", "At least bank name or account name filled"],
                ["A1-6", "13_credit_period.png", "credit_period_days ≈45 (Net 45)", "Not stuck at default 30 if 45 is visible"],
                ["A1-7", "14_two_discount_lines.png", "Two lines with 5% and 10% disc; total ≈1850", "Discounts on rows; header total matches"],
                ["A1-8", "Any selfie / screenshot of a website", "Reject, empty, or obvious garbage + warning", "Does not invent a perfect fake invoice"],
                ["A1-9", "PDF scan of 01 (print to PDF then upload if UI allows)", "Same as A1-1", "PDF path works or clear error"],
            ],
            [W * 0.08, W * 0.22, W * 0.40, W * 0.30],
        )
    )

    story.append(Paragraph("2.5 WhatsApp path (same Agent 1)", styles["h2"]))
    story.append(
        T(
            ["ID", "Action", "Expect", "Pass if"],
            [
                ["A1-W1", "Send 01_clean to the shop WhatsApp (local tunnel or Render webhook)", "Row on Invoices → WhatsApp photos, not auto-verified", "Photo visible before Send to AI"],
                ["A1-W2", "Click Send to AI on that row", "Same review draft as upload OCR", "Fields comparable to A1-1"],
                ["A1-W3", "Send a non-invoice photo", "Inbox row; OCR weak or user types details", "No crash; 403 Gemini shows flash error"],
            ],
            [W * 0.10, W * 0.36, W * 0.28, W * 0.26],
        )
    )
    story.append(
        Paragraph(
            "<b>Gemini 403:</b> “Could not read photo (PERMISSION_DENIED…)”. Unlock GEMINI_API_KEY / AI Studio project. "
            "Bundling chat can still work (OpenAI). Type details manually to continue Agent 2+.",
            styles["fail"],
        )
    )

    story.append(Spacer(1, 6))
    preview_row = []
    for key in ("clean", "math", "mrp", "phone_photo"):
        p = sample_files.get(key)
        if p and p.exists():
            preview_row.append(RLImage(str(p), width=40 * mm, height=54 * mm, kind="proportional"))
    if preview_row:
        story.append(Table([preview_row], colWidths=[W / max(len(preview_row), 1)] * len(preview_row)))
    story.append(Paragraph("Previews: 01 clean · 02 math · 11 MRP · 15 glare. Full set 01–15 in docs/agent_test_samples/.", styles["small"]))

    # --- Agent 2 ---
    story.append(PageBreak())
    story.append(Paragraph("3. Agent 2 — Anomaly audit (chat panel)", styles["h1"]))
    story.append(
        Paragraph(
            "<b>How:</b> After Agent 1, stay on Review or open Verify. Top card = status + chat bubbles + finding codes. "
            "Soft warn: tick “confirm matches” and save anyway.",
            styles["body"],
        )
    )
    story.append(
        Paragraph(
            "Unit tests: <font face='Courier'>python -m unittest agents.tests.test_anomaly_audit -q</font>",
            styles["small"],
        )
    )

    story.append(Paragraph("3.1 Worked example — discount not in total (03)", styles["h2"]))
    story.append(
        Paragraph(
            "Qty 10 × Rs.100 with <b>10% discount</b> → discounted lines = 10 × 100 × 0.90 = <b>900</b>. "
            "Printed TOTAL is <b>1,000</b> (undiscounted). Agent 2 code <b>possible_missing_discount</b>. "
            "Chat should say discounts exist but the header looks like they were ignored.",
            styles["body"],
        )
    )

    story.append(Paragraph("3.2 Worked example — qty spike (04) after history", styles["h2"]))
    story.append(
        Paragraph(
            "First verify 3–8 City Mart invoices with TOFFEE-01 qty about <b>10</b> @ Rs.100. "
            "Then upload 04 (qty <b>20</b> @ 100, total 2000). Expect <b>qty_unusual</b> MEDIUM. "
            "Chat ≈ “usually ~10, this invoice has 20”.",
            styles["body"],
        )
    )

    story.append(Paragraph("3.3 Always-on cases (little history needed)", styles["h2"]))
    story.append(
        T(
            ["ID", "Setup", "Code / severity", "Pass if"],
            [
                ["A2-1", "Upload 02 (2×400=800, header 1000)", "math_mismatch · HIGH", "Chat: lines vs header total"],
                ["A2-2", "Upload 03 (10% disc, total 1000)", "possible_missing_discount", "Warns discount missing from total"],
                ["A2-3", "Upload 06 (date today+60d)", "future_date · HIGH", "Flags date > 30 days ahead"],
                ["A2-4", "On review set date to today−400 days", "stale_date · MEDIUM", "Warns older than ~1 year"],
                ["A2-5", "Upload 09 (total 0)", "missing_amount · HIGH", "Zero amount called out"],
                ["A2-6", "Unknown supplier, no dealer match", "unknown_dealer · LOW", "Asks to pick dealer"],
                ["A2-7", "Verify CM-TEST-1001; upload same no again for that dealer", "duplicate_invoice_no · HIGH", "Existing number mentioned"],
                ["A2-8", "14_two_discount_lines with header 1850 (correct)", "No math_mismatch", "Good math stays quiet"],
                ["A2-8b", "14 but you edit header total to 2000 before save", "math_mismatch", "Edit-in-form still audited"],
                ["A2-9", "New dealer; clean 10×100=1000", "INSUFFICIENT_DATA or GOOD_TO_GO", "Panel does not crash"],
            ],
            [W * 0.10, W * 0.34, W * 0.28, W * 0.28],
        )
    )

    story.append(Paragraph("3.4 History-dependent cases", styles["h2"]))
    story.append(
        Paragraph(
            "Seed City Mart + TOFFEE-01 qty≈10 price≈100, then:",
            styles["body"],
        )
    )
    story.append(
        T(
            ["ID", "Action", "Expect", "Pass if"],
            [
                ["A2-10", "Upload 04 qty 20 toffees", "qty_unusual · needs_confirmation", "Chat usual ~10 vs 20"],
                ["A2-11", "Upload 07 price 250 after avg 100", "item_price_spike", "Unusual unit price mentioned"],
                ["A2-12", "Upload 08 total 50k if dealer avg ≪ 50k (≥3 invoices)", "amount_outlier", "Total vs dealer average"],
                ["A2-13", "Second TOFFEE-01 within 30 days", "item_reordered_soon · LOW", "Prior invoice # / date"],
                ["A2-14", "Qty 20 + reorder same week", "qty_unusual AND item_reordered_soon", "Two bubbles / two codes"],
                ["A2-15", "ISSUE_DETECTED → confirm matches → verify", "Saves; is_invoice_verified=1", "No hard block per finding"],
                ["A2-16", "Open review when not GOOD_TO_GO", "Chat auto-expands", "Bubbles visible"],
            ],
            [W * 0.10, W * 0.34, W * 0.28, W * 0.28],
        )
    )

    story.append(Paragraph("3.5 Type-in matrix (no photo — paste on Review)", styles["h2"]))
    story.append(
        T(
            ["Scenario", "Type these values", "Expected code"],
            [
                ["Math", "1 line: qty 2, price 400, disc 0, header total 1000", "math_mismatch"],
                ["Discount", "qty 10, price 100, disc 10, header 1000", "possible_missing_discount"],
                ["Qty*", "item_code TOFFEE-01, qty 20, price 100, total 2000", "qty_unusual"],
                ["Price*", "TOFFEE-01 qty 10 price 250 total 2500", "item_price_spike"],
                ["Future", "date today+60, lines match total", "future_date"],
                ["Stale", "date today−400, lines match total", "stale_date"],
                ["Zero", "supplier filled, total 0", "missing_amount"],
                ["Clean", "qty 10 price 100 disc 0 total 1000", "GOOD_TO_GO / INSUFFICIENT_DATA"],
                ["Two-line OK", "5×200×5% + 2×500×10% = 1850 header 1850", "(no math flag)"],
            ],
            [W * 0.18, W * 0.52, W * 0.30],
        )
    )
    story.append(Paragraph("* Qty/price need City Mart TOFFEE-01 history first.", styles["small"]))

    # --- Agent 3 ---
    story.append(PageBreak())
    story.append(Paragraph("4. Agent 3 — Strategist (cheque plan)", styles["h1"]))
    story.append(
        Paragraph(
            "<b>How:</b> Verify invoices → Bundling → pick dealer → set ceiling → Compute. "
            "Gemini strategist; on failure Python compute_bundles. Setup sheet: 10_bundling_setup_sheet.png.",
            styles["body"],
        )
    )
    story.append(
        Paragraph(
            "Tests: <font face='Courier'>python -m unittest agents.tests.test_strategist agents.tests.test_strategist_dates -q</font>",
            styles["small"],
        )
    )

    story.append(Paragraph("4.1 Worked example — three invoices, one dealer", styles["h2"]))
    story.append(
        Paragraph(
            "Create and <b>verify</b> for City Mart (or one dealer):<br/>"
            "• CM-B1 Rs. <b>180,000</b> invoiced today−40d credit 30d<br/>"
            "• CM-B2 Rs. <b>220,000</b> invoiced today−20d credit 30d<br/>"
            "• CM-B3 Rs. <b>160,000</b> invoiced today−5d credit 30d<br/>"
            "Sum = <b>560,000</b>. Shop cash/OD enough to plan (e.g. balance ≥ 100,000).",
            styles["body"],
        )
    )
    story.append(
        Paragraph(
            "<b>Ceiling 500,000:</b> plan may be 2 cheques (e.g. 180+220 and 160, or other split) — all under 500k. "
            "<b>Ceiling 200,000:</b> 220k invoice must split or sit on its own cheque with a warning; expect <b>at least 3</b> cheques. "
            "PASS: every rupee of 560k appears on some cheque (within rounding).",
            styles["body"],
        )
    )

    story.append(Paragraph("4.2 Strategist test cases", styles["h2"]))
    story.append(
        T(
            ["ID", "Setup", "Expect", "Pass if"],
            [
                ["A3-1 Happy", "CM-B1/B2/B3; ceiling 500k; cash OK", "proposed_cheques + strategy_summary", "Groups cover all three invoices"],
                ["A3-2 Ceiling split", "Same invoices; ceiling 200,000", "Multiple cheques / split of 220k", "No silent 220k cheque above ceiling"],
                ["A3-3 Guardrail", "Drag/edit one group above ceiling then validate", "Exceeds ceiling warning", "Visible before commit"],
                ["A3-4 Interbank", "Dealer bank Commercial; pay from Sampath", "clearing_type INTERBANK", "Float/interbank mentioned"],
                ["A3-5 Intrabank", "Dealer bank = paying bank", "INTRABANK (not false interbank)", "No wrong interbank flag"],
                ["A3-6 Holiday", "Aim a cheque date on Sunday or CBSL holiday", "Shift to next business day / note", "Not left on holiday with no note"],
                ["A3-7 Empty", "Compute with nothing selected", "Friendly empty / no crash", "Page still usable"],
                ["A3-8 Fallback", "USE_FAKE_AI=true or bad Gemini", "Python/mock cheques still returned", "No HTTP 500"],
                ["A3-9 Conservation", "Sum cheque amounts vs 560,000", "Match within rounding", "No dropped invoice"],
                ["A3-10 Account", "≥2 shop accounts", "selected_shop_account_id on cheques", "Real Cash-flow account id"],
                ["A3-11 Overdue vs fresh", "B1 due earlier than B3", "Older/due-sooner invoices not ignored", "Dates respect credit periods roughly"],
                ["A3-12 Drag-drop", "After compute, move an invoice to another cheque in UI", "Totals update; still under ceiling or warn", "DnD does not zero amounts"],
            ],
            [W * 0.12, W * 0.32, W * 0.28, W * 0.28],
        )
    )

    # --- Agent 4 ---
    story.append(Paragraph("5. Agent 4 — Reviewer (teacher tone)", styles["h1"]))
    story.append(
        Paragraph(
            "Runs after Agent 3 compute. First model line is VERDICT: approve or VERDICT: suggest_changes, then informal explanation.",
            styles["body"],
        )
    )
    story.append(Paragraph("5.1 Example wording (English, healthy 200k-ceiling split)", styles["h2"]))
    story.append(
        Paragraph(
            "You might see something like: “VERDICT: approve — We split City Mart’s Rs. 560,000 across several cheques "
            "so none go over your Rs. 200,000 ceiling. The 220,000 bill cannot sit on one cheque. Dates avoid Sunday. "
            "Check the Sampath account has cash on those days.” PASS if a shop owner could act on it (counts, ceiling, dates).",
            styles["body"],
        )
    )
    story.append(
        T(
            ["ID", "Action", "Expect", "Pass if"],
            [
                ["A4-1 EN approve", "Healthy plan, UI English, compute", "Verdict + informal EN", "Dates/amounts understandable"],
                ["A4-2 Suggest", "Tight cash or ceiling violations", "suggest_changes + concrete fix", "Does not approve a broken plan"],
                ["A4-3 Sinhala", "UI lang si → re-run review", "Mostly Sinhala", "Not pure English"],
                ["A4-4 Tamil", "UI lang ta → re-run review", "Mostly Tamil", "Not pure English"],
                ["A4-5 Facts", "Note cheque count & totals from A3", "Review cites those numbers", "Not a generic essay"],
                ["A4-6 Preview", "Preview review without commit", "Text returns", "trigger=preview OK"],
                ["A4-7 Apply", "Apply suggestions if button exists", "Groups update or clear error", "No silent no-op"],
                ["A4-8 Gemini", "USE_FAKE_AI=false + valid key", "Non-empty Gemini text", "Panel not blank"],
            ],
            [W * 0.12, W * 0.32, W * 0.28, W * 0.28],
        )
    )

    # --- Bundling chat ---
    story.append(Paragraph("6. Bundling chat assistant (OpenAI — not Agent 1)", styles["h1"]))
    story.append(
        Paragraph(
            "On the Bundling page, the chat box can split cheques / change dates. It must <b>not</b> be confused with App Guide. "
            "Needs OPENAI_API_KEY.",
            styles["body"],
        )
    )
    story.append(
        T(
            ["ID", "You type (example)", "Expect", "Pass if"],
            [
                ["BA-1", "Split the 220,000 invoice into two cheques under 200k", "Plan/groups change or a clear tool result", "Does not only say “ask Agent 3”"],
                ["BA-2", "Move all cheques one week later", "Dates shift or explanation why not", "No crash"],
                ["BA-3", "What is my ceiling?", "Mentions current ceiling number", "Uses dealer context"],
                ["BA-4", "Empty OpenAI key", "Friendly error", "Page does not 500"],
            ],
            [W * 0.10, W * 0.38, W * 0.28, W * 0.24],
        )
    )

    story.append(Paragraph("7. App Guide widget (not bundling)", styles["h1"]))
    story.append(
        Paragraph(
            "Floating helper on Invoices / Cash flow / etc. Must refuse to bundle cheques (that is Bundling chat / Agent 3).",
            styles["body"],
        )
    )
    story.append(
        T(
            ["ID", "Where / prompt", "Expect", "Pass if"],
            [
                ["G-1", "Invoices: “How do I upload?”", "Steps for Upload / WhatsApp photos", "Correct page, not bundling JSON"],
                ["G-2", "“Make three cheques for City Mart”", "Redirects you to Bundling / Agent 3", "Does not emit proposed_cheques JSON"],
                ["G-3", "Cash flow: “What is a holiday?”", "CBSL / deposit timing in plain language", "No crash"],
                ["G-4", "Switch UI si/ta", "Guide replies follow language if supported", "Not stuck in English only"],
            ],
            [W * 0.10, W * 0.32, W * 0.32, W * 0.26],
        )
    )

    story.append(PageBreak())
    story.append(Paragraph("8. End-to-end smokes", styles["h1"]))
    story.append(Paragraph("8.1 Core path (~45 min)", styles["h2"]))
    story.append(
        ListFlowable(
            [
                ListItem(Paragraph("A1: Upload 01_clean → fields ~3250.", styles["body"])),
                ListItem(Paragraph("A1: Upload 11_mrp → MRP vs sell.", styles["body"])),
                ListItem(Paragraph("A2: Upload 02_math → math_mismatch; verify with confirm.", styles["body"])),
                ListItem(Paragraph("A2: Seed toffees → 04_qty → qty_unusual.", styles["body"])),
                ListItem(Paragraph("Verify CM-B1/B2/B3 (sheet 10).", styles["body"])),
                ListItem(Paragraph("A3: Ceiling 200k compute → multi-cheque, sum 560k.", styles["body"])),
                ListItem(Paragraph("A4: EN review; switch SI or TA.", styles["body"])),
                ListItem(Paragraph("Optional commit only on a disposable DB.", styles["body"])),
            ],
            bulletType="1",
            leftIndent=14,
        )
    )
    story.append(Paragraph("8.2 WhatsApp path (~15 min, if webhook live)", styles["h2"]))
    story.append(
        ListFlowable(
            [
                ListItem(Paragraph("Send 01_clean via WhatsApp → appears in WhatsApp photos.", styles["body"])),
                ListItem(Paragraph("Send to AI → review like A1-1.", styles["body"])),
                ListItem(Paragraph("If Render logs stay empty on send, Meta is not posting (messages field / unpublished app / wrong number) — not Agent 1.", styles["body"])),
            ],
            bulletType="1",
            leftIndent=14,
        )
    )

    story.append(Paragraph("9. Troubleshooting cheatsheet", styles["h1"]))
    story.append(
        T(
            ["Symptom", "Likely cause", "What to do"],
            [
                ["Could not read photo 403 PERMISSION_DENIED", "Gemini project/key denied", "New key in AI Studio; same key on Render; USE_FAKE_AI only for demos"],
                ["OCR blank but bundling chat works", "OpenAI OK, Gemini not", "Fix GEMINI_API_KEY only"],
                ["WhatsApp photos empty, Render logs empty", "Meta never POSTed", "Callback …/webhook/whatsapp; subscribe messages; tester number or Live app"],
                ["Webhook verify fails", "Wrong path or token", "URL must end /webhook/whatsapp; token = META_VERIFY_TOKEN"],
                ["Agent 2 never flags qty 20", "No TOFFEE-01 history", "Verify several qty-10 invoices first"],
                ["Agent 3 500", "Gemini down and fallback bug", "Note traceback; retry USE_FAKE_AI=true"],
                ["Agent 4 English on SI UI", "Lang not passed / model ignored lang", "Set language in header, recompute"],
            ],
            [W * 0.32, W * 0.28, W * 0.40],
        )
    )

    story.append(Paragraph("10. Sign-off checklist", styles["h1"]))
    story.append(
        T(
            ["#", "Check", "Tester", "Pass?"],
            [
                ["1", "A1 OCR 01_clean (~3250)", "", "☐"],
                ["2", "A1 OCR 05 messy / 15 glare", "", "☐"],
                ["3", "A1 MRP vs sell (11)", "", "☐"],
                ["4", "A1 bank footer (12) or credit 45d (13)", "", "☐"],
                ["5", "A2 math_mismatch (02)", "", "☐"],
                ["6", "A2 missing discount (03)", "", "☐"],
                ["7", "A2 future_date (06)", "", "☐"],
                ["8", "A2 qty_unusual (04) with history", "", "☐"],
                ["9", "A2 price_spike (07) with history", "", "☐"],
                ["10", "A2 reorder within 30d", "", "☐"],
                ["11", "A2 soft-warn still verifies", "", "☐"],
                ["12", "A3 happy compute 500k ceiling", "", "☐"],
                ["13", "A3 ceiling split 200k + sum 560k", "", "☐"],
                ["14", "A3 interbank when banks differ", "", "☐"],
                ["15", "A4 EN review + verdict", "", "☐"],
                ["16", "A4 suggest_changes on risky plan", "", "☐"],
                ["17", "A4 SI or TA", "", "☐"],
                ["18", "Bundling chat example BA-1", "", "☐"],
                ["19", "Guide refuses cheque bundling", "", "☐"],
                ["20", "WhatsApp inbox → Send to AI (if Meta live)", "", "☐"],
                ["21", "Unit tests anomaly + strategist", "", "☐"],
            ],
            [W * 0.08, W * 0.52, W * 0.20, W * 0.20],
        )
    )

    story.append(Spacer(1, 10))
    story.append(Paragraph("Notes / bugs found:", styles["body"]))
    story.append(Paragraph("________________________________________________________________", styles["body"]))
    story.append(Paragraph("________________________________________________________________", styles["body"]))
    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            "Regenerate: <font face='Courier'>python scripts/generate_agent_test_guide_pdf.py</font>",
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
