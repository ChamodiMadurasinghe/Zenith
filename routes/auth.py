from flask import Blueprint, redirect, render_template, request, session, url_for

from core.auth import login_required, verify_password
from core.i18n import flash_t

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("ingestion.dashboard"))
    if request.method == "POST":
        password = request.form.get("password", "")
        if verify_password(password):
            session["user_id"] = 1
            return redirect(url_for("ingestion.dashboard"))
        flash_t("flash_incorrect_password", "error")
    return render_template("login.html")


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
