import markdown
from flask import Blueprint, render_template

from core.auth import login_required
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
    )
