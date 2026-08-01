import os

from flask import Flask

from config import Config
from core.app_guide import guide_welcome_for_path
from core.alert_scheduler import start_alert_scheduler
from core.i18n import SUPPORTED_LANGS, get_lang, js_translations, speech_lang_code, t
from routes.analytics import analytics_bp
from routes.auth import auth_bp
from routes.bundling import bundling_bp
from routes.cash_flow import cash_flow_bp
from routes.guide import guide_bp
from routes.i18n import i18n_bp
from routes.dealers import dealers_bp
from routes.ingestion import ingestion_bp
from routes.orchestration import orchestration_bp
from whatsapp_agent import WHATSAPP_INTAKE_VERSION, whatsapp_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    Config.UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

    app.register_blueprint(auth_bp)
    app.register_blueprint(i18n_bp)
    app.register_blueprint(ingestion_bp)
    app.register_blueprint(cash_flow_bp)
    app.register_blueprint(bundling_bp)
    app.register_blueprint(dealers_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(guide_bp)
    app.register_blueprint(orchestration_bp)
    app.register_blueprint(whatsapp_bp)

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

    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        start_alert_scheduler(app)

    print(
        f"[zenith] WhatsApp intake mode: {WHATSAPP_INTAKE_VERSION} (no Gemini on receive)",
        flush=True,
    )

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
