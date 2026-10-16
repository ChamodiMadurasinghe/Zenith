"""Simple UI (Figma "Simple version"). Thin routes; page data comes from core/views and core/ui."""

from datetime import date

from flask import Blueprint, render_template, request

from config import Config
from core.auth import login_required
from core.i18n import get_lang
from core.ui.format import initials, long_date
from core.ui.nav import nav_context
from db import repositories as repo

simple_bp = Blueprint("simple", __name__)


@simple_bp.context_processor
def inject_shell():
    """Data every simple page needs for the sidebar, top bar and mobile dock."""
    user = repo.get_user() or {}
    user_name = user.get("user_name") or ""
    return {
        "nav": nav_context(request.endpoint),
        "today_label": long_date(date.today(), get_lang()),
        "user_name": user_name,
        "user_initials": initials(user_name),
        "support_phone": Config.support_phone(),
    }


@simple_bp.route("/ui/preview")
@login_required
def preview():
    """Every simple-UI building block on one page, for checking against Figma."""
    return render_template("simple/preview.html")
