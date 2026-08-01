"""Repository interface — DB team implements; InMemoryRepository provided as fallback."""

from __future__ import annotations

from typing import Any, Protocol

from agentic.contracts.models import InvoiceDraft, PriceLog


class InvoiceRepository(Protocol):
    """Persistence layer for invoices, history, and agent memory."""

    def save_draft(self, session_id: str, draft: InvoiceDraft) -> str:
        """Persist extracted draft; return invoice_id."""
        ...

    def get_history(self, dealer_id: str) -> list[PriceLog]:
        """Price history for anomaly guard."""
        ...

    def update_state(
        self,
        invoice_id: str,
        state: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Update invoice FSM state and optional payload."""
        ...

    def get_state(self, invoice_id: str) -> str | None:
        """Current FSM state for invoice."""
        ...

    def get_agent_memory(self, session_id: str) -> dict[str, Any]:
        """Session-scoped agent memory."""
        ...

    def set_agent_memory(self, session_id: str, memory: dict[str, Any]) -> None:
        """Persist session-scoped agent memory."""
        ...

    def get_trace(self, session_id: str) -> list[dict[str, Any]]:
        """Agent trace steps for UI panel."""
        ...

    def append_trace(self, session_id: str, step: dict[str, Any]) -> None:
        """Append one trace step."""
        ...

    def get_holidays(self) -> list[str]:
        """CBSL holiday dates as ISO strings (YYYY-MM-DD)."""
        ...

    def create_session(self, session_id: str, invoice_id: str | None = None) -> None:
        """Initialize a new orchestration session."""
        ...
