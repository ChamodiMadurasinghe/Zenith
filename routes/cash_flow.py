from datetime import date

from flask import Blueprint, redirect, render_template, request, url_for

from core.auth import login_required
from core.cash_flow import build_cash_flow_projection
from core.i18n import flash_t
from db import repositories as repo

cash_flow_bp = Blueprint("cash_flow", __name__)


def _account_from_form(form) -> dict:
    bank_code = (form.get("bank_code") or "").strip()
    bank_name = repo.bank_name_for_code(bank_code) or (form.get("bank_name") or "").strip()
    return {
        "account_name": (form.get("account_name") or "").strip(),
        "nickname": (form.get("nickname") or "").strip(),
        "bank_code": bank_code,
        "bank_name": bank_name,
        "branch_name": (form.get("branch_name") or "").strip(),
        "available_balance": form.get("available_balance") or 0,
        "overdraft_limit": form.get("overdraft_limit") or 0,
    }


def _bank_form_context(bank_name: str | None = None) -> dict:
    from core.cheque_utils import resolve_bank_code

    return {
        "bank_templates": repo.list_bank_cheque_templates(),
        "selected_bank_code": resolve_bank_code(bank_name),
    }


def _cheque_setup_from_form(form) -> tuple[float, float]:
    use_standard = form.get("use_standard_cheque_size") == "1"
    if use_standard:
        return repo.CITS_CHEQUE_LENGTH_MM, repo.CITS_CHEQUE_WIDTH_MM
    try:
        length_mm = float(form.get("cheque_length_mm") or repo.CITS_CHEQUE_LENGTH_MM)
        width_mm = float(form.get("cheque_width_mm") or repo.CITS_CHEQUE_WIDTH_MM)
    except (TypeError, ValueError):
        return repo.CITS_CHEQUE_LENGTH_MM, repo.CITS_CHEQUE_WIDTH_MM
    return length_mm, width_mm


def _save_cheque_setup(account_id: int, bank_name: str, form, bank_code: str | None = None) -> str | None:
    length_mm, width_mm = _cheque_setup_from_form(form)
    return repo.save_account_cheque_setup(
        account_id, bank_name, length_mm, width_mm, bank_code=bank_code
    )


def _default_account_id() -> int:
    return int(repo.get_setting("default_bank_acc_id", "1") or 1)


def _missing_account():
    flash_t("flash_bank_account_missing", "error")
    return redirect(url_for("cash_flow.cash_flow"))


def _balance_tab_url(account_id: int):
    return url_for("cash_flow.account_balance", account_id=account_id)


def _details_tab_url(account_id: int):
    return url_for("cash_flow.account_details", account_id=account_id)


def _printer_tab_url(account_id: int):
    return url_for("cash_flow.account_printer", account_id=account_id)


def _render_hub(account, active_tab, **extra):
    ctx = {
        "selected_account": account,
        "selected_account_id": account["user_bank_acc_id"],
        "default_bank_acc_id": _default_account_id(),
        "active_tab": active_tab,
        "today": date.today().isoformat(),
        "report": extra.pop("report", None),
        "planned_deposits": extra.pop("planned_deposits", []),
        "bank_deposits": extra.pop("bank_deposits", []),
        "written_cheques": extra.pop("written_cheques", []),
        "cheque_filter": extra.pop("cheque_filter", {}),
    }
    ctx.update(extra)
    return render_template("bank_hub.html", **ctx)


def _load_balance_data(account_id: int) -> dict:
    return {
        "report": build_cash_flow_projection(account_id),
        "planned_deposits": repo.get_planned_deposits(account_id),
        "bank_deposits": repo.get_bank_deposits(account_id, limit=20),
    }


@cash_flow_bp.route("/cash-flow")
@login_required
def cash_flow():
    accounts = repo.get_bank_accounts()
    return render_template(
        "cash_flow.html",
        accounts=accounts,
        default_bank_acc_id=_default_account_id(),
        cheque_setup=repo.get_account_cheque_setup(None, None),
        **_bank_form_context(),
    )


@cash_flow_bp.route("/cash-flow/account/<int:account_id>")
@login_required
def account_home(account_id):
    if not repo.get_bank_account(account_id):
        return _missing_account()
    return redirect(_balance_tab_url(account_id))


@cash_flow_bp.route("/cash-flow/accounts/new", methods=["GET"])
@login_required
def new_account():
    return render_template(
        "bank_account_new.html",
        accounts=repo.get_bank_accounts(),
        cheque_setup=repo.get_account_cheque_setup(None, None),
        **_bank_form_context(),
    )


@cash_flow_bp.route("/cash-flow/account/<int:account_id>/details", methods=["GET", "POST"])
@login_required
def account_details(account_id):
    account = repo.get_bank_account(account_id)
    if not account:
        return _missing_account()
    if request.method == "POST":
        data = _account_from_form(request.form)
        err = repo.validate_bank_account_input(data)
        if err:
            flash_t(err, "error")
            return redirect(_details_tab_url(account_id))
        dim_err = _save_cheque_setup(
            account_id, data["bank_name"], request.form, bank_code=data.get("bank_code")
        )
        if dim_err:
            flash_t(dim_err, "error")
            return redirect(_details_tab_url(account_id))
        repo.update_bank_account(account_id, data)
        if request.form.get("set_as_default"):
            repo.set_setting("default_bank_acc_id", str(account_id))
        flash_t("flash_bank_account_updated", "success")
        return redirect(_details_tab_url(account_id))
    bank_name = account.get("bank_name")
    return _render_hub(
        account,
        "details",
        cheque_setup=repo.get_account_cheque_setup(account_id, bank_name),
        **_bank_form_context(bank_name),
    )


@cash_flow_bp.route("/cash-flow/account/<int:account_id>/printer", methods=["GET"])
@login_required
def account_printer(account_id):
    account = repo.get_bank_account(account_id)
    if not account:
        return _missing_account()
    bank_name = account.get("bank_name")
    return _render_hub(
        account,
        "printer",
        printer_calibration=repo.get_account_printer_calibration(account_id, bank_name),
    )


@cash_flow_bp.route("/cash-flow/account/<int:account_id>/balance")
@login_required
def account_balance(account_id):
    account = repo.get_bank_account(account_id)
    if not account:
        return _missing_account()
    return _render_hub(account, "balance", **_load_balance_data(account_id))


@cash_flow_bp.route("/cash-flow/account/<int:account_id>/timetable")
@login_required
def account_timetable(account_id):
    account = repo.get_bank_account(account_id)
    if not account:
        return _missing_account()
    cheque_filter = repo.written_cheque_filters_from_args(request.args)
    written = repo.list_account_written_cheques(
        account_id, **repo.written_cheque_repo_kwargs(cheque_filter)
    )
    return _render_hub(
        account,
        "timetable",
        report=build_cash_flow_projection(account_id),
        written_cheques=written,
        cheque_filter=cheque_filter,
        list_summary=repo.list_amount_summary(written, "amount_in_numerals"),
    )


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
        if repo.get_bank_accounts():
            return redirect(url_for("cash_flow.new_account"))
        return redirect(url_for("cash_flow.cash_flow"))

    length_mm, width_mm = _cheque_setup_from_form(request.form)
    dim_err = repo.validate_cheque_dimensions(length_mm, width_mm)
    if dim_err:
        flash_t(dim_err, "error")
        if repo.get_bank_accounts():
            return redirect(url_for("cash_flow.new_account"))
        return redirect(url_for("cash_flow.cash_flow"))

    new_id = repo.create_bank_account(data)
    repo.save_account_cheque_setup(
        new_id,
        data["bank_name"],
        length_mm,
        width_mm,
        bank_code=data.get("bank_code"),
    )
    accounts_after = repo.get_bank_accounts()
    if request.form.get("set_as_default") or len(accounts_after) == 1:
        repo.set_setting("default_bank_acc_id", str(new_id))

    flash_t("flash_bank_account_created", "success")
    return redirect(_details_tab_url(new_id))


@cash_flow_bp.route("/cash-flow/accounts/<int:account_id>/edit", methods=["POST"])
@login_required
def edit_account(account_id):
    if not repo.get_bank_account(account_id):
        return _missing_account()

    data = _account_from_form(request.form)
    err = repo.validate_bank_account_input(data)
    if err:
        flash_t(err, "error")
        return redirect(_details_tab_url(account_id))

    dim_err = _save_cheque_setup(
        account_id, data["bank_name"], request.form, bank_code=data.get("bank_code")
    )
    if dim_err:
        flash_t(dim_err, "error")
        return redirect(_details_tab_url(account_id))

    repo.update_bank_account(account_id, data)
    if request.form.get("set_as_default"):
        repo.set_setting("default_bank_acc_id", str(account_id))
    flash_t("flash_bank_account_updated", "success")
    return redirect(_details_tab_url(account_id))


@cash_flow_bp.route("/cash-flow/accounts/<int:account_id>/set-default", methods=["POST"])
@login_required
def set_default_account(account_id):
    if not repo.get_bank_account(account_id):
        return _missing_account()
    repo.set_setting("default_bank_acc_id", str(account_id))
    flash_t("flash_bank_default_set", "success")
    return redirect(_details_tab_url(account_id))


@cash_flow_bp.route("/cash-flow/balance", methods=["POST"])
@login_required
def update_balance():
    acc_id = int(request.form["account_id"])
    if not repo.get_bank_account(acc_id):
        return _missing_account()
    balance = float(request.form["balance"])
    repo.update_balance(acc_id, balance)
    flash_t("flash_balance_updated", "success")
    return redirect(_balance_tab_url(acc_id))


@cash_flow_bp.route("/cash-flow/deposit", methods=["POST"])
@login_required
def record_deposit():
    acc_id = int(request.form["account_id"])
    if not repo.get_bank_account(acc_id):
        return _missing_account()
    try:
        amount = float(request.form.get("amount") or 0)
    except (TypeError, ValueError):
        amount = 0
    if amount <= 0:
        flash_t("flash_deposit_amount_invalid", "error")
        return redirect(_balance_tab_url(acc_id))
    deposit_date = (request.form.get("deposit_date") or date.today().isoformat()).strip()
    note = (request.form.get("reference") or request.form.get("notes") or "").strip()
    if not repo.record_deposit(acc_id, deposit_date, amount, note):
        return _missing_account()
    flash_t("flash_deposit_recorded", "success")
    return redirect(_balance_tab_url(acc_id))


@cash_flow_bp.route("/cash-flow/planned", methods=["POST"])
@login_required
def add_planned():
    acc_id = int(request.form["account_id"])
    if not repo.get_bank_account(acc_id):
        return _missing_account()
    repo.add_planned_deposit(
        acc_id,
        request.form["planned_date"],
        float(request.form["amount"]),
        request.form.get("notes", ""),
    )
    flash_t("flash_deposit_added", "success")
    return redirect(_balance_tab_url(acc_id))


@cash_flow_bp.route("/cash-flow/planned/<int:planned_id>/complete", methods=["POST"])
@login_required
def complete_planned(planned_id):
    planned = repo.complete_planned_deposit(planned_id)
    if planned:
        flash_t("flash_deposit_complete", "success")
        return redirect(_balance_tab_url(planned["user_bank_acc_id"]))
    flash_t("flash_deposit_not_found", "error")
    return redirect(url_for("cash_flow.cash_flow"))
