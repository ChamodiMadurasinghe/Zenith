"""In-memory repository — Day 1 fallback until DB team delivers SQLite implementation."""

from __future__ import annotations

import copy
import uuid
from datetime import date
from typing import Any

from agentic.contracts.models import InvoiceDraft, PriceLog
from agentic.contracts.repositories import InvoiceRepository
from agentic.state.invoice_fsm import InvoiceState


# Prototype seed data (April 2026 New Year block — proposal demo scenario)
DEFAULT_HOLIDAYS = [
    "2026-04-12",
    "2026-04-13",
    "2026-04-14",
]

DEFAULT_PRICE_HISTORY: dict[str, list[PriceLog]] = {
    "dealer-colombo-pharma": [
        PriceLog(product="Paracetamol 500mg", unit_price=12.50, recorded_at="2026-03-01"),
        PriceLog(product="Amoxicillin 250mg", unit_price=45.00, recorded_at="2026-03-01"),
    ],
    "dealer-spike-demo": [
        PriceLog(product="Widget A", unit_price=100.00, recorded_at="2026-02-01"),
    ],
}


class InMemoryRepository:
    """Thread-unsafe in-memory store for prototype and tests."""

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._invoices: dict[str, dict[str, Any]] = {}
        self._price_history: dict[str, list[PriceLog]] = copy.deepcopy(DEFAULT_PRICE_HISTORY)
        self._holidays: list[str] = list(DEFAULT_HOLIDAYS)

    def create_session(self, session_id: str, invoice_id: str | None = None) -> None:
        if session_id in self._sessions:
            if invoice_id is not None:
                self._sessions[session_id]["invoice_id"] = invoice_id
            return
        self._sessions[session_id] = {
            "invoice_id": invoice_id,
            "memory": {},
            "trace": [],
        }

    def save_draft(self, session_id: str, draft: InvoiceDraft) -> str:
        invoice_id = str(uuid.uuid4())
        self._invoices[invoice_id] = {
            "session_id": session_id,
            "state": InvoiceState.RECEIVED.value,
            "draft": draft,
            "payload": {},
        }
        if session_id not in self._sessions:
            self.create_session(session_id, invoice_id)
        else:
            self._sessions[session_id]["invoice_id"] = invoice_id
        return invoice_id

    def get_history(self, dealer_id: str) -> list[PriceLog]:
        return list(self._price_history.get(dealer_id, []))

    def update_state(
        self,
        invoice_id: str,
        state: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        if invoice_id not in self._invoices:
            raise KeyError(f"Unknown invoice_id: {invoice_id}")
        self._invoices[invoice_id]["state"] = state
        if payload:
            self._invoices[invoice_id]["payload"].update(payload)

    def get_state(self, invoice_id: str) -> str | None:
        inv = self._invoices.get(invoice_id)
        return inv["state"] if inv else None

    def get_agent_memory(self, session_id: str) -> dict[str, Any]:
        session = self._sessions.get(session_id, {})
        return copy.deepcopy(session.get("memory", {}))

    def set_agent_memory(self, session_id: str, memory: dict[str, Any]) -> None:
        if session_id not in self._sessions:
            self.create_session(session_id)
        self._sessions[session_id]["memory"] = copy.deepcopy(memory)

    def get_trace(self, session_id: str) -> list[dict[str, Any]]:
        session = self._sessions.get(session_id, {})
        return list(session.get("trace", []))

    def append_trace(self, session_id: str, step: dict[str, Any]) -> None:
        if session_id not in self._sessions:
            self.create_session(session_id)
        self._sessions[session_id]["trace"].append(step)

    def get_holidays(self) -> list[str]:
        return list(self._holidays)

    def get_invoice_id_for_session(self, session_id: str) -> str | None:
        session = self._sessions.get(session_id)
        return session.get("invoice_id") if session else None

    def get_draft(self, invoice_id: str) -> InvoiceDraft | None:
        inv = self._invoices.get(invoice_id)
        return inv["draft"] if inv else None

    def seed_dealer_history(self, dealer_id: str, logs: list[PriceLog]) -> None:
        self._price_history[dealer_id] = logs

    def seed_holidays(self, holidays: list[str | date]) -> None:
        self._holidays = [
            h.isoformat() if isinstance(h, date) else h for h in holidays
        ]


# Satisfies InvoiceRepository protocol
def _check_protocol() -> None:
    _: InvoiceRepository = InMemoryRepository()
