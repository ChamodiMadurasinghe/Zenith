"""Agentic orchestration API — additive routes; does not replace existing flows."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from agentic import get_session_trace, handle_event
from agentic.contracts.events import EventType, InboundEvent

orchestration_bp = Blueprint("orchestration", __name__)


@orchestration_bp.post("/api/orchestrate")
def orchestrate():
    body = request.get_json(force=True, silent=True) or {}
    event = InboundEvent(
        event_type=body.get("event_type", EventType.INVOICE_IMAGE.value),
        session_id=body.get("session_id", ""),
        payload=body.get("payload") or {},
        source=body.get("source", "web"),
    )
    actions = handle_event(event)
    return jsonify({"actions": [a.to_dict() for a in actions]})


@orchestration_bp.get("/api/sessions/<session_id>/trace")
def session_trace(session_id: str):
    return jsonify(get_session_trace(session_id))


@orchestration_bp.get("/api/agentic/health")
def agentic_health():
    return jsonify({"status": "ok", "layer": "agentic_orchestration"})
