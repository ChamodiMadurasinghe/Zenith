"""
Routes for the monthly bank-statement verification feature.

This is a standalone blueprint — it does not modify `routes/cash_flow.py`
(Person One's file). It injects the extra data the Bank Balance tab needs
(mail settings + latest verification) via an app-wide context processor,
so `_bank_balance.html` can read it without the existing `account_balance`
view function having to change.

Mail settings live on their own page (`/settings/bank-statement`) rather
than inline in the Balance tab — reachable from the "Manage mail settings"
link there.
"""

from flask import Blueprint, current_app, redirect, render_template, request, url_for

import core.bank_statement_mail as bank_statement_mail
from core.auth import login_required
from core.i18n import flash_t
from db import repositories as repo

bank_statement_bp = Blueprint("bank_statement", __name__)


def _balance_tab_url(account_id: int):
    return url_for("cash_flow.account_balance", account_id=account_id)


def _settings_page_url():
    return url_for("bank_statement.settings_page")


@bank_statement_bp.app_context_processor
def inject_statement_widget_data():
    """Makes `get_statement_widget_data(account_id)` available in every template."""

    def get_statement_widget_data(account_id):
        return {
            "statement_mail_config": bank_statement_mail.get_mail_config(account_id),
            "statement_verification": bank_statement_mail.latest_verification(account_id),
        }

    return {"get_statement_widget_data": get_statement_widget_data}


@bank_statement_bp.route("/settings/bank-statement", methods=["GET"])
@login_required
def settings_page():
    accounts = repo.get_bank_accounts()
    configs = {
        acc["user_bank_acc_id"]: bank_statement_mail.get_mail_config(acc["user_bank_acc_id"])
        for acc in accounts
    }
    return render_template("bank_statement_settings.html", accounts=accounts, configs=configs)


@bank_statement_bp.route("/cash-flow/account/<int:account_id>/statement/mail-settings", methods=["POST"])
@login_required
def save_mail_settings(account_id):
    if not repo.get_bank_account(account_id):
        flash_t("flash_bank_account_missing", "error")
        return redirect(url_for("cash_flow.cash_flow"))

    business_email = (request.form.get("business_email") or "").strip()
    app_password = (request.form.get("business_email_app_password") or "").strip()
    bank_email = (request.form.get("bank_email") or "").strip()
    imap_host = (request.form.get("imap_host") or "imap.gmail.com").strip()
    try:
        imap_port = int(request.form.get("imap_port") or 993)
    except ValueError:
        imap_port = 993

    if not business_email or not bank_email:
        flash_t("flash_statement_mail_settings_missing", "error")
        return redirect(_settings_page_url())

    bank_statement_mail.save_mail_config(
        account_id, business_email, app_password, bank_email, imap_host, imap_port
    )
    flash_t("flash_statement_mail_settings_saved", "success")
    return redirect(_settings_page_url())


@bank_statement_bp.route("/cash-flow/account/<int:account_id>/statement/verify", methods=["POST"])
@login_required
def verify_statement(account_id):
    if not repo.get_bank_account(account_id):
        flash_t("flash_bank_account_missing", "error")
        return redirect(url_for("cash_flow.cash_flow"))

    if not bank_statement_mail.get_mail_config(account_id):
        # Belt-and-braces: the template's own JS should already have stopped
        # this with an alert() before it ever got submitted.
        flash_t("flash_statement_no_config", "error")
        return redirect(_balance_tab_url(account_id))

    # The template's confirm() dialog is the "ask permission to access the
    # mail" step; this hidden field is the record that the user said yes.
    if request.form.get("confirm_mail_access") != "1":
        flash_t("flash_statement_permission_needed", "error")
        return redirect(_balance_tab_url(account_id))

    result = bank_statement_mail.run_verification(account_id, is_test=False)
    if result.get("error") == "no_mail_config":
        flash_t("flash_statement_no_config", "error")
    elif result.get("error") == "no_statement_found":
        flash_t("flash_statement_not_found", "error")
    elif result.get("error") == "mail_connection_failed":
        current_app.logger.warning("Bank statement mail login failed: %s", result.get("detail"))
        flash_t("flash_statement_connection_failed", "error", detail=result.get("detail", ""))
    elif result.get("error") == "unexpected":
        current_app.logger.exception("Bank statement verification failed: %s", result.get("detail"))
        flash_t("flash_statement_unexpected_error", "error")
    else:
        flash_t("flash_statement_verified", "success")
    return redirect(_balance_tab_url(account_id))
