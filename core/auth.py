from functools import wraps

from flask import jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash

from db.connection import query_one


def verify_password(password: str) -> bool:
    user = query_one("SELECT password_hash FROM user WHERE user_id = 1")
    if not user:
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
