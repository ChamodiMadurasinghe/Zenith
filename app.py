import os
from pathlib import Path

from flask import Flask

from config import Config
from core.app_guide import guide_welcome_for_path
from core.alert_scheduler import start_alert_scheduler
from core.i18n import SUPPORTED_LANGS, get_lang, js_translations, speech_lang_code, t
from routes.analytics import analytics_bp
from routes.auth import auth_bp
from routes.bundling import bundling_bp
from routes.cash_flow import cash_flow_bp
from routes.cheque_print import cheque_print_bp
from routes.guide import guide_bp
from routes.i18n import i18n_bp
from routes.dealers import dealers_bp
from routes.ingestion import ingestion_bp
from routes.orchestration import orchestration_bp
from routes.legal import legal_bp
from routes.whatsapp_settings import whatsapp_settings_bp
from whatsapp_agent import whatsapp_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    Config.UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    Config.inbound_queue_dir().mkdir(parents=True, exist_ok=True)

    app.register_blueprint(auth_bp)
    app.register_blueprint(i18n_bp)
    app.register_blueprint(ingestion_bp)
    app.register_blueprint(cash_flow_bp)
    app.register_blueprint(bundling_bp)
    app.register_blueprint(cheque_print_bp)
    app.register_blueprint(dealers_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(guide_bp)
    app.register_blueprint(orchestration_bp)
    app.register_blueprint(whatsapp_settings_bp)
    app.register_blueprint(whatsapp_bp)
    app.register_blueprint(legal_bp)

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.context_processor
    def inject_i18n():
        lang = get_lang()
        return {
            "t": t,
            "current_lang": lang,
            "supported_langs": SUPPORTED_LANGS,
            "js_i18n": js_translations(lang),
            "speech_lang": speech_lang_code(lang),
            "guide_welcome_tip": guide_welcome_for_path,
        }

    db_path = Path(Config.DATABASE_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if not db_path.exists():
        from scripts.init_db import init_db

        init_db(force_recreate=True)

    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        start_alert_scheduler(app)

    print(
        f"[zenith] data: db={Config.DATABASE_PATH} uploads={Config.UPLOAD_FOLDER}",
        flush=True,
    )
    print(
        f"[zenith] WhatsApp: {Config.whatsapp_provider()} webhook (/webhook/whatsapp)",
        flush=True,
    )

    return app


app = create_app()

if __name__ == "__main__":
    debug = os.getenv("FLASK_ENV", "development").strip().lower() != "production"
    app.run(debug=debug, host=Config.host(), port=Config.port())
