"""Conversational Manager — routes inbound events to the invoice pipeline."""

from __future__ import annotations

import uuid

from agentic.contracts.events import (
    ActionType,
    EventType,
    InboundEvent,
    OutboundAction,
)
from agentic.contracts.repositories import InvoiceRepository
from agentic.orchestrator.pipeline import InvoicePipeline
from agentic.trace.agent_trace import AgentTrace


class ConversationalManager:
    """Maps intents to orchestration workflows."""

    def __init__(self, repo: InvoiceRepository) -> None:
        self._repo = repo
        self._pipeline = InvoicePipeline(repo)

    def handle(self, event: InboundEvent) -> list[OutboundAction]:
        event_type = event.event_type

        if event_type == EventType.INVOICE_IMAGE.value:
            return self._handle_invoice_image(event)
        if event_type == EventType.DEALER_REPLY.value:
            return self._handle_dealer_reply(event)
        if event_type == EventType.APPROVAL_DECISION.value:
            return self._handle_approval(event)
        if event_type == EventType.OFFLINE_SYNC.value:
            return self._handle_offline_sync(event)

        trace = self._trace_for(event.session_id)
        trace.decide("conversational_manager", "unknown_event", {"event_type": event_type})
        self._persist_trace(event.session_id, trace)
        return [OutboundAction(ActionType.NONE, {"error": f"Unknown event: {event_type}"})]

    def _handle_invoice_image(self, event: InboundEvent) -> list[OutboundAction]:
        session_id = event.session_id or str(uuid.uuid4())
        trace = self._trace_for(session_id)
        trace.plan(
            "conversational_manager",
            {
                "event": EventType.INVOICE_IMAGE.value,
                "source": event.source,
                "lang": event.payload.get("lang", "en"),
            },
            decision="route_to_pipeline",
        )
        self._persist_trace(session_id, trace)

        return self._pipeline.run_invoice_image(
            session_id=session_id,
            payload=event.payload,
            source=event.source,
        )

    def _handle_dealer_reply(self, event: InboundEvent) -> list[OutboundAction]:
        trace = self._trace_for(event.session_id)
        trace.plan(
            "conversational_manager",
            {"reply": event.payload.get("reply", "")},
            decision="route_dealer_reply",
        )
        self._persist_trace(event.session_id, trace)
        return self._pipeline.resume_dealer_reply(
            event.session_id,
            event.payload.get("reply", ""),
        )

    def _handle_approval(self, event: InboundEvent) -> list[OutboundAction]:
        approved = bool(event.payload.get("approved", False))
        trace = self._trace_for(event.session_id)
        trace.decide(
            "conversational_manager",
            "approved" if approved else "rejected",
            {"approved": approved},
        )
        self._persist_trace(event.session_id, trace)
        return self._pipeline.resume_approval(event.session_id, approved)

    def _handle_offline_sync(self, event: InboundEvent) -> list[OutboundAction]:
        return [OutboundAction(ActionType.ENQUEUE_RETRY, {"session_id": event.session_id})]

    def _trace_for(self, session_id: str) -> AgentTrace:
        trace = AgentTrace(session_id)
        existing = self._repo.get_trace(session_id)
        if existing:
            trace.load_from_dicts(existing)
        return trace

    def _persist_trace(self, session_id: str, trace: AgentTrace) -> None:
        existing_count = len(self._repo.get_trace(session_id))
        for step in trace.to_list()[existing_count:]:
            self._repo.append_trace(session_id, step)
