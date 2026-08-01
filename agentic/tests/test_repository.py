"""Tests for in-memory repository and handler entry point."""

from datetime import date
from unittest.mock import MagicMock, patch

from agentic.adapters.in_memory_repo import InMemoryRepository
from agentic.contracts.events import EventType, InboundEvent
from agentic.contracts.models import (
    AuditResult,
    ChequePlan,
    InvoiceDraft,
    LineItem,
    PriceLog,
)
from agentic.orchestrator.handler import get_session_trace, handle_event


def test_in_memory_repo_save_and_trace():
    repo = InMemoryRepository()
    repo.create_session("s1")

    draft = InvoiceDraft(
        supplier_name="Colombo Pharma",
        dealer_id="dealer-colombo-pharma",
        total_lkr=650000,
        due_date=None,
        payment_terms="30 days",
        line_items=[LineItem("Paracetamol", 100, 12.5)],
    )
    invoice_id = repo.save_draft("s1", draft)
    assert invoice_id
    assert repo.get_state(invoice_id) == "RECEIVED"

    repo.append_trace("s1", {"agent": "test", "phase": "plan", "decision": "ok"})
    assert len(repo.get_trace("s1")) == 1

    repo.set_agent_memory("s1", {"attempt": 1})
    assert repo.get_agent_memory("s1")["attempt"] == 1


@patch("agentic.orchestrator.pipeline.ZenithAgentTools")
def test_handle_invoice_image_runs_pipeline(mock_tools_cls):
    mock_tools = MagicMock()
    mock_tools_cls.return_value = mock_tools
    mock_tools.vision.extract.return_value = InvoiceDraft(
        supplier_name="Test Supplier",
        dealer_id="1",
        total_lkr=650000,
        due_date=date(2026, 4, 20),
        payment_terms="30 days",
    )
    mock_tools.anomaly.audit.return_value = AuditResult(passed=True)
    mock_tools.liquidity.forecast.return_value = ChequePlan(
        recommended_date=date(2026, 4, 10),
        float_days=5,
        rationale="April float",
        amount_lkr=650000,
    )
    mock_tools.liaison.draft_message.return_value = "Confirm pickup?"

    repo = InMemoryRepository()
    event = InboundEvent(
        event_type=EventType.INVOICE_IMAGE,
        session_id="demo-session",
        payload={"lang": "en"},
        source="web",
    )
    actions = handle_event(event, repo=repo)

    assert len(actions) >= 1
    assert any(a.action_type in ("SHOW_UI", "SEND_MESSAGE") for a in actions)

    trace = get_session_trace("demo-session", repo=repo)
    assert len(trace["steps"]) >= 2
    assert trace["steps"][0]["phase"] == "plan"


def test_price_history_seed():
    repo = InMemoryRepository()
    history = repo.get_history("dealer-colombo-pharma")
    assert len(history) >= 1
    assert isinstance(history[0], PriceLog)


def test_holidays_seed():
    repo = InMemoryRepository()
    holidays = repo.get_holidays()
    assert "2026-04-13" in holidays
