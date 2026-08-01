from flask import Blueprint, redirect, request, session, url_for

from core.i18n import SUPPORTED_LANGS

i18n_bp = Blueprint("i18n", __name__)


@i18n_bp.route("/language/<lang_code>")
def set_language(lang_code: str):
    if lang_code in SUPPORTED_LANGS:
        session["lang"] = lang_code
    referrer = request.referrer
    if referrer and referrer.startswith(request.host_url.rstrip("/")):
        return redirect(referrer)
    return redirect(url_for("ingestion.dashboard"))
