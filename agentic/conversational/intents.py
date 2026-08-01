"""Intent constants for Conversational Manager."""

from agentic.contracts.events import EventType

# Re-export for convenience
NEW_INVOICE = EventType.INVOICE_IMAGE.value
DEALER_REPLY = EventType.DEALER_REPLY.value
APPROVAL = EventType.APPROVAL_DECISION.value
OFFLINE_SYNC = EventType.OFFLINE_SYNC.value
