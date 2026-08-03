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
    if Config.use_fake_ai():
        return (
            "# Business summary (demo)\n\n"
            f"- **Outstanding liabilities:** Rs. {metrics['outstanding_liabilities_lkr']:,.2f}\n"
            f"- **Cheques written:** {metrics['committed_cheques_count']} "
            f"(Rs. {metrics['committed_cheques_total_lkr']:,.2f})\n"
            f"- **Invoices not checked:** {metrics['unverified_invoices']}\n"
            f"- **Recent deposits (weekly):** Rs. {float(metrics.get('weekly_deposits') or 0):,.2f}\n\n"
            "## Recommendations\n"
            "- Review unverified invoices before writing more cheques.\n"
            "- Check Cash Flow for deposit timing against upcoming clearances.\n"
            "- Turn off demo mode and set OPENAI_API_KEY for a full AI narrative.\n"
        )
    return generate_report(metrics)
