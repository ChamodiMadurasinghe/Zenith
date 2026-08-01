"""Import orphan WhatsApp photos in storage/invoices into pending invoices."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import Config
from core.dates import format_date
from db import repositories as repo
from db.connection import query


def _already_imported(location_path: str) -> bool:
    row = query(
        "SELECT invoices_id FROM invoices WHERE location_path = ? LIMIT 1",
        (location_path,),
    )
    return bool(row)


def import_orphans(limit: int = 20) -> list[int]:
    upload = Config.UPLOAD_FOLDER
    files = sorted(
        [
            p
            for p in upload.glob("*")
            if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
            and not p.name.startswith("sample_")
            and not p.name.startswith("inv_")
        ],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit]

    created: list[int] = []
    dealer_id = repo.get_pending_supplier_dealer_id()
    today = format_date(date.today())

    for path in files:
        rel = f"{upload.relative_to(ROOT).as_posix()}/{path.name}"
        if _already_imported(rel):
            print(f"skip existing {rel}")
            continue
        # Try Gemini; fall back to manual-review stub
        extracted = None
        try:
            from agents.ingestion import extract_invoice

            extracted = extract_invoice(str(path))
        except Exception as exc:
            print(f"extract failed for {path.name}: {exc}")

        if extracted:
            invoice_no = (extracted.get("invoice_no") or "").strip() or f"WA-{path.stem[:8]}"
            try:
                total = float(extracted.get("total_amount") or 0)
            except (TypeError, ValueError):
                total = 0.0
            invoiced_date = extracted.get("invoiced_date") or today
            try:
                credit = int(extracted.get("credit_period_days") or Config.DEFAULT_CREDIT_PERIOD_DAYS)
            except (TypeError, ValueError):
                credit = Config.DEFAULT_CREDIT_PERIOD_DAYS
            items = extracted.get("line_items") or [
                {
                    "item_code": "",
                    "item_name": "WhatsApp intake",
                    "item_qty": 1,
                    "item_price": total or 1,
                    "item_discount": 0,
                }
            ]
            pending = {
                "dealer_name": (extracted.get("supplier_name") or "").strip(),
                "source": "whatsapp_import",
            }
        else:
            invoice_no = f"WA-{path.stem[:8].upper()}"
            total = 0.0
            invoiced_date = today
            credit = Config.DEFAULT_CREDIT_PERIOD_DAYS
            items = [
                {
                    "item_code": "",
                    "item_name": "WhatsApp photo (manual review)",
                    "item_qty": 1,
                    "item_price": 1,
                    "item_discount": 0,
                }
            ]
            pending = {
                "dealer_name": "",
                "source": "whatsapp_import",
                "needs_manual_review": True,
                "extraction_error": "AI extraction unavailable; enter details in web app.",
            }

        inv_id = repo.save_pending_invoice(
            {
                "invoice_no": invoice_no,
                "invoiced_date": invoiced_date,
                "credit_period_days": credit,
                "total_amount": total,
                "location_path": rel,
            },
            items,
            dealer_id,
            pending_dealer_json=json.dumps(pending),
        )
        created.append(inv_id)
        print(f"imported {path.name} -> invoice #{inv_id}")
    return created


if __name__ == "__main__":
    ids = import_orphans()
    print(f"done: {len(ids)} pending invoice(s)")
