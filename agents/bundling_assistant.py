"""Bundling Assistant — LangChain tool-calling agent over core/bundling.py."""

from __future__ import annotations

import json
from typing import Any

from config import Config
from core.chat_context import build_bundling_chat_context

BUNDLING_ASSISTANT_SYSTEM = """You are the Bundling Assistant for ChequeMate / Zenith (Sri Lankan SME cheque planning).

Identity:
- You are the interactive Bundling Assistant in the web app.
- You are NOT agentic pipeline Agent 2 (Anomaly) or Agent 3 (Liquidity Forecast).
- You are NOT the analytics report writer.

Deterministic authority (CRITICAL):
- You MUST NEVER invent or calculate cheque dates, holiday shifts, settlement dates, funding dates, or LKR ceilings yourself.
- All packing and date math MUST go through tools that call core/bundling.py / guardrails / cheque_batcher.
- Prefer dry_run=True on mutating tools until the user clearly confirms (apply / save / yes / commit).
- After a successful dry_run preview the user likes, call apply_bundle_changes(confirm=true) OR re-call the same tool with dry_run=False.

Self-correction:
- If a tool returns ok=false, issues[], or day_limit verdict LIMIT_BREACH_WARNING, explain the constraint in plain language and propose a concrete alternative tool call (different date, split, move invoice, raise allow_exceed only if user said so).

Style:
- Be concise. Cite invoice numbers and cheque group numbers from tool output / context.
- Always reply with helpful text for the merchant after tool use.
"""

LANG_INSTRUCTIONS = {
    "en": "Always respond in English.",
    "si": "Always respond in Sinhala (සිංහල). Use simple, clear Sinhala suitable for a Sri Lankan merchant.",
    "ta": "Always respond in Tamil (தமிழ்). Use simple, clear Tamil suitable for a Sri Lankan merchant.",
}


def bundling_tool_agent_available() -> bool:
    try:
        from langchain.agents import AgentExecutor, create_tool_calling_agent  # noqa: F401
        from langchain_openai import ChatOpenAI  # noqa: F401

        return True
    except ImportError:
        return False


def _history_to_messages(chat_history: list) -> list:
    from langchain_core.messages import AIMessage, HumanMessage

    messages = []
    for turn in chat_history or []:
        role = (turn.get("role") or "").lower()
        content = (turn.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    return messages


def _tool_trace(intermediate_steps: list) -> list[dict[str, Any]]:
    trace = []
    for step in intermediate_steps or []:
        try:
            action, observation = step
            trace.append(
                {
                    "tool": getattr(action, "tool", None),
                    "input": getattr(action, "tool_input", None),
                    "observation": str(observation)[:2000],
                }
            )
        except Exception:
            continue
    return trace


def run_bundling_assistant(
    *,
    dealer_id: int,
    message: str,
    chat_history: list,
    bundles: list,
    ceiling_lkr: float,
    lang: str = "en",
    agentic_hints: dict | None = None,
) -> dict:
    """Run one Bundling Assistant turn with tool calling.

    Returns dict compatible with the bundling chat route:
      reply, bundles, validation_issues, allow_exceed_ceiling, pending_commit, tool_trace
    """
    from langchain.agents import AgentExecutor, create_tool_calling_agent
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
    from langchain_openai import ChatOpenAI

    from agents.bundling_tools import BundlingToolContext, build_bundling_tools

    if not Config.openai_api_key():
        raise RuntimeError("OPENAI_API_KEY not set")

    ctx = BundlingToolContext(
        dealer_id=dealer_id,
        ceiling_lkr=float(ceiling_lkr),
        bundles=list(bundles or []),
        allow_exceed_ceiling=False,
    )
    tools = build_bundling_tools(ctx)

    context = build_bundling_chat_context(
        dealer_id, ctx.bundles, ceiling_lkr, agentic_hints=agentic_hints
    )
    context_json = json.dumps(context, default=str, indent=2)
    lang_line = LANG_INSTRUCTIONS.get(lang, LANG_INSTRUCTIONS["en"])
    system = (
        f"{BUNDLING_ASSISTANT_SYSTEM}\n{lang_line}\n\n"
        f"Current bundling context (JSON):\n{context_json}"
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system),
            MessagesPlaceholder("chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ]
    )
    llm = ChatOpenAI(
        model=Config.openai_chat_model(),
        api_key=Config.openai_api_key(),
        temperature=0.2,
    )
    agent = create_tool_calling_agent(llm, tools, prompt)
    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=False,
        max_iterations=6,
        return_intermediate_steps=True,
        handle_parsing_errors=True,
    )

    history_msgs = _history_to_messages(chat_history)
    # Keep recent turns only to limit tokens
    if len(history_msgs) > 8:
        history_msgs = history_msgs[-8:]

    result = executor.invoke(
        {
            "input": message,
            "chat_history": history_msgs,
        }
    )
    reply = (result.get("output") or "").strip()
    if not reply:
        reply = (
            "I checked the tools but had nothing useful to say. "
            "Ask me to group invoices, move an invoice, or check day-limit risk."
        )

    return {
        "reply": reply,
        "bundles": ctx.bundles,
        "validation_issues": list(ctx.validation_issues),
        "allow_exceed_ceiling": ctx.allow_exceed_ceiling,
        "pending_commit": ctx.pending_commit,
        "tool_trace": _tool_trace(result.get("intermediate_steps") or []),
        "proposed_actions": [],  # tools already applied into ctx when dry_run=False / apply
    }
