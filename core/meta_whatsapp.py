"""Meta WhatsApp Cloud API client (Graph API)."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from pathlib import Path
from urllib.parse import urlparse

import requests

from config import Config

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def _graph_base() -> str:
    return f"https://graph.facebook.com/{Config.meta_graph_version()}"


def _headers() -> dict:
    token = Config.meta_whatsapp_token()
    if not token:
        raise RuntimeError("META_WHATSAPP_TOKEN must be set")
    return {"Authorization": f"Bearer {token}"}


def normalize_whatsapp_phone(phone: str) -> str:
    """Canonical +E.164 style used for sessions and allow-lists."""
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if not digits:
        return (phone or "").strip()
    return f"+{digits}"


def phone_for_meta_api(phone: str) -> str:
    """Meta 'to' field wants digits only (country code, no +)."""
    return "".join(ch for ch in (phone or "") if ch.isdigit())


def verify_webhook_challenge(mode: str, token: str, challenge: str) -> str | None:
    if mode == "subscribe" and token and token == Config.meta_verify_token():
        return challenge
    return None


def validate_meta_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """If META_APP_SECRET is set, require a valid X-Hub-Signature-256."""
    secret = Config.meta_app_secret()
    if Config.use_whatsapp_mock():
        return True
    if not secret:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = signature_header.split("=", 1)[1]
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, expected)


def _extension_from_content_type(content_type: str | None, url: str = "") -> str:
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


def download_media(media_id: str) -> tuple[Path, str]:
    """Download inbound WhatsApp media by Graph media id."""
    meta = requests.get(
        f"{_graph_base()}/{media_id}",
        headers=_headers(),
        timeout=60,
    )
    meta.raise_for_status()
    payload = meta.json()
    url = payload.get("url")
    if not url:
        raise RuntimeError(f"No download URL for media id {media_id}")

    binary = requests.get(url, headers=_headers(), timeout=60)
    binary.raise_for_status()

    Config.UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    ext = _extension_from_content_type(
        binary.headers.get("Content-Type") or payload.get("mime_type"),
        url,
    )
    filename = f"{uuid.uuid4()}{ext}"
    path = Config.UPLOAD_FOLDER / filename
    path.write_bytes(binary.content)

    return path, Config.location_path_for(filename)


def send_text_message(to_phone: str, body: str) -> dict:
    phone_number_id = Config.meta_phone_number_id()
    if not phone_number_id:
        raise RuntimeError("META_PHONE_NUMBER_ID must be set")
    to = phone_for_meta_api(to_phone)
    if not to:
        raise ValueError("Recipient phone is empty")
    resp = requests.post(
        f"{_graph_base()}/{phone_number_id}/messages",
        headers={**_headers(), "Content-Type": "application/json"},
        json={
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": body},
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def extract_inbound_messages(payload: dict) -> list[dict]:
    """Normalize Meta webhook payload into simple message dicts."""
    messages: list[dict] = []
    if payload.get("object") != "whatsapp_business_account":
        return messages
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for msg in value.get("messages") or []:
                sender = normalize_whatsapp_phone(msg.get("from", ""))
                msg_type = msg.get("type")
                text = ""
                media_id = None
                if msg_type == "text":
                    text = ((msg.get("text") or {}).get("body") or "").strip()
                elif msg_type == "image":
                    media_id = (msg.get("image") or {}).get("id")
                elif msg_type == "document":
                    # Allow invoice PDFs/photos sent as documents
                    doc = msg.get("document") or {}
                    mime = (doc.get("mime_type") or "").lower()
                    if mime.startswith("image/") or mime == "application/pdf":
                        media_id = doc.get("id")
                messages.append(
                    {
                        "from": sender,
                        "type": msg_type,
                        "text": text,
                        "media_id": media_id,
                        "message_id": msg.get("id"),
                    }
                )
    return messages
