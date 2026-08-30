from datetime import date
from pathlib import Path

from flask import Blueprint, abort, redirect, render_template, request, session, url_for

from config import Config
from core.auth import login_required
from core.bundle_session import load_bundle_state
from core.dates import format_date, parse_date
from core.i18n import flash_t
from db import repositories as repo

dealers_bp = Blueprint("dealers", __name__)


def _image_url(location_path: str | None) -> str | None:
    if not location_path:
        return None
    filename = Path(location_path).name
    return url_for("ingestion.serve_upload", filename=filename)


def _aging_days(invoice: dict) -> int:
    raw = (invoice.get("delivery_date") or invoice.get("invoiced_date") or "").strip()
    if not raw:
        return 0
    try:
        d = parse_date(str(raw)[:10])
    except ValueError:
        return 0
    return max(0, (date.today() - d).days)


def _parse_invoice_form(location_path=None) -> dict:
    delivery_raw = (request.form.get("delivery_date") or "").strip()
    return {
        "invoice_no": (request.form.get("invoice_no") or "").strip(),
        "invoiced_date": request.form["invoiced_date"],
        "delivery_date": delivery_raw or None,
        "credit_period_days": request.form["credit_period_days"],
        "total_amount": request.form["total_amount"],
        "location_path": location_path,
    }


def _parse_items_from_form() -> list:
    codes = request.form.getlist("item_code")
    names = request.form.getlist("item_name")
    qtys = request.form.getlist("item_qty")
    prices = request.form.getlist("item_price")
    items = []
    for i in range(len(names)):
        name = (names[i] or "").strip()
        if not name:
            continue
        items.append(
            {
                "item_code": (codes[i] if i < len(codes) else "") or "",
                "item_name": name,
                "item_qty": int(qtys[i] if i < len(qtys) and qtys[i] else 1),
                "item_price": float(prices[i] if i < len(prices) and prices[i] else 0),
                "item_discount": 0,
            }
        )
    return items


def _dealer_from_form(form) -> dict:
    acc_raw = form.get("default_user_bank_acc_id", "").strip()
    return {
        "dealer_name": form.get("dealer_name", "").strip(),
        "dealer_email": form.get("dealer_email", "").strip() or None,
        "dealer_telno": form.get("dealer_telno", "").strip() or None,
        "dealer_address": form.get("dealer_address", "").strip() or None,
        "dealer_strictness": form.get("dealer_strictness", "Medium"),
        "casual_days": int(form.get("casual_days") or 3),
        "impossible_days": form.get("impossible_days", "Sunday"),
        "bank_name": form.get("bank_name", "").strip() or None,
        "branch_name": form.get("branch_name", "").strip() or None,
        "account_name": form.get("account_name", "").strip() or None,
        "default_user_bank_acc_id": int(acc_raw) if acc_raw else None,
    }


def _form_context(dealer_data=None):
    accounts = repo.get_bank_accounts()
    data = dealer_data or {}
    if not data.get("default_user_bank_acc_id") and accounts:
        default_id = int(repo.get_setting("default_bank_acc_id", str(accounts[0]["user_bank_acc_id"])))
        if any(a["user_bank_acc_id"] == default_id for a in accounts):
            data = {**data, "default_user_bank_acc_id": default_id}
    return {
        "dealer_data": data,
        "user_bank_accounts": accounts,
    }


def _get_dealer_or_404(dealer_id: int):
    dealer = repo.get_dealer(dealer_id)
    if not dealer:
        abort(404)
    return dealer


@dealers_bp.route("/dealers/new", methods=["GET", "POST"])
@login_required
def new_dealer():
    if request.method == "POST":
        if not request.form.get("confirm_dealer"):
            flash_t("flash_confirm_dealer_required", "error")
            return render_template("dealer_form.html", **_form_context(_dealer_from_form(request.form)))

        data = _dealer_from_form(request.form)
        if not data["dealer_name"]:
            flash_t("flash_dealer_name_required", "error")
            return render_template("dealer_form.html", **_form_context(data))

        existing = repo.find_dealer_by_name_exact(data["dealer_name"])
        if existing:
            flash_t("flash_dealer_duplicate", "error")
            return redirect(url_for("dealers.details", dealer_id=existing["dealer_id"]))

        bank_err = repo.validate_dealer_bank_input(data)
        if bank_err:
            flash_t(bank_err, "error")
            return render_template("dealer_form.html", **_form_context(data))

        dealer_id = repo.create_dealer(data)
        save_err = repo.save_dealer_banking(dealer_id, data)
        if save_err:
            flash_t(save_err, "error")
            return render_template("dealer_form.html", **_form_context(data))

        flash_t("flash_dealer_registered", "success")
        return redirect(url_for("dealers.details", dealer_id=dealer_id))

    return render_template("dealer_form.html", **_form_context())


@dealers_bp.route("/dealers/<int:dealer_id>/details", methods=["GET", "POST"])
@login_required
def details(dealer_id):
    dealer = _get_dealer_or_404(dealer_id)
    bank = repo.get_dealer_preferred_bank(dealer_id)

    if request.method == "POST":
        data = _dealer_from_form(request.form)
        if not data["dealer_name"]:
            flash_t("flash_dealer_name_required", "error")
            return redirect(url_for("dealers.details", dealer_id=dealer_id))

        existing = repo.find_dealer_by_name_exact(
            data["dealer_name"], exclude_dealer_id=dealer_id
        )
        if existing:
            flash_t("flash_dealer_duplicate", "error")
            return redirect(url_for("dealers.details", dealer_id=dealer_id))

        bank_err = repo.validate_dealer_bank_input(data)
        if bank_err:
            flash_t(bank_err, "error")
            return redirect(url_for("dealers.details", dealer_id=dealer_id))

        repo.update_dealer(dealer_id, data)
        save_err = repo.save_dealer_banking(dealer_id, data)
        if save_err:
            flash_t(save_err, "error")
            return redirect(url_for("dealers.details", dealer_id=dealer_id))

        flash_t("flash_dealer_updated", "success")
        return redirect(url_for("dealers.details", dealer_id=dealer_id))

    dealer_data = dict(dealer)
    if bank:
        dealer_data["bank_name"] = bank.get("bank_name") or ""
        dealer_data["branch_name"] = bank.get("branch_name") or ""
        dealer_data["account_name"] = bank.get("account_name") or ""

    ctx = _form_context(dealer_data)
    return render_template(
        "dealer_hub.html",
        dealer=dealer,
        active_tab="details",
        **ctx,
    )


@dealers_bp.route("/dealers/<int:dealer_id>/cheques")
@login_required
def cheques(dealer_id):
    dealer = _get_dealer_or_404(dealer_id)
    state = load_bundle_state(session, dealer_id)
    return render_template(
        "dealer_hub.html",
        dealer=dealer,
        active_tab="cheques",
        invoices=repo.get_verified_unassigned_invoices(dealer_id),
        pending_invoices=repo.get_pending_verification_invoices(dealer_id),
        committed_cheques=repo.get_committed_cheque_bundles(dealer_id),
        summary=repo.get_dealer_invoice_summary(dealer_id),
        bundles=state["bundles"],
        ceiling_lkr=state["ceiling_lkr"],
        chat_history=state["chat_history"],
        validation_issues=state["validation_issues"],
        pending_review=state.get("pending_review"),
        use_fake_ai=Config.use_fake_ai(),
    )


@dealers_bp.route("/dealers/<int:dealer_id>/invoices")
@login_required
def invoices(dealer_id):
    dealer = _get_dealer_or_404(dealer_id)
    rows = repo.get_dealer_invoices(dealer_id)
    for row in rows:
        row["aging_days"] = _aging_days(row)
    return render_template(
        "dealer_hub.html",
        dealer=dealer,
        active_tab="invoices",
        dealer_invoices=rows,
    )


@dealers_bp.route(
    "/dealers/<int:dealer_id>/invoices/<int:invoice_id>",
    methods=["GET", "POST"],
)
@login_required
def invoice_detail(dealer_id, invoice_id):
    dealer = _get_dealer_or_404(dealer_id)
    invoice = repo.get_invoice(invoice_id)
    if not invoice or int(invoice["dealer_id"]) != int(dealer_id):
        abort(404)
    if invoice.get("user_id") is not None and int(invoice["user_id"]) != int(Config.USER_ID):
        abort(404)

    if request.method == "POST":
        data = _parse_invoice_form(invoice.get("location_path"))
        if not data["invoice_no"]:
            flash_t("flash_invoice_no_required", "error")
            return redirect(
                url_for("dealers.invoice_detail", dealer_id=dealer_id, invoice_id=invoice_id)
            )
        existing = repo.find_invoice_by_no_and_dealer(
            data["invoice_no"], dealer_id, exclude_invoice_id=invoice_id
        )
        if existing:
            flash_t("flash_invoice_duplicate", "error", invoice_no=data["invoice_no"])
            return redirect(
                url_for("dealers.invoice_detail", dealer_id=dealer_id, invoice_id=invoice_id)
            )
        items = _parse_items_from_form()
        try:
            repo.update_invoice_record(invoice_id, data, items, dealer_id)
            flash_t("flash_invoice_updated", "success")
        except Exception:
            flash_t("flash_invoice_update_failed", "error")
        return redirect(url_for("dealers.invoices", dealer_id=dealer_id))

    items = repo.get_invoice_items(invoice_id)
    return render_template(
        "dealer_invoice_detail.html",
        dealer=dealer,
        invoice=invoice,
        items=items,
        image_url=_image_url(invoice.get("location_path")),
        default_credit=Config.DEFAULT_CREDIT_PERIOD_DAYS,
        aging_days=_aging_days(invoice),
        today=format_date(date.today()),
    )
