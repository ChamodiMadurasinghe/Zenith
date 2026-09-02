"""Agent 3: Gemini tool-calling strategist over bundling.py + guardrails."""

from __future__ import annotations

import json

from config import Config
from core.guardrails import collect_bundle_issues

STRATEGIST_AGENT_SYSTEM = """You are Agent 3: the Cunning Financial Strategist — a rule-following, business-minded
Sri Lankan SME owner planning cheque payments.

CRITICAL: You MUST use tools for all dates, amounts, splits, and bank math. Never invent cheque dates or totals.

Workflow (follow in order):
1. get_dealer_payment_patterns — learn preferred shop account, typical splits, aging habits.
2. compute_cheque_bundles — baseline pack by invoice totals and LKR ceiling (dry_run=false).
3. list_interbank_account_options — see which shop accounts give INTERBANK vs INTRABANK clearing.
4. select_paying_account — prefer INTERBANK (cross-bank) when it gains float vs distributor bank.
5. suggest_max_float_date — for each cheque group, let Python pick the best date in the credit window
   (e.g. last working day before a CBSL holiday/weekend break — cheque on 25 when 26–27 are holidays).
6. split_invoice or divide_into_cheques — smooth cash outflow into smaller cheques when patterns/history suggest it.
7. recalculate_dates — refresh liquidity fields after changes.
8. check_day_limit_risk — read-only audit; fix issues with postpone_cheque or split if needed.

Rules:
- Respect distributor credit terms: never date cheques beyond latest_permissible in context.
- Sum of cheque amounts must equal sum of invoice amounts.
- Prefer keeping cash in the shop account as long as legally possible.
- End with a short strategy_summary in plain language for the shop owner."""


def strategist_tool_agent_available() -> bool:
    try:
        from langchain.agents import AgentExecutor, create_tool_calling_agent  # noqa: F401
        from langchain_google_genai import ChatGoogleGenerativeAI  # noqa: F401

        return bool(Config.gemini_api_key())
    except ImportError:
        return False


def run_strategist_agent(dealer_id: int, invoice_ids: list[int], ceiling_lkr: float) -> dict:
    from agents.bundling_tools import BundlingToolContext, build_strategist_tools
    from agents.strategist import _bundles_to_strategy, build_strategist_context
    from agents.tool_agent import run_tool_agent

    if not Config.gemini_api_key():
        raise RuntimeError("GEMINI_API_KEY not set")

    ctx = BundlingToolContext(
        dealer_id=dealer_id,
        ceiling_lkr=float(ceiling_lkr),
        bundles=[],
        allow_exceed_ceiling=False,
    )
    tools = build_strategist_tools(ctx)
    context = build_strategist_context(dealer_id, invoice_ids, ceiling_lkr)
    context_json = json.dumps(context, indent=2, default=str)

    from langchain_google_genai import ChatGoogleGenerativeAI

    llm = ChatGoogleGenerativeAI(
        model=Config.gemini_text_model(),
        google_api_key=Config.gemini_api_key(),
        temperature=0.2,
    )

    user_message = (
        f"Plan cheques for invoice_ids={invoice_ids} with ceiling_lkr={ceiling_lkr}. "
        f"Maximize float using interbank accounts and holiday positioning. "
        f"Use dry_run=false on mutating tools.\n\nContext:\n{context_json}"
    )

    result = run_tool_agent(
        llm=llm,
        tools=tools,
        system_prompt=STRATEGIST_AGENT_SYSTEM,
        user_message=user_message,
        max_iterations=10,
    )

    bundles = ctx.bundles or ctx.last_preview or []
    issues = collect_bundle_issues(
        {"bundles": bundles},
        dealer_id,
        ceiling_lkr,
        allow_exceed_ceiling=ctx.allow_exceed_ceiling,
    )
    strategy = _bundles_to_strategy(bundles, dealer_id, ceiling_lkr)
    summary = (result.get("output") or "").strip() or strategy.get("strategy_summary", "")
    strategy["strategy_summary"] = summary
    strategy["bundles"] = bundles
    strategy["validation_issues"] = issues
    strategy["tool_trace"] = result.get("tool_trace") or []
    return strategy
