"""Public legal pages for Meta App Review (no login required)."""

from __future__ import annotations

import os

from flask import Blueprint, render_template

legal_bp = Blueprint("legal", __name__)


def _legal_context() -> dict:
    return {
        "contact_email": (
            os.getenv("LEGAL_CONTACT_EMAIL") or "yohanruchitha2@gmail.com"
        ).strip(),
        "app_name": "Zenith",
        "site_host": "zenith-ccg1.onrender.com",
    }


@legal_bp.route("/privacy")
def privacy():
    return render_template("privacy.html", **_legal_context())


@legal_bp.route("/terms")
def terms():
    return render_template("terms.html", **_legal_context())


@legal_bp.route("/data-deletion")
def data_deletion():
    return render_template("data_deletion.html", **_legal_context())
