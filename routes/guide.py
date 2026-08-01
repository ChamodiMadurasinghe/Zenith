from flask import Blueprint, current_app, jsonify, request, session

from config import Config
from core.auth import login_required
from core.guide_actions import (
    is_cheque_section,
    normalize_guide_actions,
    resolve_guide_actions,
)
from core.i18n import get_lang

guide_bp = Blueprint("guide", __name__)

HISTORY_LIMIT = 10


def _chat_error_hint(err: str) -> str:
    if "OPENAI_API_KEY not set" in err:
        return "Guide unavailable. Set OPENAI_API_KEY in .env and restart the app."
    if "401" in err or "invalid_api_key" in err.lower() or "incorrect api key" in err.lower():
        return "Invalid OpenAI API key. Replace OPENAI_API_KEY in .env and restart."
    if "429" in err or "rate_limit" in err.lower() or "ResourceExhausted" in err:
        return "Rate limit exceeded. Try USE_FAKE_AI=true for UI testing, or reset the guide chat."
    return f"Guide unavailable: {err[:200]}"


def _get_history() -> list:
    return list(session.get("guide_chat_history") or [])


def _save_history(history: list) -> None:
    session["guide_chat_history"] = history[-HISTORY_LIMIT:]


def _finalize_actions(page_path: str, raw_actions: list) -> list:
    if is_cheque_section(page_path):
        return []
    normalized = normalize_guide_actions(raw_actions)
    return resolve_guide_actions(normalized)


@guide_bp.route("/api/guide/health", methods=["GET"])
@login_required
def guide_health():
    return jsonify({"ok": True, "demo_mode": Config.use_fake_ai()})


@guide_bp.route("/api/guide/chat", methods=["POST"])
@login_required
def guide_chat_route():
    try:
        data = request.get_json(silent=True) or {}
        message = (data.get("message") or "").strip()
        page_path = (data.get("page_path") or "/").strip() or "/"

        if not message:
            return jsonify({"error": "empty_message", "reply": "Please enter a message.", "actions": []}), 400

        current_app.logger.info("guide POST path=%s message=%r", page_path, message[:80])
        history = _get_history()
        lang = get_lang()

        try:
            if Config.use_fake_ai():
                from agents.mock import mock_guide_chat

                result = mock_guide_chat(message, page_path, history, lang)
            else:
                from agents.guide import guide_chat

                result = guide_chat(message, history, page_path, lang)
        except Exception as e:
            err = str(e)
            return jsonify({"error": err, "reply": _chat_error_hint(err), "actions": []}), 500

        reply = (result.get("reply") or "").strip()
        actions = _finalize_actions(page_path, result.get("guide_actions") or [])

        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": reply})
        _save_history(history)

        return jsonify({"reply": reply, "actions": actions})
    except Exception as e:
        err = str(e)
        return jsonify({"error": err, "reply": _chat_error_hint(err), "actions": []}), 500


@guide_bp.route("/api/guide/chat/reset", methods=["POST"])
@login_required
def reset_guide_chat():
    session.pop("guide_chat_history", None)
    return jsonify({"ok": True})
