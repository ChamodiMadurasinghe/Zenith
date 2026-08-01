"""Orchestrator entry point — routes events via Conversational Manager."""

from __future__ import annotations

from typing import Any

from agentic.adapters.zenith_repository import ZenithAgenticRepository
from agentic.adapters.in_memory_repo import InMemoryRepository
from agentic.contracts.events import InboundEvent
from agentic.conversational.manager import ConversationalManager
from agentic.contracts.repositories import InvoiceRepository


_default_repo: InvoiceRepository | None = None


def get_default_repository() -> InvoiceRepository:
    global _default_repo
    if _default_repo is None:
        try:
            _default_repo = ZenithAgenticRepository()
        except Exception:
            _default_repo = InMemoryRepository()
    return _default_repo


def set_default_repository(repo: InvoiceRepository) -> None:
    global _default_repo
    _default_repo = repo


def handle_event(
    event: InboundEvent,
    repo: InvoiceRepository | None = None,
) -> list:
    """
    Main orchestrator entry — backend calls this from POST /api/orchestrate.

    Returns list of OutboundAction for the route layer to execute.
    """
    repository = repo or get_default_repository()
    manager = ConversationalManager(repository)
    return manager.handle(event)


def get_session_trace(
    session_id: str,
    repo: InvoiceRepository | None = None,
) -> dict[str, Any]:
    """Helper for GET /api/sessions/{id}/trace."""
    repository = repo or get_default_repository()
    memory = repository.get_agent_memory(session_id)
    return {
        "session_id": session_id,
        "steps": repository.get_trace(session_id),
        "memory": memory,
        "fsm_state": memory.get("fsm_state"),
    }
