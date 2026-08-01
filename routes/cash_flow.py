from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from core.auth import login_required
from core.i18n import flash_t
from core.cash_flow import build_cash_flow_projection
from db import repositories as repo

cash_flow_bp = Blueprint("cash_flow", __name__)


@cash_flow_bp.route("/cash-flow")
@cash_flow_bp.route("/cash-flow/account/<int:account_id>")
@login_required
def cash_flow(account_id=None):
    accounts = repo.get_bank_accounts()
    if not accounts:
        flash_t("flash_no_accounts", "error")
        return redirect(url_for("ingestion.dashboard"))
    if account_id is None:
        account_id = int(repo.get_setting("default_bank_acc_id", "1"))
    report = build_cash_flow_projection(account_id)
    planned = repo.get_planned_deposits(account_id)
    return render_template(
        "cash_flow.html",
        accounts=accounts,
        report=report,
        selected_account_id=account_id,
        planned_deposits=planned,
    )


@cash_flow_bp.route("/api/cash-flow/<int:account_id>/liquidity-schedule")
@login_required
def liquidity_schedule_api(account_id):
    report = build_cash_flow_projection(account_id)
    return jsonify(report.liquidity_schedule)


@cash_flow_bp.route("/cash-flow/balance", methods=["POST"])
@login_required
def update_balance():
    acc_id = int(request.form["account_id"])
    balance = float(request.form["balance"])
    repo.update_balance(acc_id, balance)
    flash_t("flash_balance_updated", "success")
    return redirect(url_for("cash_flow.cash_flow", account_id=acc_id))


@cash_flow_bp.route("/cash-flow/planned", methods=["POST"])
@login_required
def add_planned():
    acc_id = int(request.form["account_id"])
    repo.add_planned_deposit(
        acc_id,
        request.form["planned_date"],
        float(request.form["amount"]),
        request.form.get("notes", ""),
    )
    flash_t("flash_deposit_added", "success")
    return redirect(url_for("cash_flow.cash_flow", account_id=acc_id))


@cash_flow_bp.route("/cash-flow/planned/<int:planned_id>/complete", methods=["POST"])
@login_required
def complete_planned(planned_id):
    planned = repo.complete_planned_deposit(planned_id)
    if planned:
        flash_t("flash_deposit_complete", "success")
        return redirect(url_for("cash_flow.cash_flow", account_id=planned["user_bank_acc_id"]))
    flash_t("flash_deposit_not_found", "error")
    return redirect(url_for("cash_flow.cash_flow"))
