import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
_ENV_PATH = BASE_DIR / ".env"
load_dotenv(_ENV_PATH)


def _data_path(env_key: str, default: str) -> Path:
    """Relative paths stay under the project; absolute paths (PaaS disks) are used as-is."""
    raw = os.getenv(env_key, default).strip() or default
    path = Path(raw)
    return path if path.is_absolute() else BASE_DIR / path


def _env(key: str, default: str = "") -> str:
    """Read env var, reloading .env so running server picks up changes."""
    load_dotenv(_ENV_PATH, override=True)
    return os.getenv(key, default)


def _env_bool(key: str, default: bool = False) -> bool:
    val = _env(key, "true" if default else "false").strip().lower()
    return val in ("1", "true", "yes", "on")


class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")
    DATABASE_PATH = _data_path("DATABASE_PATH", "database/invoice_cheque.db")
    UPLOAD_FOLDER = _data_path("UPLOAD_FOLDER", "storage/invoices")
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

    # Only these OpenAI models are allowed for this project (Gemini is separate).
    OPENAI_ALLOWED_MODELS = frozenset({"gpt-5.6-luna", "gpt-5.6-sol"})

    @staticmethod
    def resolve_openai_model(model: str | None, default: str = "gpt-5.6-luna") -> str:
        """Clamp any OpenAI model id to the allowed set; unknown → default."""
        name = (model or default).strip()
        if name not in Config.OPENAI_ALLOWED_MODELS:
            return default if default in Config.OPENAI_ALLOWED_MODELS else "gpt-5.6-luna"
        return name

    @staticmethod
    def _openai_model(env_key: str, default: str) -> str:
        return Config.resolve_openai_model(_env(env_key, default), default)

    @staticmethod
    def openai_chat_model() -> str:
        return Config._openai_model("OPENAI_CHAT_MODEL", "gpt-5.6-luna")

    @staticmethod
    def openai_analyst_model() -> str:
        return Config._openai_model("OPENAI_ANALYST_MODEL", "gpt-5.6-sol")

    @staticmethod
    def use_fake_ai() -> bool:
        return _env_bool("USE_FAKE_AI", False)

    @staticmethod
    def whatsapp_provider() -> str:
        """meta (default) | twilio — WhatsApp channel backend."""
        raw = _env("WHATSAPP_PROVIDER", "meta").strip().lower()
        return raw if raw in ("meta", "twilio") else "meta"

    @staticmethod
    def meta_whatsapp_token() -> str:
        return _env("META_WHATSAPP_TOKEN", _env("WHATSAPP_TOKEN", ""))

    @staticmethod
    def meta_phone_number_id() -> str:
        return _env("META_PHONE_NUMBER_ID", _env("WHATSAPP_PHONE_NUMBER_ID", ""))

    @staticmethod
    def meta_verify_token() -> str:
        return _env("META_VERIFY_TOKEN", "zenith-meta-verify")

    @staticmethod
    def meta_app_secret() -> str:
        """Optional: validates X-Hub-Signature-256 on inbound webhooks."""
        return _env("META_APP_SECRET", "")

    @staticmethod
    def meta_graph_version() -> str:
        return _env("META_GRAPH_VERSION", "v21.0")

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
    def use_whatsapp_mock() -> bool:
        if _env("USE_WHATSAPP_MOCK", ""):
            return _env_bool("USE_WHATSAPP_MOCK", True)
        return _env_bool("USE_TWILIO_MOCK", False)

    @staticmethod
    def use_twilio_mock() -> bool:
        return Config.use_whatsapp_mock()

    @staticmethod
    def mock_image_path() -> str:
        return _env("MOCK_IMAGE_PATH", "")

    @staticmethod
    def webhook_public_url() -> str:
        return _env("WEBHOOK_PUBLIC_URL", "http://127.0.0.1:5000").rstrip("/")

    @staticmethod
    def host() -> str:
        if _env("FLASK_ENV", "development").strip().lower() == "production":
            return _env("HOST", "0.0.0.0")
        return _env("HOST", "127.0.0.1")

    @staticmethod
    def port() -> int:
        try:
            return int(_env("PORT", "5000"))
        except ValueError:
            return 5000

    @staticmethod
    def inbound_queue_dir() -> Path:
        return _data_path("INBOUND_QUEUE_DIR", "data/inbound_queue")

    @staticmethod
    def whatsapp_bridge_secret() -> str:
        return _env("WHATSAPP_BRIDGE_SECRET", "")

    @staticmethod
    def whatsapp_bridge_url() -> str:
        return _env("WHATSAPP_BRIDGE_URL", "http://127.0.0.1:3001")

    @staticmethod
    def zenith_ingest_url() -> str:
        return _env(
            "ZENITH_INGEST_URL",
            f"http://{Config.host()}:{Config.port()}/api/invoices/ingest",
        )

    @staticmethod
    def use_agentic_orchestrator() -> bool:
        """Route WhatsApp intake through agentic PER pipeline (handle_event)."""
        return _env_bool("USE_AGENTIC_ORCHESTRATOR", False)

    @staticmethod
    def use_bundling_tool_agent() -> bool:
        """Use LangChain tool-calling Bundling Assistant (fallback: JSON proposed_actions)."""
        return _env_bool("USE_BUNDLING_TOOL_AGENT", True)

    @staticmethod
    def use_strategist_tool_agent() -> bool:
        """Agent 3: Gemini tool-calling over bundling.py + guardrails."""
        return _env_bool("USE_STRATEGIST_TOOL_AGENT", True)

    @staticmethod
    def enable_vector_patterns() -> bool:
        return _env_bool("ENABLE_VECTOR_PATTERNS", True)

    @staticmethod
    def chroma_persist_dir() -> str:
        return _env("CHROMA_PERSIST_DIR", "database/chroma")

    @staticmethod
    def openai_embedding_model() -> str:
        return _env("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

    @staticmethod
    def pattern_large_bill_lkr() -> float:
        try:
            return float(_env("PATTERN_LARGE_BILL_LKR", "500000"))
        except ValueError:
            return 500_000.0

    @staticmethod
    def merchant_whatsapp_phone() -> str:
        from db import repositories as repo

        return repo.get_merchant_whatsapp_phone()

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
