"""ReportLab PDF generation for Sri Lankan bank cheques."""

from __future__ import annotations

import io
import re
from datetime import datetime

from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

from core.cheque_utils import format_cheque_amount_in_words

_DATE_DIGIT_RE = re.compile(r"\D")


def normalize_cheque_date(date_str: str) -> str:
    """Return 8-digit DDMMYYYY for boxed cheque date fields."""
    raw = (date_str or "").strip()
    if not raw:
        return "00000000"

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%d%m%Y")
        except ValueError:
            continue

    digits = _DATE_DIGIT_RE.sub("", raw)
    if len(digits) == 8:
        return digits
    return digits[:8].ljust(8, "0")


def _mm_pos(x_mm: float, y_mm: float, offset_x_mm: float, offset_y_mm: float) -> tuple[float, float]:
    return (x_mm + offset_x_mm) * mm, (y_mm + offset_y_mm) * mm


def _draw_spaced_digits(
    c: canvas.Canvas,
    x_pt: float,
    y_pt: float,
    digits: str,
    letter_spacing_mm: float,
    font_name: str = "Courier-Bold",
    font_size: int = 12,
) -> None:
    c.setFont(font_name, font_size)
    x = x_pt
    spacing = letter_spacing_mm * mm
    for digit in digits:
        c.drawString(x, y_pt, digit)
        x += c.stringWidth(digit, font_name, font_size) + spacing


def _draw_wrapped_text(
    c: canvas.Canvas,
    x_pt: float,
    y_pt: float,
    text: str,
    max_width_mm: float,
    font_name: str = "Helvetica",
    font_size: int = 9,
    line_height_mm: float = 3.5,
) -> None:
    c.setFont(font_name, font_size)
    max_width_pt = max_width_mm * mm
    line_height_pt = line_height_mm * mm
    lines = simpleSplit(text, font_name, font_size, max_width_pt)
    for i, line in enumerate(lines):
        c.drawString(x_pt, y_pt - (i * line_height_pt), line)


def generate_cheque_pdf(
    date_str: str,
    payee_name: str,
    amount: float,
    bank_template: dict,
    printer_settings: dict,
    *,
    crossing: bool = True,
) -> bytes:
    offset_x = float(printer_settings.get("offset_x_mm", 0.0))
    offset_y = float(printer_settings.get("offset_y_mm", 0.0))
    orientation = str(printer_settings.get("feed_orientation", "VERTICAL")).upper()

    w_mm = float(bank_template["cheque_width_mm"])
    h_mm = float(bank_template["cheque_height_mm"])

    buffer = io.BytesIO()
    if orientation == "VERTICAL":
        c = canvas.Canvas(buffer, pagesize=(h_mm * mm, w_mm * mm))
        c.translate(h_mm * mm, 0)
        c.rotate(90)
    else:
        c = canvas.Canvas(buffer, pagesize=(w_mm * mm, h_mm * mm))

    def pos(x_key: str, y_key: str) -> tuple[float, float]:
        return _mm_pos(float(bank_template[x_key]), float(bank_template[y_key]), offset_x, offset_y)

    if crossing:
        cx, cy = pos("crossing_x", "crossing_y")
        c.setFont("Helvetica-Bold", 10)
        c.drawString(cx, cy, "--- A/C PAYEE ONLY ---")

    dx, dy = pos("date_x", "date_y")
    _draw_spaced_digits(
        c,
        dx,
        dy,
        normalize_cheque_date(date_str),
        float(bank_template.get("date_letter_spacing", 3.5)),
    )

    px, py = pos("payee_x", "payee_y")
    c.setFont("Helvetica-Bold", 11)
    c.drawString(px, py, payee_name or "")

    wx, wy = pos("amount_words_x", "amount_words_y")
    _draw_wrapped_text(
        c,
        wx,
        wy,
        format_cheque_amount_in_words(amount),
        float(bank_template.get("amount_words_max_width", 110.0)),
    )

    fx, fy = pos("amount_figures_x", "amount_figures_y")
    c.setFont("Helvetica-Bold", 11)
    c.drawString(fx, fy, f"**{amount:,.2f}/=")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.getvalue()
