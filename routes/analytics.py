import markdown
from flask import Blueprint, redirect, render_template, url_for

from agents.analyst import build_report_markdown
from config import Config
from core.auth import login_required
from core.i18n import flash_t, flash_user_error
from db import repositories as repo

analytics_bp = Blueprint("analytics", __name__)


@analytics_bp.route("/analytics")
@login_required
def analytics():
    report = repo.get_latest_analyst_report()
    html = ""
    if report:
        html = markdown.markdown(report["report_markdown"], extensions=["tables", "fenced_code"])
    metrics = repo.get_analytics_metrics()
    return render_template(
        "analytics.html",
        report_html=html,
        report=report,
        metrics=metrics,
        use_fake_ai=Config.use_fake_ai(),
        has_openai=bool(Config.openai_api_key()),
    )


@analytics_bp.route("/analytics/generate", methods=["POST"])
@login_required
def generate_analytics_report():
    if not Config.use_fake_ai() and not Config.openai_api_key():
        flash_t("flash_analytics_need_openai", "error")
        return redirect(url_for("analytics.analytics"))

    try:
        metrics = repo.get_analytics_metrics()
        report = build_report_markdown(metrics)
        repo.save_analyst_report(report)
        flash_t("flash_analytics_generated", "success")
    except Exception as exc:
        flash_user_error(exc, default_key="err_analytics_failed")

    return redirect(url_for("analytics.analytics"))
