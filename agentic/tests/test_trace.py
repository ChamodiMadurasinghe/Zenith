"""Tests for AgentTrace logger."""

from agentic.trace.agent_trace import AgentTrace


def test_trace_logs_plan_execute_review_decide():
    trace = AgentTrace("session-1")

    trace.plan("agent1", {"lang": "si"}, decision="planned")
    trace.execute("agent1", {"attempt": 1}, {"total_lkr": 650000})
    trace.review("agent1", {"fields_ok": True}, decision="continue")
    trace.decide("orchestrator", "continue")

    steps = trace.to_list()
    assert len(steps) == 4
    assert steps[0]["phase"] == "plan"
    assert steps[0]["agent"] == "agent1"
    assert steps[2]["decision"] == "continue"
    assert steps[3]["phase"] == "decide"


def test_trace_load_from_dicts():
    trace = AgentTrace("session-2")
    trace.plan("orchestrator", {"event": "INVOICE_IMAGE"})
    saved = trace.to_list()

    restored = AgentTrace("session-2")
    restored.load_from_dicts(saved)
    assert len(restored.steps) == 1
    assert restored.steps[0].agent == "orchestrator"
