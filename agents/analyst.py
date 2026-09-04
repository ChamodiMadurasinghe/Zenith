import json

from agents.base import generate_text
from config import Config

SYSTEM = """You are a financial analyst for a Sri Lankan hardware business.
Given structured metrics, write a clear markdown report covering:
- Cash position vs outstanding liabilities
- Bank deposit trends
- Inventory / invoice velocity observations
- Actionable recommendations
Use headings, bullet points, and LKR amounts formatted with commas."""


def _as_money(value) -> float:
    """Coerce metrics values to float (handles legacy list-shaped deposit totals)."""
    if value is None:
        return 0.0
    if isinstance(value, (list, tuple)):
        total = 0.0
        for item in value:
            if isinstance(item, dict):
                total += _as_money(item.get("total"))
            else:
                total += _as_money(item)
        return total
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def generate_report(metrics: dict) -> str:
    prompt = f"Analyze these business metrics and write a markdown report:\n{json.dumps(metrics, indent=2)}"
    return generate_text(
        prompt,
        SYSTEM,
        provider="openai",
        model=Config.openai_analyst_model(),
    )


def build_report_markdown(metrics: dict) -> str:
    """Generate analyst markdown, with a deterministic demo fallback when USE_FAKE_AI."""
    liabilities = _as_money(metrics.get("outstanding_liabilities_lkr"))
    cheques_total = _as_money(metrics.get("committed_cheques_total_lkr"))
    weekly = _as_money(metrics.get("weekly_deposits"))
    cheques_count = int(metrics.get("committed_cheques_count") or 0)
    unverified = int(metrics.get("unverified_invoices") or 0)
    if Config.use_fake_ai():
        return (
            "# Business summary (demo)\n\n"
            f"- **Outstanding liabilities:** Rs. {liabilities:,.2f}\n"
            f"- **Cheques written:** {cheques_count} "
            f"(Rs. {cheques_total:,.2f})\n"
            f"- **Invoices not checked:** {unverified}\n"
            f"- **Recent deposits (weekly):** Rs. {weekly:,.2f}\n\n"
            "## Recommendations\n"
            "- Review unverified invoices before writing more cheques.\n"
            "- Check Cash Flow for deposit timing against upcoming clearances.\n"
            "- Turn off demo mode and set OPENAI_API_KEY for a full AI narrative.\n"
        )
    return generate_report(metrics)
