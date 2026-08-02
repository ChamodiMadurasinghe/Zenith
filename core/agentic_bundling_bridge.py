"""Load agentic pipeline memory hints for the Bundling Assistant."""

from __future__ import annotations

from typing import Any


def load_agentic_hints_for_bundling(session_id: str | None) -> dict[str, Any] | None:
    """Return cheque_plan + anomaly_flags from agentic session memory when available.

    These come from agentic Agents 2 (Anomaly) and 3 (Liquidity), and seed the
    Bundling Assistant context — not to be confused with legacy 'Agent 2' chat naming.
    """
    if not session_id or not str(session_id).strip():
        return None
    try:
        from agentic.orchestrator.handler import get_default_repository

        memory = get_default_repository().get_agent_memory(str(session_id).strip()) or {}
    except Exception:
        return None

    cheque_plan = memory.get("cheque_plan")
    anomaly_flags = memory.get("anomaly_flags")
    if not cheque_plan and not anomaly_flags:
        return None
    return {
        "session_id": str(session_id).strip(),
        "cheque_plan": cheque_plan,
        "anomaly_flags": anomaly_flags or [],
    }
