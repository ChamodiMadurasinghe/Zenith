import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
_ENV_PATH = BASE_DIR / ".env"
load_dotenv(_ENV_PATH)


def _env(key: str, default: str = "") -> str:
    """Read env var, reloading .env so running server picks up changes."""
    load_dotenv(_ENV_PATH, override=True)
    return os.getenv(key, default)


def _env_bool(key: str, default: bool = False) -> bool:
    val = _env(key, "true" if default else "false").strip().lower()
    return val in ("1", "true", "yes", "on")


class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")
    DATABASE_PATH = BASE_DIR / os.getenv("DATABASE_PATH", "database/invoice_cheque.db")
    UPLOAD_FOLDER = BASE_DIR / os.getenv("UPLOAD_FOLDER", "storage/invoices")
    MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "10"))

    @staticmethod
    def gemini_api_key() -> str:
        return _env("GEMINI_API_KEY", "")

    @staticmethod
    def gemini_vision_model() -> str:
        return _env("GEMINI_VISION_MODEL", _env("GEMINI_MODEL", "gemini-2.0-flash"))

    @staticmethod
    def gemini_text_model() -> str:
        """Text/JSON model for Agents 2–3 conditional AI calls."""
        return _env("GEMINI_TEXT_MODEL", Config.gemini_vision_model())

    @staticmethod
    def agent_conditional_ai() -> bool:
        """When true, Agents 2–3 call Gemini only if triggers fire (see agent_ai.py)."""
        return _env_bool("AGENT_CONDITIONAL_AI", True)

    @staticmethod
    def gemini_model() -> str:
        """Backward compatibility — maps to vision model."""
        return Config.gemini_vision_model()

    @staticmethod
    def openai_api_key() -> str:
        return _env("OPENAI_API_KEY", "")

    @staticmethod
    def openai_chat_model() -> str:
        return _env("OPENAI_CHAT_MODEL", "gpt-3.5-turbo")

    @staticmethod
    def openai_analyst_model() -> str:
        return _env("OPENAI_ANALYST_MODEL", "gpt-3.5-turbo")

    @staticmethod
    def use_fake_ai() -> bool:
        return _env_bool("USE_FAKE_AI", False)

    @staticmethod
    def twilio_account_sid() -> str:
        return _env("TWILIO_ACCOUNT_SID", "")

    @staticmethod
    def twilio_auth_token() -> str:
        return _env("TWILIO_AUTH_TOKEN", "")

    @staticmethod
    def twilio_whatsapp_from() -> str:
        return _env("TWILIO_WHATSAPP_FROM", "")

    @staticmethod
    def whatsapp_allowed_numbers() -> list[str]:
        raw = _env("WHATSAPP_ALLOWED_NUMBERS", "").strip()
        if not raw:
            return []
        return [n.strip() for n in raw.split(",") if n.strip()]

    @staticmethod
    def use_twilio_mock() -> bool:
        return _env_bool("USE_TWILIO_MOCK", True)

    @staticmethod
    def use_agentic_orchestrator() -> bool:
        """Route WhatsApp intake through agentic PER pipeline (handle_event)."""
        return _env_bool("USE_AGENTIC_ORCHESTRATOR", False)

    @staticmethod
    def mock_image_path() -> str:
        return _env("MOCK_IMAGE_PATH", "")

    @staticmethod
    def merchant_whatsapp_phone() -> str:
        return _env("MERCHANT_WHATSAPP_PHONE", "")

    @staticmethod
    def cash_alert_days_ahead() -> int:
        try:
            return int(_env("CASH_ALERT_DAYS_AHEAD", "3"))
        except ValueError:
            return 3

    @staticmethod
    def enable_cash_alerts() -> bool:
        return _env_bool("ENABLE_CASH_ALERTS", False)

    APP_PASSWORD = os.getenv("APP_PASSWORD", "change-me-on-first-setup")
    DEFAULT_CREDIT_PERIOD_DAYS = int(os.getenv("DEFAULT_CREDIT_PERIOD_DAYS", "30"))
    MIN_CASH_BUFFER_LKR = float(os.getenv("MIN_CASH_BUFFER_LKR", "500000"))
    # Zenith-1 casual daily cheque allocation ceiling (agent day-limit audit)
    CASUAL_DAILY_LIMIT_LKR = float(os.getenv("CASUAL_DAILY_LIMIT_LKR", "1000000"))
    USER_ID = 1
