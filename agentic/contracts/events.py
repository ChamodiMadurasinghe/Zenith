"""Inbound/outbound event contracts — shared by backend, UI, and orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(str, Enum):
    INVOICE_IMAGE = "INVOICE_IMAGE"
    DEALER_REPLY = "DEALER_REPLY"
    APPROVAL_DECISION = "APPROVAL_DECISION"
    OFFLINE_SYNC = "OFFLINE_SYNC"


class EventSource(str, Enum):
    WHATSAPP = "whatsapp"
    WEB = "web"
    CLI = "cli"
    SYSTEM = "system"


class ActionType(str, Enum):
    SHOW_UI = "SHOW_UI"
    SEND_MESSAGE = "SEND_MESSAGE"
    AWAIT_APPROVAL = "AWAIT_APPROVAL"
    ENQUEUE_RETRY = "ENQUEUE_RETRY"
    NONE = "NONE"


@dataclass
class InboundEvent:
    """
    Event passed to orchestrator.handle_event().

    Backend/UI construct these; orchestrator routes via Conversational Manager.
    """

    event_type: str | EventType
    session_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    source: str | EventSource = EventSource.WEB

    def __post_init__(self) -> None:
        if isinstance(self.event_type, EventType):
            self.event_type = self.event_type.value
        if isinstance(self.source, EventSource):
            self.source = self.source.value


@dataclass
class OutboundAction:
    """
    Action returned by orchestrator for backend/UI to execute.

    Examples:
      - SHOW_UI: display invoice detail + trace panel
      - SEND_MESSAGE: simulate WhatsApp to dealer
      - AWAIT_APPROVAL: block until human approves
    """

    action_type: str | ActionType
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.action_type, ActionType):
            self.action_type = self.action_type.value

    def to_dict(self) -> dict[str, Any]:
        return {"action_type": self.action_type, "payload": self.payload}
