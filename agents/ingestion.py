from agents.base import generate_with_image
from config import Config

SYSTEM = """You are a document extraction agent for a Sri Lankan business.
The image may be a supplier invoice OR a handwritten/printed cheque.
Extract only information visible on the image. Do not invent line items.

For invoices: use supplier name, invoice number, invoice date, and total amount as shown.
Also extract supplier contact and bank details printed on the invoice header or footer when visible.
For cheques: map payee name to supplier_name, cheque amount to total_amount, cheque date to
invoiced_date, and use an empty string for invoice_no if none is visible.

Return JSON with keys: invoice_no, supplier_name, supplier_email, supplier_phone, supplier_address,
supplier_bank_name, supplier_account_name, supplier_branch, invoiced_date (YYYY-MM-DD if visible else null),
total_amount (number), credit_period_days (integer, default 30), line_items (array of
{item_code, item_name, item_qty, item_price, item_discount})."""


def extract_invoice(image_path: str) -> dict:
    if Config.use_fake_ai():
        return {
            "invoice_no": "WA-MOCK-001",
            "supplier_name": "Mock Supplier Ltd",
            "supplier_email": "",
            "supplier_phone": "",
            "supplier_address": "",
            "supplier_bank_name": "",
            "supplier_account_name": "",
            "supplier_branch": "",
            "invoiced_date": "2026-08-30",
            "total_amount": 125000.0,
            "credit_period_days": 30,
            "line_items": [
                {
                    "item_code": "",
                    "item_name": "Mock goods",
                    "item_qty": 1,
                    "item_price": 125000.0,
                    "item_discount": 0,
                }
            ],
        }
    return generate_with_image(
        "Extract all invoice fields from this image.",
        image_path,
        SYSTEM,
    )
