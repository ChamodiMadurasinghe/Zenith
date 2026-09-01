"""4-stage WhatsApp image ingestion pipeline for the local bridge."""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from config import BASE_DIR, Config
from core.dates import format_date
from core.ingestion_helpers import dealer_setup_from_extraction
from core.whatsapp_utils import normalize_whatsapp_phone
from db import repositories as repo

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass
class PipelineResult:
    status: str
    http_status: int
    invoice_id: int | None = None
    log_id: int | None = None
    duplicate: bool = False
    message: str = ""

    def to_dict(self) -> dict:
        payload = {"ok": True, "status": self.status}
        if self.duplicate:
            payload["duplicate"] = True
        if self.invoice_id is not None:
            payload["invoice_id"] = self.invoice_id
        if self.log_id is not None:
            payload["log_id"] = self.log_id
        if self.message:
            payload["message"] = self.message
        return payload


def _relative_location_path(filename: str) -> str:
    try:
        upload_rel = Config.UPLOAD_FOLDER.relative_to(BASE_DIR).as_posix()
    except ValueError:
        upload_rel = Path(Config.UPLOAD_FOLDER).as_posix()
    return f"{upload_rel}/{filename}"


def _copy_to_upload_folder(source: Path) -> tuple[Path, str]:
    ext = source.suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        ext = ".jpg"
    Config.UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4()}{ext}"
    dest = Config.UPLOAD_FOLDER / filename
    shutil.copy2(source, dest)
    return dest, _relative_location_path(filename)


def _normalize_extracted(extracted: dict) -> dict:
    supplier = (extracted.get("supplier_name") or "").strip()
    invoice_no = (extracted.get("invoice_no") or "").strip()
    invoiced_date = extracted.get("invoiced_date")
    if not invoiced_date:
        invoiced_date = format_date(date.today())
    try:
        total_amount = float(extracted.get("total_amount") or 0)
    except (TypeError, ValueError):
        total_amount = 0.0
    try:
        credit_period_days = int(
            extracted.get("credit_period_days") or Config.DEFAULT_CREDIT_PERIOD_DAYS
        )
    except (TypeError, ValueError):
        credit_period_days = Config.DEFAULT_CREDIT_PERIOD_DAYS
    line_items = extracted.get("line_items") or []
    return {
        "supplier_name": supplier or "Unknown",
        "invoice_no": invoice_no or "PENDING",
        "invoiced_date": invoiced_date,
        "total_amount": total_amount,
        "credit_period_days": credit_period_days,
        "line_items": line_items,
        "date_was_missing": not extracted.get("invoiced_date"),
    }


def _save_pipeline_pending_invoice(
    extracted: dict,
    *,
    location_path: str,
    sender_phone: str | None,
    delivery_date: str | None,
) -> int:
    from agents.anomaly import check_invoice_anomalies

    dealer = (
        repo.find_dealer_by_name(extracted["supplier_name"])
        if extracted["supplier_name"] != "Unknown"
        else None
    )
    dealer_id = dealer["dealer_id"] if dealer else repo.get_pending_supplier_dealer_id()

    try:
        anomalies = check_invoice_anomalies(extracted, dealer["dealer_id"] if dealer else None)
    except Exception:
        anomalies = []

    items = extracted["line_items"] or [
        {
            "item_code": "",
            "item_name": "WhatsApp intake",
            "item_qty": 1,
            "item_price": extracted["total_amount"] or 1,
            "item_discount": 0,
        }
    ]
    pending_payload = {
        **dealer_setup_from_extraction(extracted),
        "anomalies": anomalies,
        "whatsapp_sender": sender_phone,
        "source": "whatsapp_web",
    }
    delivery = (delivery_date or "").strip() or format_date(date.today())
    return repo.save_pending_invoice(
        {
            "invoice_no": extracted["invoice_no"],
            "invoiced_date": extracted["invoiced_date"],
            "delivery_date": delivery,
            "credit_period_days": extracted["credit_period_days"],
            "total_amount": extracted["total_amount"],
            "location_path": location_path,
        },
        items,
        dealer_id,
        pending_dealer_json=json.dumps(pending_payload),
    )


def run_whatsapp_image_pipeline(
    *,
    wa_msg_id: str,
    sender_phone: str,
    image_path: str,
    received_at: str | None = None,
) -> PipelineResult:
    sender = normalize_whatsapp_phone(sender_phone)
    source = Path(image_path).resolve()
    queue_root = Config.inbound_queue_dir().resolve()
    upload_root = Config.UPLOAD_FOLDER.resolve()
    if queue_root not in source.parents and source != queue_root and upload_root not in source.parents:
        raise ValueError("image_path must be under inbound queue or upload folder")

    state, existing = repo.begin_inbound_processing(
        wa_msg_id,
        sender_phone=sender,
        received_at=received_at,
        location_path=None,
    )
    if state == "duplicate":
        row = existing or {}
        return PipelineResult(
            status=row.get("pipeline_status") or "duplicate",
            http_status=200,
            invoice_id=row.get("invoice_id"),
            duplicate=True,
        )

    if not repo.is_sender_allowed(sender):
        repo.finalize_inbound(wa_msg_id, status="ignored_sender")
        return PipelineResult(
            status="ignored_sender",
            http_status=200,
            message="Sender not on whitelist",
        )

    try:
        local_path, location_path = _copy_to_upload_folder(source)
        repo.finalize_inbound(wa_msg_id, status="processing", location_path=location_path)

        from agents.document_classifier import classify_document, is_business_document

        classification = classify_document(str(local_path))
        if not is_business_document(classification):
            log_id = repo.save_unprocessed_media_log(
                wa_msg_id=wa_msg_id,
                sender_phone=sender,
                location_path=location_path,
                received_at=received_at,
                reject_reason=classification.get("reason") or "not_invoice",
                classifier_json=json.dumps(classification),
            )
            repo.finalize_inbound(wa_msg_id, status="rejected_non_invoice")
            return PipelineResult(
                status="rejected_non_invoice",
                http_status=200,
                log_id=log_id,
            )

        from agents.ingestion import extract_invoice

        raw = extract_invoice(str(local_path))
        extracted = _normalize_extracted(raw)
        delivery_date = (received_at or "")[:10] if received_at and len(received_at) >= 10 else None
        invoice_id = _save_pipeline_pending_invoice(
            extracted,
            location_path=location_path,
            sender_phone=sender,
            delivery_date=delivery_date,
        )
        repo.finalize_inbound(
            wa_msg_id,
            status="processed",
            invoice_id=invoice_id,
            location_path=location_path,
        )
        return PipelineResult(
            status="processed",
            http_status=200,
            invoice_id=invoice_id,
        )
    except Exception as exc:
        repo.finalize_inbound(wa_msg_id, status="failed", error_message=str(exc))
        return PipelineResult(
            status="failed",
            http_status=500,
            message=str(exc),
        )
