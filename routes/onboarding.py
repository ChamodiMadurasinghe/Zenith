"""First-run setup. Every integration step can be skipped."""

from __future__ import annotations

from pathlib import Path

import markdown
from flask import Blueprint, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from config import BASE_DIR, Config
from core.auth import login_required
from core.env_store import update_keys
from core.i18n import flash_t
from db import repositories as repo
from db.connection import execute

onboarding_bp = Blueprint("onboarding", __name__)

STATUS_KEY = "onboarding_status"
STEPS = ("welcome", "password", "gemini", "openai", "whatsapp", "backup", "done")


def onboarding_status() -> str:
    try:
        return repo.get_setting(STATUS_KEY, "")
    except Exception:
        return ""


def onboarding_blocks_app() -> bool:
    """True when a logged-in desktop shop still needs the first-run wizard."""
    if not Config.show_onboarding():
        return False
    return onboarding_status() in ("pending", "in_progress")


def _step_from_request() -> str:
    raw = (request.values.get("step") or "welcome").strip()
    return raw if raw in STEPS else "welcome"


def _next_step(step: str) -> str:
    index = STEPS.index(step)
    if index >= len(STEPS) - 1:
        return "done"
    return STEPS[index + 1]


def _setup_url(step: str, review: bool):
    if review:
        return url_for("onboarding.setup", step=step, review=1)
    return url_for("onboarding.setup", step=step)


def _mark(status: str) -> None:
    repo.set_setting(STATUS_KEY, status)


def _set_password(password: str) -> None:
    update_keys({"APP_PASSWORD": password})
    execute(
        "UPDATE user SET password_hash = ? WHERE user_id = ?",
        (generate_password_hash(password), Config.USER_ID),
    )


def _save_creds_upload(upload) -> None:
    if upload is None or not getattr(upload, "filename", ""):
        return
    dest = Path(Config.gdrive_credentials_path())
    dest.parent.mkdir(parents=True, exist_ok=True)
    upload.save(dest)


def _apply_step(step: str, action: str) -> str | None:
    """Apply the posted step. Return an error i18n key, or None on success."""
    if step == "password" and action == "continue":
        password = request.form.get("password", "")
        confirm = request.form.get("password_confirm", "")
        if not password and not confirm:
            return None
        if len(password) < 4 or password != confirm:
            return "onboarding_password_mismatch"
        _set_password(password)
        return None
    if step == "gemini":
        key = request.form.get("gemini_api_key", "").strip()
        if action == "continue" and key:
            update_keys({"GEMINI_API_KEY": key, "USE_FAKE_AI": "false"})
        else:
            update_keys({"USE_FAKE_AI": "true"})
        return None
    if step == "openai" and action == "continue":
        key = request.form.get("openai_api_key", "").strip()
        if key:
            update_keys({"OPENAI_API_KEY": key})
        return None
    if step == "backup" and action == "continue":
        passphrase = request.form.get("backup_passphrase", "").strip()
        if passphrase:
            update_keys({"BACKUP_PASSPHRASE": passphrase})
        _save_creds_upload(request.files.get("creds_file"))
    return None


@onboarding_bp.route("/setup", methods=["GET", "POST"])
@login_required
def setup():
    review = request.values.get("review") == "1"
    if request.method == "GET" and onboarding_status() == "pending":
        _mark("in_progress")

    step = _step_from_request()
    if request.method == "GET" and step == "done":
        _mark("completed")
    if request.method == "POST":
        action = (request.form.get("action") or "continue").strip()
        if action == "skip_all":
            _mark("skipped")
            return redirect(url_for("ingestion.dashboard"))
        if step == "done" and action == "continue":
            _mark("completed")
            return redirect(url_for("ingestion.dashboard"))
        error = _apply_step(step, action)
        if error:
            flash_t(error, "error")
            return redirect(_setup_url(step, review))
        return redirect(_setup_url(_next_step(step), review))

    return render_template(
        "onboarding/setup.html",
        step=step,
        step_index=STEPS.index(step) + 1,
        step_count=len(STEPS),
        review=review,
    )


@onboarding_bp.get("/help/setup")
def help_setup():
    doc = BASE_DIR / "docs" / "SETUP_GUIDES.md"
    text = doc.read_text(encoding="utf-8") if doc.exists() else ""
    html = markdown.markdown(text, extensions=["extra"])
    return render_template("onboarding/help.html", body_html=html)
