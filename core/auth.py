from functools import wraps
import secrets

from flask import jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash

from config import Config, _env
from db.connection import query_one


def verify_password(password: str) -> bool:
    """Accept APP_PASSWORD from .env, with optional SQLite password_hash fallback."""
    if not password:
        return False

    expected = _env("APP_PASSWORD", Config.APP_PASSWORD or "")
    if expected and secrets.compare_digest(password, expected):
        return True

    try:
        user = query_one("SELECT password_hash FROM user WHERE user_id = 1")
    except Exception:
        return False
    if not user or not user.get("password_hash"):
        return False
    return check_password_hash(user["password_hash"], password)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            if request.path.startswith("/api/") or request.is_json:
                return jsonify({"error": "unauthorized", "reply": "Session expired. Please log in again."}), 401
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)

    return decorated
