import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
_ENV_PATH = BASE_DIR / ".env"
load_dotenv(_ENV_PATH)

# Desktop installs keep customer data outside the code folder so updates can
# replace the app without touching the database, photos, or secrets.
_DESKTOP_RELATIVE = {
    "DATABASE_PATH": "invoice_cheque.db",
    "UPLOAD_FOLDER": "invoices",
    "INBOUND_QUEUE_DIR": "inbound_queue",
    "CHROMA_PERSIST_DIR": "chroma",
    "GDRIVE_CREDS_PATH": "mycreds.txt",
}


def _flag_value(raw: str) -> bool:
    return raw.strip().lower() in ("1", "true", "yes", "on")


def is_desktop_mode() -> bool:
    return _flag_value(os.getenv("ZENITH_DESKTOP", ""))


def desktop_data_dir() -> Path | None:
    """%LOCALAPPDATA%\\Zenith when ZENITH_DESKTOP is on; otherwise None."""
    if not is_desktop_mode():
        return None
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    path = Path(local) / "Zenith"
    path.mkdir(parents=True, exist_ok=True)
    return path


def secrets_env_path() -> Path:
    """Where the setup wizard writes API keys and the app password."""
    desktop = desktop_data_dir()
    if desktop is not None:
        return desktop / ".env"
    return _ENV_PATH


def _reload_env() -> None:
    load_dotenv(_ENV_PATH, override=True)
    desktop_env = desktop_data_dir()
    if desktop_env is not None:
        load_dotenv(desktop_env / ".env", override=True)


if desktop_data_dir() is not None:
    load_dotenv(desktop_data_dir() / ".env", override=True)


def resolve_storage_path(env_key: str, default: str) -> Path:
    """Project-relative by default. Desktop mode uses AppData unless the path is absolute."""
    desktop = desktop_data_dir()
    raw = os.getenv(env_key, "").strip()
    if desktop is not None and env_key in _DESKTOP_RELATIVE:
        if raw:
            candidate = Path(raw)
            if candidate.is_absolute():
                return candidate
        return desktop / _DESKTOP_RELATIVE[env_key]
    raw = raw or default
    path = Path(raw)
    return path if path.is_absolute() else BASE_DIR / path


def _data_path(env_key: str, default: str) -> Path:
    """Relative paths stay under the project; absolute paths (PaaS disks) are used as-is."""
    return resolve_storage_path(env_key, default)


def _env(key: str, default: str = "") -> str:
    """Read env var, reloading .env so running server picks up changes."""
    _reload_env()
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
    def location_path_for(filename: str) -> str:
        """Path stored in DB for an upload. Relative under the project; absolute on PaaS disks."""
        name = Path(filename).name
        try:
            upload_rel = Config.UPLOAD_FOLDER.relative_to(BASE_DIR).as_posix()
            return f"{upload_rel}/{name}"
        except ValueError:
            return f"{Config.UPLOAD_FOLDER.resolve().as_posix().rstrip('/')}/{name}"

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
    def meta_phone_pin() -> str:
        """6-digit WhatsApp two-step PIN for Cloud API phone /register (ops only)."""
        return _env("META_PHONE_PIN", "").strip()

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
        return str(_data_path("CHROMA_PERSIST_DIR", "database/chroma"))

    @staticmethod
    def backup_passphrase() -> str:
        """User-supplied or env backup passphrase. Never hardcode a production secret."""
        return _env("BACKUP_PASSPHRASE", "") or _env("ZENITH_BACKUP_PASSPHRASE", "")

    @staticmethod
    def gdrive_credentials_path() -> Path:
        return _data_path("GDRIVE_CREDS_PATH", "mycreds.txt")

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

    @staticmethod
    def ui_mode() -> str:
        """Which UI the home page and login land on: "classic" or "simple"."""
        mode = _env("UI_MODE", "classic").lower()
        return mode if mode in ("classic", "simple") else "classic"

    @staticmethod
    def support_phone() -> str:
        return _env("SUPPORT_PHONE", "011 234 5678")

    @staticmethod
    def app_version() -> str:
        version_file = BASE_DIR / "VERSION"
        try:
            text = version_file.read_text(encoding="utf-8").strip()
        except OSError:
            return "0.0.0"
        return text or "0.0.0"

    @staticmethod
    def use_production_init() -> bool:
        """Fresh databases for desktop customers skip demo dealers and sample invoices."""
        if _env_bool("ZENITH_PRODUCTION_INIT", False):
            return True
        return is_desktop_mode()

    @staticmethod
    def show_onboarding() -> bool:
        """First-run wizard. Off on the Render team preview unless explicitly enabled."""
        raw = _env("ZENITH_SHOW_ONBOARDING", "").strip()
        if raw:
            return _flag_value(raw)
        return is_desktop_mode()

    @staticmethod
    def github_repo() -> str:
        return _env("GITHUB_REPO", "ChamodiMadurasinghe/Zenith").strip().strip("/")

    @staticmethod
    def auto_update_check_enabled() -> bool:
        raw = _env("AUTO_UPDATE_CHECK", "").strip()
        if raw:
            return _flag_value(raw)
        return is_desktop_mode()

    @staticmethod
    def update_check_hour() -> int:
        try:
            hour = int(_env("UPDATE_CHECK_HOUR", "2"))
        except ValueError:
            return 2
        return hour if 0 <= hour <= 23 else 2

    APP_PASSWORD = os.getenv("APP_PASSWORD", "change-me-on-first-setup")
    DEFAULT_CREDIT_PERIOD_DAYS = int(os.getenv("DEFAULT_CREDIT_PERIOD_DAYS", "30"))
    MIN_CASH_BUFFER_LKR = float(os.getenv("MIN_CASH_BUFFER_LKR", "500000"))
    # Zenith-1 casual daily cheque allocation ceiling (agent day-limit audit)
    CASUAL_DAILY_LIMIT_LKR = float(os.getenv("CASUAL_DAILY_LIMIT_LKR", "1000000"))
    USER_ID = 1
