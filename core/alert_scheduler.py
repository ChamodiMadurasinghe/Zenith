from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from config import Config
from core.cash_flow import build_cash_flow_projection
from core.twilio_client import send_whatsapp_message
from db import repositories as repo

_scheduler: BackgroundScheduler | None = None


def check_upcoming_funding_gaps(days_ahead: int) -> list[dict]:
    rows = []
    for account_id in repo.get_all_account_ids():
        report = build_cash_flow_projection(account_id, horizon_days=max(30, days_ahead + 7))
        for alert in report.alerts:
            rows.append(
                {
                    "account_id": account_id,
                    "deposit_by_date": alert.deposit_by_date,
                    "amount_needed": alert.amount_needed,
                    "reason": alert.reason,
                }
            )
    return rows


def format_alert_message(alerts: list[dict]) -> str:
    if not alerts:
        return ""
    lines = ["Zenith cash-flow alert:"]
    for a in alerts[:5]:
        lines.append(
            f"- Account {a['account_id']}: deposit LKR {a['amount_needed']:,.2f} by {a['deposit_by_date']} ({a['reason']})"
        )
    return "\n".join(lines)


def run_daily_alerts():
    if not Config.enable_cash_alerts():
        return
    phone = Config.merchant_whatsapp_phone()
    if not phone:
        return
    alerts = check_upcoming_funding_gaps(Config.cash_alert_days_ahead())
    if not alerts:
        return
    message = format_alert_message(alerts)
    send_whatsapp_message(phone, message)
    repo.save_alert_log("whatsapp", phone, message)


def start_alert_scheduler(app):
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = BackgroundScheduler(timezone="Asia/Colombo")
    _scheduler.add_job(run_daily_alerts, "cron", hour=8, minute=0, id="daily_cash_alerts", replace_existing=True)
    _scheduler.start()
    app.logger.info("Cash-flow alert scheduler started")
    return _scheduler
