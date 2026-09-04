"""WhatsApp local bridge settings, ingest API, and unprocessed media log."""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for

from config import Config
from core.auth import login_required
from core.ingestion_pipeline import run_whatsapp_image_pipeline
from core.i18n import flash_t, friendly_error_message
from core.whatsapp_utils import normalize_whatsapp_phone
from db import repositories as repo

whatsapp_settings_bp = Blueprint("whatsapp_settings", __name__)


def _validate_bridge_token() -> bool:
    secret = Config.whatsapp_bridge_secret()
    if not secret:
        return False
    token = request.headers.get("X-Zenith-Bridge-Token", "")
    return token == secret


def _image_url(location_path: str | None) -> str | None:
    if not location_path:
        return None
    filename = Path(location_path).name
    return url_for("ingestion.serve_upload", filename=filename)


@whatsapp_settings_bp.route("/api/invoices/ingest", methods=["POST"])
def ingest_invoice():
    if not _validate_bridge_token():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    wa_msg_id = (payload.get("whatsapp_message_id") or "").strip()
    sender_phone = (payload.get("sender_phone") or "").strip()
    image_path = (payload.get("image_path") or "").strip()
    received_at = (payload.get("timestamp") or payload.get("received_at") or "").strip() or None

    if not wa_msg_id or not sender_phone or not image_path:
        return jsonify({"ok": False, "error": "Missing required fields"}), 400

    source = Path(image_path).resolve()
    queue_root = Config.inbound_queue_dir().resolve()
    try:
        source.relative_to(queue_root)
    except ValueError:
        return jsonify({"ok": False, "error": "image_path outside inbound queue"}), 400
    if not source.is_file():
        return jsonify({"ok": False, "error": "image file not found"}), 400

    try:
        result = run_whatsapp_image_pipeline(
            wa_msg_id=wa_msg_id,
            sender_phone=sender_phone,
            image_path=str(source),
            received_at=received_at,
        )
        return jsonify(result.to_dict()), result.http_status
    except ValueError as exc:
        return jsonify({"ok": False, "error": friendly_error_message(exc, default_key="err_whatsapp_ingest")}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": friendly_error_message(exc, default_key="err_whatsapp_ingest")}), 500


@whatsapp_settings_bp.route("/settings/whatsapp")
@login_required
def settings_index():
    senders = repo.list_allowed_senders()
    unprocessed = repo.get_unprocessed_media_pending()
    for row in unprocessed:
        row["image_url"] = _image_url(row.get("location_path"))
    return render_template(
        "whatsapp_settings.html",
        senders=senders,
        unprocessed=unprocessed,
        merchant_phone=repo.get_merchant_whatsapp_phone(),
    )


@whatsapp_settings_bp.route("/settings/whatsapp/merchant-phone", methods=["POST"])
@login_required
def save_merchant_phone():
    phone = (request.form.get("merchant_phone") or "").strip()
    if not phone:
        repo.clear_merchant_whatsapp_phone()
        flash_t("flash_merchant_phone_cleared", "success")
        return redirect(url_for("whatsapp_settings.settings_index"))
    try:
        repo.save_merchant_whatsapp_phone(phone)
        flash_t("flash_merchant_phone_saved", "success")
    except ValueError:
        flash_t("flash_whatsapp_phone_required", "error")
    return redirect(url_for("whatsapp_settings.settings_index"))


@whatsapp_settings_bp.route("/settings/whatsapp/senders", methods=["POST"])
@login_required
def add_sender():
    phone = (request.form.get("phone_e164") or "").strip()
    display_name = (request.form.get("display_name") or "").strip() or None
    if not phone:
        flash_t("flash_whatsapp_phone_required", "error")
        return redirect(url_for("whatsapp_settings.settings_index"))
    try:
        normalized = normalize_whatsapp_phone(phone)
        repo.add_allowed_sender(normalized, display_name)
        flash_t("flash_whatsapp_sender_added", "success")
    except Exception:
        flash_t("flash_whatsapp_sender_duplicate", "error")
    return redirect(url_for("whatsapp_settings.settings_index"))


@whatsapp_settings_bp.route("/settings/whatsapp/senders/<int:sender_id>", methods=["POST"])
@login_required
def update_sender(sender_id: int):
    row = repo.get_allowed_sender(sender_id)
    if not row:
        abort(404)
    display_name = (request.form.get("display_name") or "").strip() or None
    is_active = request.form.get("is_active") == "1"
    repo.update_allowed_sender(sender_id, display_name=display_name, is_active=is_active)
    flash_t("flash_whatsapp_sender_updated", "success")
    return redirect(url_for("whatsapp_settings.settings_index"))


@whatsapp_settings_bp.route("/settings/whatsapp/senders/<int:sender_id>/delete", methods=["POST"])
@login_required
def delete_sender(sender_id: int):
    repo.remove_allowed_sender(sender_id)
    flash_t("flash_whatsapp_sender_removed", "success")
    return redirect(url_for("whatsapp_settings.settings_index"))


@whatsapp_settings_bp.route("/settings/whatsapp/unprocessed/<int:log_id>/dismiss", methods=["POST"])
@login_required
def dismiss_unprocessed(log_id: int):
    item = repo.get_unprocessed_media_item(log_id)
    if item and item.get("status") == "pending":
        repo.dismiss_unprocessed_media(log_id)
        flash_t("flash_unprocessed_dismissed", "success")
    return redirect(url_for("whatsapp_settings.settings_index"))
