from flask import Blueprint, redirect, render_template, request, url_for

from core.auth import login_required
from core.cash_flow import build_cash_flow_projection
from core.i18n import flash_t
from db import repositories as repo

cash_flow_bp = Blueprint("cash_flow", __name__)


def _account_from_form(form) -> dict:
    return {
        "account_name": (form.get("account_name") or "").strip(),
        "nickname": (form.get("nickname") or "").strip(),
        "bank_name": (form.get("bank_name") or "").strip(),
        "branch_name": (form.get("branch_name") or "").strip(),
        "available_balance": form.get("available_balance") or 0,
    }


def _account_panel_context(account_id: int) -> dict | None:
    selected = repo.get_bank_account(account_id)
    if not selected:
        return None
    return {
        "report": build_cash_flow_projection(account_id),
        "selected_account": selected,
        "selected_account_id": account_id,
        "planned_deposits": repo.get_planned_deposits(account_id),
        "upcoming_cheques": repo.get_upcoming_cheques(account_id),
        "default_bank_acc_id": int(repo.get_setting("default_bank_acc_id", "1") or 1),
    }


@cash_flow_bp.route("/cash-flow")
@cash_flow_bp.route("/cash-flow/account/<int:account_id>")
@login_required
def cash_flow(account_id=None):
    accounts = repo.get_bank_accounts()
    default_id = int(repo.get_setting("default_bank_acc_id", "1") or 1)

    if not accounts:
        return render_template(
            "cash_flow.html",
            accounts=[],
            report=None,
            selected_account=None,
            selected_account_id=None,
            planned_deposits=[],
            upcoming_cheques=[],
            default_bank_acc_id=default_id,
            show_add_form=True,
        )

    if account_id is None:
        account_id = default_id
        if not repo.get_bank_account(account_id):
            account_id = int(accounts[0]["user_bank_acc_id"])

    selected = repo.get_bank_account(account_id)
    if not selected:
        flash_t("flash_bank_account_missing", "error")
        return redirect(url_for("cash_flow.cash_flow"))

    ctx = _account_panel_context(account_id)
    return render_template(
        "cash_flow.html",
        accounts=accounts,
        report=ctx["report"],
        selected_account=ctx["selected_account"],
        selected_account_id=account_id,
        planned_deposits=ctx["planned_deposits"],
        upcoming_cheques=ctx["upcoming_cheques"],
        default_bank_acc_id=ctx["default_bank_acc_id"],
        show_add_form=request.args.get("add") == "1",
    )


@cash_flow_bp.route("/api/cash-flow/<int:account_id>/panel")
@login_required
def cash_flow_panel(account_id):
    from flask import jsonify

    ctx = _account_panel_context(account_id)
    if not ctx:
        return jsonify({"error": "not_found"}), 404
    html = render_template("_cash_flow_account_panel.html", **ctx)
    return jsonify({"html": html, "account_id": account_id})


@cash_flow_bp.route("/api/cash-flow/<int:account_id>/liquidity-schedule")
@login_required
def liquidity_schedule_api(account_id):
    from flask import jsonify

    report = build_cash_flow_projection(account_id)
    return jsonify(report.liquidity_schedule)


@cash_flow_bp.route("/cash-flow/accounts/new", methods=["POST"])
@login_required
def create_account():
    data = _account_from_form(request.form)
    err = repo.validate_bank_account_input(data)
    if err:
        flash_t(err, "error")
        return redirect(url_for("cash_flow.cash_flow", add=1))

    new_id = repo.create_bank_account(data)
    accounts_after = repo.get_bank_accounts()
    if request.form.get("set_as_default") or len(accounts_after) == 1:
        repo.set_setting("default_bank_acc_id", str(new_id))

    flash_t("flash_bank_account_created", "success")
    return redirect(url_for("cash_flow.cash_flow", account_id=new_id))


@cash_flow_bp.route("/cash-flow/accounts/<int:account_id>/edit", methods=["POST"])
@login_required
def edit_account(account_id):
    if not repo.get_bank_account(account_id):
        flash_t("flash_bank_account_missing", "error")
        return redirect(url_for("cash_flow.cash_flow"))

    data = _account_from_form(request.form)
    err = repo.validate_bank_account_input(data)
    if err:
        flash_t(err, "error")
        return redirect(url_for("cash_flow.cash_flow", account_id=account_id))

    repo.update_bank_account(account_id, data)
    if request.form.get("set_as_default"):
        repo.set_setting("default_bank_acc_id", str(account_id))
    flash_t("flash_bank_account_updated", "success")
    return redirect(url_for("cash_flow.cash_flow", account_id=account_id))


@cash_flow_bp.route("/cash-flow/accounts/<int:account_id>/set-default", methods=["POST"])
@login_required
def set_default_account(account_id):
    if not repo.get_bank_account(account_id):
        flash_t("flash_bank_account_missing", "error")
        return redirect(url_for("cash_flow.cash_flow"))
    repo.set_setting("default_bank_acc_id", str(account_id))
    flash_t("flash_bank_default_set", "success")
    return redirect(url_for("cash_flow.cash_flow", account_id=account_id))


@cash_flow_bp.route("/cash-flow/balance", methods=["POST"])
@login_required
def update_balance():
    acc_id = int(request.form["account_id"])
    if not repo.get_bank_account(acc_id):
        flash_t("flash_bank_account_missing", "error")
        return redirect(url_for("cash_flow.cash_flow"))
    balance = float(request.form["balance"])
    repo.update_balance(acc_id, balance)
    flash_t("flash_balance_updated", "success")
    return redirect(url_for("cash_flow.cash_flow", account_id=acc_id))


@cash_flow_bp.route("/cash-flow/planned", methods=["POST"])
@login_required
def add_planned():
    acc_id = int(request.form["account_id"])
    if not repo.get_bank_account(acc_id):
        flash_t("flash_bank_account_missing", "error")
        return redirect(url_for("cash_flow.cash_flow"))
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
