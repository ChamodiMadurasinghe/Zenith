"""Headless WhatsApp webhook for invoice/cheque intake (Meta Cloud API default)."""

from __future__ import annotations

import json
import uuid
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import requests
from flask import Blueprint, Request, request

from config import BASE_DIR, Config
from core.dates import format_date
from core.ingestion_helpers import dealer_setup_from_extraction
from core.liquidity_engine import calculate_max_liquidity_schedule
from core.meta_whatsapp import (
    download_media as download_meta_media,
    extract_inbound_messages,
    normalize_whatsapp_phone,
    validate_meta_signature,
    verify_webhook_challenge,
)
from core.whatsapp_conversation import begin_dealer_confirmation, handle_text_reply
from core.whatsapp_sender import send_whatsapp_message
from db import repositories as repo

whatsapp_bp = Blueprint("whatsapp", __name__)

USE_WHATSAPP_MOCK = Config.use_whatsapp_mock()

MOCK_PAYLOAD = {
    "From": "+94771234567",
    "MediaUrl0": "https://picsum.photos/800/1200",
    "MessageSid": "SM_mock_001",
}

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def _relative_location_path(filename: str) -> str:
    upload_rel = Config.UPLOAD_FOLDER.relative_to(BASE_DIR).as_posix()
    return f"{upload_rel}/{filename}"


def _extension_from_response(url: str, content_type: str | None) -> str:
    if content_type:
        mapping = {
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
        }
        ext = mapping.get(content_type.split(";")[0].strip().lower())
        if ext:
            return ext
    path_ext = Path(urlparse(url).path).suffix.lower()
    if path_ext in ALLOWED_EXTENSIONS:
        return path_ext
    return ".jpg"


def download_twilio_media(media_url: str) -> tuple[Path, str]:
    sid = Config.twilio_account_sid()
    token = Config.twilio_auth_token()
    if not sid or not token:
        raise RuntimeError("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be set to download media")
    response = requests.get(media_url, auth=(sid, token), timeout=60)
    response.raise_for_status()
    Config.UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    ext = _extension_from_response(media_url, response.headers.get("Content-Type"))
    filename = f"{uuid.uuid4()}{ext}"
    path = Config.UPLOAD_FOLDER / filename
    path.write_bytes(response.content)
    return path, _relative_location_path(filename)


def resolve_image_path(
    media_url: str | None = None,
    *,
    media_id: str | None = None,
) -> tuple[Path, str]:
    """Resolve inbound media. Positional media_url keeps agentic bridge compatible."""
    mock_path = Config.mock_image_path().strip()
    if USE_WHATSAPP_MOCK and mock_path:
        local = Path(mock_path)
        if not local.is_absolute():
            local = BASE_DIR / local
        if not local.exists():
            raise FileNotFoundError(f"MOCK_IMAGE_PATH not found: {local}")
        return local, _relative_location_path(local.name)

    if media_id:
        return download_meta_media(media_id)
    if media_url:
        if Config.whatsapp_provider() == "twilio" or "twilio.com" in media_url:
            return download_twilio_media(media_url)
        if media_url.startswith("http://") or media_url.startswith("https://"):
            response = requests.get(media_url, timeout=60)
            response.raise_for_status()
            Config.UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
            ext = _extension_from_response(media_url, response.headers.get("Content-Type"))
            filename = f"{uuid.uuid4()}{ext}"
            path = Config.UPLOAD_FOLDER / filename
            path.write_bytes(response.content)
            return path, _relative_location_path(filename)
        # Agentic Meta path may pass a Graph media id as the "url" argument
        return download_meta_media(media_url)
    raise ValueError("No media_id or media_url provided")


def _default_account_id() -> int | None:
    accounts = repo.get_bank_accounts()
    return accounts[0]["user_bank_acc_id"] if accounts else None


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


def build_liquidity_reply(
    extracted: dict, schedule_row: dict, *, dealer_matched: bool, anomalies: list[dict]
) -> str:
    days_gained = int(schedule_row.get("Days_Gained_By_Holiday_Lag") or 0)
    day_word = "day" if days_gained == 1 else "days"
    lines = [
        "Zenith Liquidity Agent Status Update",
        "Document processed successfully.",
        f"Issuer: {extracted['supplier_name']}",
        f"Face Value: LKR {extracted['total_amount']:,.2f}",
        f"Stated Date: {extracted['invoiced_date']}",
        "",
        "Working Capital Strategy:",
        (
            "Due to upcoming public bank holidays, this cash will NOT leave your account until "
            f"{schedule_row['True_Settlement_Date']}. "
            f"You safely gain {days_gained} extra {day_word} of free cash holding."
        ),
        "",
        "Saved as pending verification — open web app to confirm details.",
    ]
    if anomalies:
        lines.append("")
        lines.append("Anomaly warnings:")
        for a in anomalies:
            lines.append(f"- {a.get('message')}")
    if extracted.get("date_was_missing"):
        lines.append("")
        lines.append("Note: date was not visible; today's date was used for planning.")
    if not dealer_matched:
        lines.append("")
        lines.append(
            "Supplier details were captured. Reply YES/NO when asked to register the dealer."
        )
    return "\n".join(lines)


def process_whatsapp_document(
    sender_phone: str,
    *,
    media_id: str | None = None,
    media_url: str | None = None,
) -> str:
    local_path, location_path = resolve_image_path(media_id=media_id, media_url=media_url)
    try:
        from agents.ingestion import extract_invoice

        raw = extract_invoice(str(local_path))
    except Exception:
        return "Could not read document — try a clearer photo and ensure GEMINI_API_KEY is set."

    extracted = _normalize_extracted(raw)
    dealer_setup = dealer_setup_from_extraction(raw)
    dealer = (
        repo.find_dealer_by_name(extracted["supplier_name"])
        if extracted["supplier_name"] != "Unknown"
        else None
    )
    dealer_id = dealer["dealer_id"] if dealer else repo.get_pending_supplier_dealer_id()

    try:
        from agents.anomaly import check_invoice_anomalies

        anomalies = check_invoice_anomalies(extracted, dealer["dealer_id"] if dealer else None)
    except Exception:
        anomalies = []

    account_id = _default_account_id()
    bank_context = repo.build_bank_context(account_id) if account_id else {}
    holidays = repo.get_holidays()
    pending_rows = [
        {
            "stated_date": extracted["invoiced_date"],
            "total_amount": extracted["total_amount"],
            "dealer_id": dealer["dealer_id"] if dealer else None,
            "status": "pending",
        }
    ]
    schedule = calculate_max_liquidity_schedule(pending_rows, holidays, bank_context)
    if not schedule:
        return "Could not compute liquidity schedule for this document."

    items = extracted["line_items"] or [
        {
            "item_code": "",
            "item_name": "WhatsApp intake",
            "item_qty": 1,
            "item_price": extracted["total_amount"],
            "item_discount": 0,
        }
    ]
    pending_payload = {**dealer_setup, "anomalies": anomalies}
    invoice_id = repo.save_pending_invoice(
        {
            "invoice_no": extracted["invoice_no"],
            "invoiced_date": extracted["invoiced_date"],
            "credit_period_days": extracted["credit_period_days"],
            "total_amount": extracted["total_amount"],
            "location_path": location_path,
        },
        items,
        dealer_id,
        pending_dealer_json=json.dumps(pending_payload),
    )
    reply = build_liquidity_reply(
        extracted, schedule[0], dealer_matched=bool(dealer), anomalies=anomalies
    )
    if not dealer and dealer_setup.get("dealer_name"):
        onboarding = begin_dealer_confirmation(sender_phone, dealer_setup, invoice_id=invoice_id)
        reply = f"{reply}\n\n{onboarding}"
    return reply


def _sender_allowed(sender: str) -> bool:
    allowed = Config.whatsapp_allowed_numbers()
    if not allowed:
        return True
    normalized = normalize_whatsapp_phone(sender)
    allowed_norm = {normalize_whatsapp_phone(n) for n in allowed}
    return normalized in allowed_norm


def _reply(to_phone: str, body: str):
    try:
        send_whatsapp_message(to_phone, body)
    except Exception as exc:
        # Still ack webhook; log-style print for local debugging
        print(f"WhatsApp reply failed for {to_phone}: {exc}")


def validate_twilio_request(req: Request) -> bool:
    if USE_WHATSAPP_MOCK:
        return True
    auth_token = Config.twilio_auth_token()
    if not auth_token:
        return False
    signature = req.headers.get("X-Twilio-Signature", "")
    if not signature:
        return False
    from twilio.request_validator import RequestValidator

    validator = RequestValidator(auth_token)
    return validator.validate(req.url, req.form, signature)


@whatsapp_bp.route("/webhook/whatsapp", methods=["GET"])
def whatsapp_webhook_verify():
    """Meta Cloud API subscription verification handshake."""
    mode = request.args.get("hub.mode", "")
    token = request.args.get("hub.verify_token", "")
    challenge = request.args.get("hub.challenge", "")
    result = verify_webhook_challenge(mode, token, challenge)
    if result is None:
        return "Verification failed", 403
    return result, 200, {"Content-Type": "text/plain"}


@whatsapp_bp.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    provider = Config.whatsapp_provider()

    # --- Meta Cloud API ---
    if provider == "meta":
        raw = request.get_data()
        if not validate_meta_signature(raw, request.headers.get("X-Hub-Signature-256")):
            return "Invalid signature", 403
        payload = request.get_json(silent=True) or {}
        print(
            f"[whatsapp] META POST keys={list(payload.keys())} raw_len={len(raw)}",
            flush=True,
        )
        try:
            log_path = Config.UPLOAD_FOLDER.parent / "webhook_meta.jsonl"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(raw.decode("utf-8", errors="replace") + "\n")
        except Exception as log_exc:
            print(f"[whatsapp] log write failed: {log_exc}", flush=True)
        inbound = extract_inbound_messages(payload)
        print(f"[whatsapp] parsed {len(inbound)} inbound message(s)", flush=True)
        if not inbound:
            # statuses / other change types still POST with empty messages
            print(f"[whatsapp] non-message payload preview={str(payload)[:400]}", flush=True)
        use_agentic = Config.use_agentic_orchestrator()
        for msg in inbound:
            sender = msg["from"]
            if not _sender_allowed(sender):
                continue
            try:
                if use_agentic:
                    from agentic.adapters.whatsapp_bridge import (
                        process_whatsapp_text_via_agentic,
                        process_whatsapp_via_agentic,
                    )

                    if msg.get("media_id"):
                        reply_text = process_whatsapp_via_agentic(
                            msg["media_id"],
                            sender,
                            resolve_image_path=resolve_image_path,
                        )
                    else:
                        reply_text = process_whatsapp_text_via_agentic(
                            sender, msg.get("text") or ""
                        )
                elif msg.get("media_id"):
                    reply_text = process_whatsapp_document(sender, media_id=msg["media_id"])
                elif msg.get("text"):
                    reply_text = (
                        handle_text_reply(sender, msg["text"])
                        or "Please send a photo of an invoice or cheque."
                    )
                else:
                    reply_text = "Please send a photo of an invoice or cheque."
            except Exception as exc:
                reply_text = f"Processing failed: {exc}"
            _reply(sender, reply_text)
        return "", 200

    # --- Legacy Twilio form webhook ---
    if not validate_twilio_request(request):
        return "Unauthorized", 403
    sender = normalize_whatsapp_phone(request.form.get("From", ""))
    if not _sender_allowed(sender):
        return "", 403
    media_url = request.form.get("MediaUrl0")
    body = (request.form.get("Body") or "").strip()
    use_agentic = Config.use_agentic_orchestrator()
    try:
        if use_agentic:
            from agentic.adapters.whatsapp_bridge import (
                process_whatsapp_text_via_agentic,
                process_whatsapp_via_agentic,
            )

            if media_url:
                reply_text = process_whatsapp_via_agentic(
                    media_url, sender, resolve_image_path=resolve_image_path
                )
            else:
                reply_text = process_whatsapp_text_via_agentic(sender, body)
        elif media_url:
            reply_text = process_whatsapp_document(sender, media_url=media_url)
        else:
            reply_text = handle_text_reply(sender, body) or (
                "Please send a photo of an invoice or cheque."
            )
    except Exception as exc:
        reply_text = f"Processing failed: {exc}"
    _reply(sender, reply_text)
    # Twilio also accepts empty 200 when using the REST API to reply
    return "", 200


def run_mock():
    media_url = MOCK_PAYLOAD["MediaUrl0"]
    mock_path = Config.mock_image_path().strip()
    if mock_path:
        media_url = None
    sender = normalize_whatsapp_phone(MOCK_PAYLOAD["From"])
    print(f"WHATSAPP_PROVIDER={Config.whatsapp_provider()}")
    print(f"USE_WHATSAPP_MOCK={USE_WHATSAPP_MOCK}")
    print(f"USE_AGENTIC_ORCHESTRATOR={Config.use_agentic_orchestrator()}")
    print(f"Sender: {sender}")
    if mock_path:
        print(f"Using MOCK_IMAGE_PATH: {mock_path}")
    else:
        print(f"MediaUrl0: {MOCK_PAYLOAD['MediaUrl0']}")
    try:
        if Config.use_agentic_orchestrator():
            from agentic.adapters.whatsapp_bridge import process_whatsapp_via_agentic

            reply_text = process_whatsapp_via_agentic(
                media_url, sender, resolve_image_path=resolve_image_path
            )
        else:
            reply_text = process_whatsapp_document(sender, media_url=media_url)
    except Exception as exc:
        reply_text = f"Processing failed: {exc}"
    print("\n--- Reply ---\n")
    print(reply_text)
    _reply(sender, reply_text)
    if Config.use_agentic_orchestrator():
        from agentic import get_session_trace

        trace = get_session_trace(sender)
        print(f"\nAgent trace steps: {len(trace.get('steps', []))}")
        print(f"FSM state: {trace.get('fsm_state')}")


if __name__ == "__main__":
    run_mock()
