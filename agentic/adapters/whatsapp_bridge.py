"""Bridge local WhatsApp intake ↔ agentic orchestrator (legacy agentic path)."""

from __future__ import annotations

from agentic import handle_event
from agentic.contracts.events import ActionType, EventSource, EventType, InboundEvent, OutboundAction
from agentic.orchestrator.handler import get_default_repository
from core.whatsapp_intake import WHATSAPP_INBOX_REPLY
from db import repositories as repo


def actions_to_whatsapp_reply(actions: list[OutboundAction]) -> str:
    """Convert orchestrator OutboundActions into a single WhatsApp text reply."""
    parts: list[str] = []

    for action in actions:
        atype = action.action_type
        payload = action.payload or {}

        if atype == ActionType.SEND_MESSAGE.value:
            msg = payload.get("message")
            if msg:
                parts.append(str(msg))

        elif atype == ActionType.AWAIT_APPROVAL.value:
            parts.append(
                "Cheque plan ready. Reply APPROVE to confirm or REJECT to cancel, "
                "or open the web dashboard to review."
            )

        elif atype == ActionType.SHOW_UI.value:
            if payload.get("message"):
                parts.append(str(payload["message"]))
            if payload.get("locked"):
                anomalies = payload.get("anomalies") or []
                parts.append("Invoice locked — anomalies detected:")
                for a in anomalies:
                    parts.append(f"- {a}")
            plan = payload.get("cheque_plan")
            if plan:
                parts.append("Working Capital Strategy:")
                parts.append(
                    f"Recommended cheque date: {plan.get('recommended_date')} "
                    f"(LKR {float(plan.get('amount_lkr', 0)):,.2f}, "
                    f"{plan.get('float_days', 0)} day(s) float)."
                )
                if plan.get("rationale"):
                    parts.append(str(plan["rationale"]))
            draft = payload.get("draft")
            if draft and draft.get("supplier_name"):
                parts.append(f"Supplier: {draft['supplier_name']}")

        elif atype == ActionType.ENQUEUE_RETRY.value:
            parts.append("Queued for retry when connection is restored.")

        elif atype == ActionType.NONE.value and payload.get("error"):
            parts.append(f"Error: {payload['error']}")

    combined = "\n\n".join(p.strip() for p in parts if p and p.strip())
    return combined or "Processed. Open the web app for details."


def _route_text_event(sender: str, body: str) -> InboundEvent | None:
    """Map WhatsApp text to orchestrator event based on session FSM state."""
    memory = get_default_repository().get_agent_memory(sender)
    state = memory.get("fsm_state", "")
    text = (body or "").strip().lower()

    if state == "AWAITING_APPROVAL":
        if text in {"approve", "approved", "yes", "y", "ok", "confirm"}:
            return InboundEvent(
                EventType.APPROVAL_DECISION,
                sender,
                {"approved": True},
                EventSource.WHATSAPP,
            )
        if text in {"reject", "rejected", "no", "n", "cancel"}:
            return InboundEvent(
                EventType.APPROVAL_DECISION,
                sender,
                {"approved": False},
                EventSource.WHATSAPP,
            )
        return None

    if state in {"AWAITING_DEALER", "REFORECASTING"}:
        return InboundEvent(
            EventType.DEALER_REPLY,
            sender,
            {"reply": body},
            EventSource.WHATSAPP,
        )

    return None


def process_whatsapp_via_agentic(
    media_ref: str | None,
    sender_phone: str,
    *,
    resolve_image_path,
) -> str:
    """Save invoice image to web inbox; Gemini runs when user chooses on the portal."""
    if media_ref and str(media_ref).startswith("http"):
        _, location_path = resolve_image_path(media_url=media_ref)
    else:
        _, location_path = resolve_image_path(media_id=media_ref)
    repo.save_whatsapp_inbox(sender_phone, location_path)
    return WHATSAPP_INBOX_REPLY


def process_whatsapp_text_via_agentic(sender_phone: str, body: str) -> str:
    """Route dealer/approval replies through orchestrator; fall back to legacy onboarding."""
    event = _route_text_event(sender_phone, body)
    if event:
        actions = handle_event(event)
        return actions_to_whatsapp_reply(actions)

    from core.whatsapp_conversation import handle_text_reply

    legacy = handle_text_reply(sender_phone, body)
    if legacy:
        return legacy

    memory = get_default_repository().get_agent_memory(sender_phone)
    if memory.get("fsm_state"):
        actions = handle_event(
            InboundEvent(
                EventType.DEALER_REPLY,
                sender_phone,
                {"reply": body},
                EventSource.WHATSAPP,
            )
        )
        return actions_to_whatsapp_reply(actions)

    return "Please send a photo of an invoice or cheque."
