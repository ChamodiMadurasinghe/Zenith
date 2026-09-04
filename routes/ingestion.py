import json
import uuid
from datetime import date
from pathlib import Path
from typing import Optional

from flask import Blueprint, abort, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.utils import secure_filename

from config import Config
from core.auth import login_required
from core.dates import format_date, impossible_days_from_form
from core.i18n import flash_t, flash_vision_error
from core.ingestion_helpers import PENDING_SUPPLIER_NAME, dealer_setup_from_extraction, merge_dealer_setup, parse_items_from_form
from core.whatsapp_intake import extract_image_to_pending_invoice
from db import repositories as repo

ingestion_bp = Blueprint("ingestion", __name__)

ALLOWED = {".jpg", ".jpeg", ".png", ".webp"}


def _drafts():
    return session.setdefault("drafts", {})


def _image_url(location_path: Optional[str]) -> Optional[str]:
    if not location_path:
        return None
    filename = Path(location_path).name
    return url_for("ingestion.serve_upload", filename=filename)


def _form_dealer_id():
    raw = (request.form.get("dealer_id") or "").strip()
    if not raw or raw == "__add__":
        return None
    return raw


def _parse_items_from_form():
    return parse_items_from_form(request.form)


def _parse_invoice_data_from_form(location_path=None):
    delivery_raw = (request.form.get("delivery_date") or "").strip()
    return {
        "invoice_no": (request.form.get("invoice_no") or "").strip(),
        "invoiced_date": request.form["invoiced_date"],
        "delivery_date": delivery_raw or None,
        "credit_period_days": request.form["credit_period_days"],
        "total_amount": request.form["total_amount"],
        "location_path": location_path,
    }


def _block_duplicate_invoice(
    invoice_no: str,
    dealer_id: int,
    *,
    exclude_invoice_id: int | None = None,
) -> bool:
    """Flash and return True when this dealer already has the invoice number."""
    existing = repo.find_invoice_by_no_and_dealer(
        invoice_no, int(dealer_id), exclude_invoice_id=exclude_invoice_id
    )
    if existing:
        flash_t("flash_invoice_duplicate", "error", invoice_no=invoice_no.strip())
        return True
    return False


def _parse_dealer_form_data():
    acc_raw = request.form.get("default_user_bank_acc_id", "").strip()
    return {
        "dealer_name": request.form["dealer_name"],
        "dealer_email": request.form.get("dealer_email"),
        "dealer_telno": request.form.get("dealer_telno"),
        "dealer_address": request.form.get("dealer_address"),
        "dealer_strictness": request.form.get("dealer_strictness", "Medium"),
        "casual_days": request.form.get("casual_days", 3),
        "impossible_days": impossible_days_from_form(request.form),
        "account_name": request.form.get("account_name", "").strip() or None,
        "bank_name": request.form.get("bank_name", "").strip() or None,
        "branch_name": request.form.get("branch_name", "").strip() or None,
        "default_user_bank_acc_id": int(acc_raw) if acc_raw else None,
    }


def _default_user_bank_acc_id():
    accounts = repo.get_bank_accounts()
    if not accounts:
        return None
    return int(repo.get_setting("default_bank_acc_id", str(accounts[0]["user_bank_acc_id"])))


def _dealer_setup_from_invoice(invoice: dict) -> dict | None:
    raw = invoice.get("pending_dealer_json")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None


def _anomalies_from_invoice(invoice: dict) -> list[dict]:
    raw = invoice.get("pending_dealer_json")
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed.get("anomalies") or []


def _audit_from_invoice(invoice: dict) -> dict | None:
    raw = invoice.get("pending_dealer_json")
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed.get("audit")


def _run_agent2_audit(
    extracted: dict,
    dealer_id: int | None,
    *,
    exclude_invoice_id: int | None = None,
) -> tuple[list[dict], dict]:
    from agents.anomaly import audit_invoice, check_invoice_anomalies

    try:
        audit = audit_invoice(
            extracted, dealer_id, exclude_invoice_id=exclude_invoice_id
        )
        anomalies = check_invoice_anomalies(
            extracted, dealer_id, exclude_invoice_id=exclude_invoice_id
        )
    except Exception:
        audit = {
            "status": "GOOD_TO_GO",
            "risk_level": "LOW",
            "remark": "Automatic checks could not run — please review manually.",
            "findings": [],
            "chat_messages": [
                {
                    "role": "agent2",
                    "content": "I could not run automatic checks — please review this invoice manually.",
                }
            ],
        }
        anomalies = []
    return anomalies, audit


@ingestion_bp.route("/uploads/<path:filename>")
@login_required
def serve_upload(filename):
    return send_from_directory(Config.UPLOAD_FOLDER, filename)


@ingestion_bp.route("/")
@login_required
def dashboard():
    whatsapp_inbox = repo.get_whatsapp_inbox_pending()
    for row in whatsapp_inbox:
        row["image_url"] = _image_url(row.get("location_path"))
    return render_template(
        "upload.html",
        invoices=repo.get_recent_invoices(),
        pending_invoices=repo.get_pending_verification_invoices(),
        whatsapp_inbox=whatsapp_inbox,
        dealers=repo.get_dealers(),
        default_credit=Config.DEFAULT_CREDIT_PERIOD_DAYS,
    )


@ingestion_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    file = request.files.get("invoice_image")
    if not file or not file.filename:
        flash_t("flash_select_image", "error")
        return redirect(url_for("ingestion.dashboard"))

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED:
        flash_t("flash_allowed_formats", "error")
        return redirect(url_for("ingestion.dashboard"))

    Config.UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    draft_id = str(uuid.uuid4())
    filename = secure_filename(f"{draft_id}{ext}")
    path = Config.UPLOAD_FOLDER / filename
    file.save(path)

    extracted = None
    gemini_error = None
    try:
        from agents.ingestion import extract_invoice

        extracted = extract_invoice(str(path))
    except Exception as e:
        gemini_error = str(e)
        extracted = {
            "invoice_no": "",
            "supplier_name": "",
            "invoiced_date": "",
            "total_amount": 0,
            "credit_period_days": Config.DEFAULT_CREDIT_PERIOD_DAYS,
            "line_items": [],
        }

    supplier = (extracted.get("supplier_name") or "").strip()
    dealer = repo.find_dealer_by_name(supplier) if supplier else None
    anomalies, audit = _run_agent2_audit(
        extracted, dealer["dealer_id"] if dealer else None
    )
    invoice_setup = dealer_setup_from_extraction(extracted)
    dealer_setup = None

    if supplier and not dealer:
        try:
            from agents.assistant import suggest_dealer_setup

            dealer_setup = merge_dealer_setup(invoice_setup, suggest_dealer_setup(supplier))
        except Exception:
            dealer_setup = invoice_setup

    _drafts()[draft_id] = {
        "extracted": {
            **extracted,
            "delivery_date": extracted.get("delivery_date") or format_date(date.today()),
        },
        "location_path": f"storage/invoices/{filename}",
        "dealer_id": dealer["dealer_id"] if dealer else None,
        "dealer_setup": dealer_setup,
        "new_dealer": dealer is None and bool(supplier),
        "anomalies": anomalies,
        "audit": audit,
    }
    session.modified = True

    if gemini_error:
        flash_vision_error(gemini_error)

    return redirect(url_for("ingestion.review", draft_id=draft_id))


@ingestion_bp.route("/review/<draft_id>", methods=["GET", "POST"])
@login_required
def review(draft_id):
    draft = _drafts().get(draft_id)
    if not draft:
        flash_t("flash_draft_expired", "error")
        return redirect(url_for("ingestion.dashboard"))

    extracted = draft["extracted"]
    dealers = repo.get_dealers()

    if request.method == "POST" and request.form.get("action") == "create_dealer":
        if not request.form.get("confirm_dealer"):
            flash_t("flash_confirm_dealer_required", "error")
            return redirect(url_for("ingestion.review", draft_id=draft_id))

        name = request.form.get("dealer_name", "").strip()
        existing = repo.find_dealer_by_name_exact(name)
        if existing:
            # Same supplier already registered — reuse; do not create a second row.
            draft["dealer_id"] = int(existing["dealer_id"])
            draft["new_dealer"] = False
            session.modified = True
            flash_t("flash_dealer_reused", "success", name=existing["dealer_name"])
            return redirect(url_for("ingestion.review", draft_id=draft_id))

        data = _parse_dealer_form_data()
        bank_err = repo.validate_dealer_bank_input(data)
        if bank_err:
            flash_t(bank_err, "error")
            return redirect(url_for("ingestion.review", draft_id=draft_id))

        dealer_id = repo.create_dealer(data)
        save_err = repo.save_dealer_banking(dealer_id, data)
        if save_err:
            flash_t(save_err, "error")
            return redirect(url_for("ingestion.review", draft_id=draft_id))
        draft["dealer_id"] = dealer_id
        draft["new_dealer"] = False
        session.modified = True
        flash_t("flash_dealer_registered", "success")
        return redirect(url_for("ingestion.review", draft_id=draft_id))

    accounts = repo.get_bank_accounts()
    default_acc = _default_user_bank_acc_id()

    return render_template(
        "review_invoice.html",
        draft_id=draft_id,
        extracted=extracted,
        dealers=[d for d in dealers if d["dealer_name"] != PENDING_SUPPLIER_NAME],
        dealer_id=draft.get("dealer_id"),
        dealer_setup=draft.get("dealer_setup"),
        new_dealer=draft.get("new_dealer"),
        location_path=draft["location_path"],
        image_url=_image_url(draft["location_path"]),
        default_credit=Config.DEFAULT_CREDIT_PERIOD_DAYS,
        today=format_date(date.today()),
        is_upload_review=True,
        user_bank_accounts=accounts,
        dealer_bank_data={"default_user_bank_acc_id": default_acc},
        anomalies=draft.get("anomalies") or [],
        audit=draft.get("audit"),
    )


@ingestion_bp.route("/review/<draft_id>/verify", methods=["POST"])
@login_required
def verify(draft_id):
    draft = _drafts().get(draft_id)
    if not draft:
        flash_t("flash_draft_expired", "error")
        return redirect(url_for("ingestion.dashboard"))

    if not request.form.get("confirm_matches"):
        flash_t("flash_confirm_required", "error")
        return redirect(url_for("ingestion.review", draft_id=draft_id))

    dealer_id = _form_dealer_id() or draft.get("dealer_id")
    if not dealer_id:
        if draft.get("new_dealer"):
            flash_t("flash_verify_dealer_first", "error")
        else:
            flash_t("flash_select_dealer", "error")
        return redirect(url_for("ingestion.review", draft_id=draft_id))

    items = _parse_items_from_form()
    data = _parse_invoice_data_from_form(draft["location_path"])
    if not data["invoice_no"]:
        flash_t("flash_invoice_no_required", "error")
        return redirect(url_for("ingestion.review", draft_id=draft_id))
    if _block_duplicate_invoice(data["invoice_no"], int(dealer_id)):
        return redirect(url_for("ingestion.review", draft_id=draft_id))
    repo.save_verified_invoice(data, items, int(dealer_id))
    _drafts().pop(draft_id, None)
    session.modified = True
    flash_t("flash_invoice_verified", "success")
    return redirect(url_for("ingestion.dashboard"))


@ingestion_bp.route("/invoice/<int:invoice_id>/verify", methods=["GET", "POST"])
@login_required
def verify_invoice(invoice_id):
    invoice = repo.get_invoice(invoice_id)
    if not invoice:
        abort(404)
    if invoice["is_invoice_verified"]:
        flash_t("flash_already_verified", "success")
        return redirect(url_for("ingestion.dashboard"))

    pending_supplier_id = repo.get_pending_supplier_dealer_id()
    dealer_setup = _dealer_setup_from_invoice(invoice)
    new_dealer = invoice["dealer_id"] == pending_supplier_id

    items = repo.get_invoice_items(invoice_id)
    line_items = [
        {
            "item_code": it["item_code"],
            "item_name": it["item_name"],
            "item_qty": it["item_qty"],
            "item_price": it["item_price"],
            "item_discount": it.get("item_discount", 0),
            "item_mrp": it.get("item_mrp", 0),
            "item_line_total": it.get("item_line_total", 0),
        }
        for it in items
    ]
    extracted = {
        "invoice_no": invoice["invoice_no"],
        "supplier_name": (dealer_setup or {}).get("dealer_name") or invoice.get("dealer_name") or "",
        "invoiced_date": invoice["invoiced_date"],
        "delivery_date": invoice.get("delivery_date") or "",
        "total_amount": invoice["total_amount"],
        "credit_period_days": invoice["credit_period_days"],
        "line_items": line_items,
    }

    dealer_for_audit = invoice["dealer_id"] if not new_dealer else None
    if dealer_for_audit == pending_supplier_id:
        dealer_for_audit = None
    anomalies, audit = _run_agent2_audit(
        extracted,
        int(dealer_for_audit) if dealer_for_audit else None,
        exclude_invoice_id=invoice_id,
    )

    if request.method == "POST" and request.form.get("action") == "create_dealer":
        if not request.form.get("confirm_dealer"):
            flash_t("flash_confirm_dealer_required", "error")
            return redirect(url_for("ingestion.verify_invoice", invoice_id=invoice_id))

        name = request.form.get("dealer_name", "").strip()
        existing = repo.find_dealer_by_name_exact(name)
        if existing:
            repo.update_invoice_dealer_id(invoice_id, int(existing["dealer_id"]))
            flash_t("flash_dealer_reused", "success", name=existing["dealer_name"])
            return redirect(url_for("ingestion.verify_invoice", invoice_id=invoice_id))

        data = _parse_dealer_form_data()
        bank_err = repo.validate_dealer_bank_input(data)
        if bank_err:
            flash_t(bank_err, "error")
            return redirect(url_for("ingestion.verify_invoice", invoice_id=invoice_id))

        dealer_id = repo.create_dealer(data)
        save_err = repo.save_dealer_banking(dealer_id, data)
        if save_err:
            flash_t(save_err, "error")
            return redirect(url_for("ingestion.verify_invoice", invoice_id=invoice_id))

        repo.update_invoice_dealer_id(invoice_id, dealer_id)
        flash_t("flash_dealer_registered", "success")
        return redirect(url_for("ingestion.verify_invoice", invoice_id=invoice_id))

    if request.method == "POST":
        if not request.form.get("confirm_matches"):
            flash_t("flash_confirm_required", "error")
            return redirect(url_for("ingestion.verify_invoice", invoice_id=invoice_id))

        dealer_id = _form_dealer_id() or invoice["dealer_id"]
        if not dealer_id or int(dealer_id) == pending_supplier_id:
            if new_dealer:
                flash_t("flash_verify_dealer_first", "error")
            else:
                flash_t("flash_select_dealer", "error")
            return redirect(url_for("ingestion.verify_invoice", invoice_id=invoice_id))

        data = _parse_invoice_data_from_form(invoice.get("location_path"))
        if not data["invoice_no"]:
            flash_t("flash_invoice_no_required", "error")
            return redirect(url_for("ingestion.verify_invoice", invoice_id=invoice_id))
        if _block_duplicate_invoice(
            data["invoice_no"], int(dealer_id), exclude_invoice_id=invoice_id
        ):
            return redirect(url_for("ingestion.verify_invoice", invoice_id=invoice_id))
        repo.update_verified_invoice(invoice_id, data, _parse_items_from_form(), int(dealer_id))
        flash_t("flash_invoice_verified", "success")
        return redirect(url_for("ingestion.dashboard"))

    invoice = repo.get_invoice(invoice_id)
    new_dealer = invoice["dealer_id"] == pending_supplier_id

    return render_template(
        "verify_invoice.html",
        invoice_id=invoice_id,
        extracted=extracted,
        dealers=[d for d in repo.get_dealers() if d["dealer_name"] != PENDING_SUPPLIER_NAME],
        dealer_id=invoice["dealer_id"] if not new_dealer else None,
        dealer_setup=dealer_setup,
        new_dealer=new_dealer,
        image_url=_image_url(invoice.get("location_path")),
        location_path=invoice.get("location_path"),
        default_credit=Config.DEFAULT_CREDIT_PERIOD_DAYS,
        user_bank_accounts=repo.get_bank_accounts(),
        dealer_bank_data={"default_user_bank_acc_id": _default_user_bank_acc_id()},
        anomalies=anomalies,
        audit=audit,
    )


@ingestion_bp.route("/invoice/manual", methods=["GET", "POST"])
@login_required
def manual_invoice():
    dealers = repo.get_dealers()
    if request.method == "POST":
        dealer_id = _form_dealer_id()
        if not dealer_id:
            flash_t("flash_select_dealer", "error")
            return redirect(url_for("ingestion.manual_invoice"))

        items = _parse_items_from_form()
        data = _parse_invoice_data_from_form(None)
        if not data["invoice_no"]:
            flash_t("flash_invoice_no_required", "error")
            return redirect(url_for("ingestion.manual_invoice"))
        if _block_duplicate_invoice(data["invoice_no"], int(dealer_id)):
            return redirect(url_for("ingestion.manual_invoice"))
        repo.save_verified_invoice(data, items, int(dealer_id))
        flash_t("flash_invoice_saved", "success")
        return redirect(url_for("ingestion.dashboard"))

    return render_template(
        "manual_invoice.html",
        dealers=[d for d in dealers if d["dealer_name"] != PENDING_SUPPLIER_NAME],
        default_credit=Config.DEFAULT_CREDIT_PERIOD_DAYS,
        today=format_date(date.today()),
        user_bank_accounts=repo.get_bank_accounts(),
        dealer_bank_data={"default_user_bank_acc_id": _default_user_bank_acc_id()},
    )


@ingestion_bp.route("/whatsapp-inbox/<int:inbox_id>/extract", methods=["POST"])
@login_required
def extract_whatsapp_inbox(inbox_id):
    item = repo.get_whatsapp_inbox_item(inbox_id)
    if not item or item.get("status") != "pending":
        flash_t("flash_whatsapp_inbox_missing", "error")
        return redirect(url_for("ingestion.dashboard"))

    location_path = item.get("location_path") or ""
    received_at = (item.get("received_at") or "").strip()
    delivery_date = received_at[:10] if len(received_at) >= 10 else None
    try:
        invoice_id = extract_image_to_pending_invoice(
            location_path,
            sender_phone=item.get("sender_phone"),
            delivery_date=delivery_date,
        )
        repo.mark_whatsapp_inbox_extracted(inbox_id, invoice_id)
        flash_t("flash_whatsapp_extracted", "success")
        return redirect(url_for("ingestion.verify_invoice", invoice_id=invoice_id))
    except Exception as exc:
        flash_vision_error(exc)
        return redirect(url_for("ingestion.dashboard"))


@ingestion_bp.route("/whatsapp-inbox/<int:inbox_id>/dismiss", methods=["POST"])
@login_required
def dismiss_whatsapp_inbox(inbox_id):
    item = repo.get_whatsapp_inbox_item(inbox_id)
    if item and item.get("status") == "pending":
        repo.dismiss_whatsapp_inbox(inbox_id)
        flash_t("flash_whatsapp_dismissed", "success")
    return redirect(url_for("ingestion.dashboard"))


@ingestion_bp.route("/api/check-dealer-name")
@login_required
def api_check_dealer_name():
    name = (request.args.get("name") or "").strip()
    exclude_id = request.args.get("exclude_id", type=int)
    if not name:
        return jsonify({"ok": True, "available": True})
    existing = repo.find_dealer_by_name_exact(name, exclude_dealer_id=exclude_id)
    return jsonify(
        {
            "ok": True,
            "available": existing is None,
            "existing_id": int(existing["dealer_id"]) if existing else None,
            "existing_name": existing["dealer_name"] if existing else None,
        }
    )


@ingestion_bp.route("/api/check-invoice-no")
@login_required
def api_check_invoice_no():
    invoice_no = (request.args.get("invoice_no") or "").strip()
    dealer_id = request.args.get("dealer_id", type=int)
    exclude_id = request.args.get("exclude_id", type=int)
    if not invoice_no or not dealer_id:
        return jsonify({"ok": True, "available": True})
    existing = repo.find_invoice_by_no_and_dealer(
        invoice_no, dealer_id, exclude_invoice_id=exclude_id
    )
    return jsonify(
        {
            "ok": True,
            "available": existing is None,
            "existing_id": int(existing["invoices_id"]) if existing else None,
        }
    )
