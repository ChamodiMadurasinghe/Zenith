from agents.base import generate_with_image

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
    return generate_with_image(
        "Extract all invoice fields from this image.",
        image_path,
        SYSTEM,
    )
