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
