"""
Routes for the monthly bank-statement verification feature.

This is a standalone blueprint — it does not modify `routes/cash_flow.py`
(Person One's file). It injects the extra data the Bank Balance tab needs
(mail settings + latest verification) via an app-wide context processor,
so `_bank_balance.html` can read it without the existing `account_balance`
view function having to change.
"""

from flask import Blueprint, redirect, request, url_for

import core.bank_statement_mail as bank_statement_mail
from core.auth import login_required
from core.i18n import flash_t
from db import repositories as repo

bank_statement_bp = Blueprint("bank_statement", __name__)


def _balance_tab_url(account_id: int):
    return url_for("cash_flow.account_balance", account_id=account_id)


@bank_statement_bp.app_context_processor
def inject_statement_widget_data():
    """Makes `get_statement_widget_data(account_id)` available in every template."""

    def get_statement_widget_data(account_id):
        return {
            "statement_mail_config": bank_statement_mail.get_mail_config(account_id),
            "statement_verification": bank_statement_mail.latest_verification(account_id),
        }

    return {"get_statement_widget_data": get_statement_widget_data}


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
        return redirect(_balance_tab_url(account_id))

    bank_statement_mail.save_mail_config(
        account_id, business_email, app_password, bank_email, imap_host, imap_port
    )
    flash_t("flash_statement_mail_settings_saved", "success")
    return redirect(_balance_tab_url(account_id))


@bank_statement_bp.route("/cash-flow/account/<int:account_id>/statement/verify", methods=["POST"])
@login_required
def verify_statement(account_id):
    if not repo.get_bank_account(account_id):
        flash_t("flash_bank_account_missing", "error")
        return redirect(url_for("cash_flow.cash_flow"))

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
    else:
        flash_t("flash_statement_verified", "success")
    return redirect(_balance_tab_url(account_id))


@bank_statement_bp.route("/cash-flow/account/<int:account_id>/statement/verify-test", methods=["POST"])
@login_required
def verify_statement_test(account_id):
    """Runs the whole pipeline against built-in sample statement text — no
    real mailbox needed. This is the 'way to test the newly added
    functions' from inside the app itself."""
    if not repo.get_bank_account(account_id):
        flash_t("flash_bank_account_missing", "error")
        return redirect(url_for("cash_flow.cash_flow"))

    bank_statement_mail.run_verification(account_id, is_test=True)
    flash_t("flash_statement_test_ran", "success")
    return redirect(_balance_tab_url(account_id))
