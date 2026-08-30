from datetime import date

from flask import Blueprint, Response, jsonify, request

from core.auth import login_required
from core.cheque_printer import generate_cheque_pdf
from core.cheque_utils import resolve_bank_code
from db import repositories as repo

cheque_print_bp = Blueprint("cheque_print", __name__)


def _merge_template_and_settings(template: dict, printer_settings: dict) -> dict:
    merged = dict(template)
    if printer_settings.get("cheque_width_mm") is not None:
        merged["cheque_width_mm"] = printer_settings["cheque_width_mm"]
    if printer_settings.get("cheque_height_mm") is not None:
        merged["cheque_height_mm"] = printer_settings["cheque_height_mm"]
    return merged


def _printer_settings_for_account(
    user_bank_acc_id: int,
    bank_code: str,
    *,
    offset_x_mm: float | None = None,
    offset_y_mm: float | None = None,
    feed_orientation: str | None = None,
) -> dict:
    settings = dict(repo.get_printer_settings(user_bank_acc_id, bank_code))
    if offset_x_mm is not None:
        settings["offset_x_mm"] = float(offset_x_mm)
    if offset_y_mm is not None:
        settings["offset_y_mm"] = float(offset_y_mm)
    if feed_orientation is not None:
        settings["feed_orientation"] = str(feed_orientation).upper()
    return settings


def _generate_pdf_for_account(
    user_bank_acc_id: int,
    *,
    payee_name: str,
    amount: float,
    date_str: str,
    offset_x_mm: float | None = None,
    offset_y_mm: float | None = None,
    feed_orientation: str | None = None,
    crossing: bool = True,
) -> tuple[bytes, str] | tuple[None, dict, int]:
    account = repo.get_bank_account(user_bank_acc_id)
    if not account:
        return None, {"error": "account_not_found"}, 404

    bank_code = resolve_bank_code(account.get("bank_name"))
    if not bank_code:
        return None, {"error": "unsupported_bank", "bank_name": account.get("bank_name")}, 400

    template = repo.get_bank_cheque_template(bank_code)
    if not template:
        return None, {"error": "template_not_found", "bank_code": bank_code}, 404

    printer_settings = _printer_settings_for_account(
        user_bank_acc_id,
        bank_code,
        offset_x_mm=offset_x_mm,
        offset_y_mm=offset_y_mm,
        feed_orientation=feed_orientation,
    )
    bank_template = _merge_template_and_settings(dict(template), printer_settings)
    pdf_bytes = generate_cheque_pdf(
        date_str=date_str,
        payee_name=payee_name,
        amount=amount,
        bank_template=bank_template,
        printer_settings=printer_settings,
        crossing=crossing,
    )
    return pdf_bytes, bank_code


@cheque_print_bp.route("/api/cheque/print", methods=["POST"])
@login_required
def print_cheque():
    data = request.get_json(silent=True) or {}

    try:
        user_bank_acc_id = int(data.get("user_bank_acc_id") or 0)
    except (TypeError, ValueError):
        user_bank_acc_id = 0
    if not user_bank_acc_id:
        return jsonify({"error": "user_bank_acc_id_required"}), 400

    payee_name = (data.get("payee_name") or "").strip()
    if not payee_name:
        return jsonify({"error": "payee_name_required"}), 400

    try:
        amount = float(data.get("amount"))
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_amount"}), 400
    if amount < 0:
        return jsonify({"error": "invalid_amount"}), 400

    date_str = (data.get("date_str") or "").strip()
    if not date_str:
        return jsonify({"error": "date_str_required"}), 400

    crossing = data.get("crossing", True)
    if isinstance(crossing, str):
        crossing = crossing.lower() not in ("0", "false", "no")

    result = _generate_pdf_for_account(
        user_bank_acc_id,
        payee_name=payee_name,
        amount=amount,
        date_str=date_str,
        crossing=bool(crossing),
    )
    if result[0] is None:
        return jsonify(result[1]), result[2]

    pdf_bytes, bank_code = result
    filename = f"cheque-{bank_code.lower()}.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@cheque_print_bp.route("/api/cheque/print-test", methods=["POST"])
@login_required
def print_test_cheque():
    data = request.get_json(silent=True) or {}

    try:
        user_bank_acc_id = int(data.get("user_bank_acc_id") or 0)
    except (TypeError, ValueError):
        user_bank_acc_id = 0
    if not user_bank_acc_id:
        return jsonify({"error": "user_bank_acc_id_required"}), 400

    offset_x = data.get("offset_x_mm")
    offset_y = data.get("offset_y_mm")
    feed_orientation = data.get("feed_orientation")

    if offset_x is not None or offset_y is not None:
        err = repo.validate_printer_offsets(
            float(offset_x or 0),
            float(offset_y or 0),
        )
        if err:
            return jsonify({"error": err}), 400

    result = _generate_pdf_for_account(
        user_bank_acc_id,
        payee_name="TEST PAYEE",
        amount=1234.56,
        date_str=date.today().isoformat(),
        offset_x_mm=float(offset_x) if offset_x is not None else None,
        offset_y_mm=float(offset_y) if offset_y is not None else None,
        feed_orientation=feed_orientation,
        crossing=True,
    )
    if result[0] is None:
        return jsonify(result[1]), result[2]

    pdf_bytes, bank_code = result
    filename = f"cheque-test-{bank_code.lower()}.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@cheque_print_bp.route("/api/cheque/calibration", methods=["POST"])
@login_required
def save_calibration():
    data = request.get_json(silent=True) or {}

    try:
        user_bank_acc_id = int(data.get("user_bank_acc_id") or 0)
    except (TypeError, ValueError):
        user_bank_acc_id = 0
    if not user_bank_acc_id:
        return jsonify({"error": "user_bank_acc_id_required"}), 400

    account = repo.get_bank_account(user_bank_acc_id)
    if not account:
        return jsonify({"error": "account_not_found"}), 404

    bank_code = resolve_bank_code(account.get("bank_name"))
    if not bank_code:
        return jsonify({"error": "unsupported_bank"}), 400

    try:
        offset_x = float(data.get("offset_x_mm", 0))
        offset_y = float(data.get("offset_y_mm", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "flash_printer_offsets_invalid"}), 400

    feed_orientation = str(data.get("feed_orientation") or "VERTICAL").upper()
    if feed_orientation not in ("VERTICAL", "HORIZONTAL"):
        feed_orientation = "VERTICAL"

    err = repo.save_account_printer_calibration(
        user_bank_acc_id,
        bank_code,
        offset_x,
        offset_y,
        feed_orientation,
    )
    if err:
        return jsonify({"error": err}), 400

    return jsonify(
        {
            "ok": True,
            "offset_x_mm": offset_x,
            "offset_y_mm": offset_y,
            "feed_orientation": feed_orientation,
        }
    )
