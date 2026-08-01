"""Invoice finite state machine — source of truth for pipeline states."""

from __future__ import annotations

from enum import Enum


class InvoiceState(str, Enum):
    RECEIVED = "RECEIVED"
    EXTRACTING = "EXTRACTING"
    RETRYING = "RETRYING"
    AUDITING = "AUDITING"
    LOCKED = "LOCKED"
    FORECASTING = "FORECASTING"
    REFORECASTING = "REFORECASTING"
    AWAITING_DEALER = "AWAITING_DEALER"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"


# Valid transitions: current_state -> set of allowed next states
TRANSITIONS: dict[InvoiceState, set[InvoiceState]] = {
    InvoiceState.RECEIVED: {InvoiceState.EXTRACTING},
    InvoiceState.EXTRACTING: {
        InvoiceState.RETRYING,
        InvoiceState.AUDITING,
    },
    InvoiceState.RETRYING: {InvoiceState.EXTRACTING},
    InvoiceState.AUDITING: {
        InvoiceState.LOCKED,
        InvoiceState.FORECASTING,
    },
    InvoiceState.LOCKED: set(),
    InvoiceState.FORECASTING: {InvoiceState.AWAITING_DEALER},
    InvoiceState.REFORECASTING: {InvoiceState.AWAITING_DEALER},
    InvoiceState.AWAITING_DEALER: {
        InvoiceState.REFORECASTING,
        InvoiceState.AWAITING_APPROVAL,
    },
    InvoiceState.AWAITING_APPROVAL: {
        InvoiceState.APPROVED,
        InvoiceState.REJECTED,
    },
    InvoiceState.APPROVED: {InvoiceState.COMPLETED},
    InvoiceState.REJECTED: set(),
    InvoiceState.COMPLETED: set(),
}

TERMINAL_STATES = {
    InvoiceState.LOCKED,
    InvoiceState.REJECTED,
    InvoiceState.COMPLETED,
}


class InvalidTransitionError(ValueError):
    """Raised when FSM transition is not allowed."""


class InvoiceFSM:
    """Validates and applies invoice state transitions."""

    def __init__(self, initial: InvoiceState = InvoiceState.RECEIVED) -> None:
        self._state = initial

    @property
    def state(self) -> InvoiceState:
        return self._state

    @property
    def is_terminal(self) -> bool:
        return self._state in TERMINAL_STATES

    def can_transition(self, target: InvoiceState | str) -> bool:
        target_state = _coerce_state(target)
        return target_state in TRANSITIONS.get(self._state, set())

    def transition(self, target: InvoiceState | str) -> InvoiceState:
        target_state = _coerce_state(target)
        if not self.can_transition(target_state):
            raise InvalidTransitionError(
                f"Cannot transition from {self._state.value} to {target_state.value}"
            )
        self._state = target_state
        return self._state

    def force_state(self, target: InvoiceState | str) -> InvoiceState:
        """Restore state from persistence (skip validation)."""
        self._state = _coerce_state(target)
        return self._state


def _coerce_state(value: InvoiceState | str) -> InvoiceState:
    if isinstance(value, InvoiceState):
        return value
    return InvoiceState(value)
