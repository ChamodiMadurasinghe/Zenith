"""Tests for invoice FSM transitions."""

import pytest

from agentic.state.invoice_fsm import InvalidTransitionError, InvoiceFSM, InvoiceState


def test_happy_path_transitions():
    fsm = InvoiceFSM()
    assert fsm.state == InvoiceState.RECEIVED

    fsm.transition(InvoiceState.EXTRACTING)
    fsm.transition(InvoiceState.AUDITING)
    fsm.transition(InvoiceState.FORECASTING)
    fsm.transition(InvoiceState.AWAITING_DEALER)
    fsm.transition(InvoiceState.AWAITING_APPROVAL)
    fsm.transition(InvoiceState.APPROVED)
    fsm.transition(InvoiceState.COMPLETED)

    assert fsm.is_terminal


def test_anomaly_lock_is_terminal():
    fsm = InvoiceFSM()
    fsm.transition(InvoiceState.EXTRACTING)
    fsm.transition(InvoiceState.AUDITING)
    fsm.transition(InvoiceState.LOCKED)
    assert fsm.is_terminal


def test_dealer_loop_via_reforecasting():
    fsm = InvoiceFSM()
    fsm.transition(InvoiceState.EXTRACTING)
    fsm.transition(InvoiceState.AUDITING)
    fsm.transition(InvoiceState.FORECASTING)
    fsm.transition(InvoiceState.AWAITING_DEALER)
    fsm.transition(InvoiceState.REFORECASTING)
    fsm.transition(InvoiceState.AWAITING_DEALER)
    assert fsm.state == InvoiceState.AWAITING_DEALER


def test_retry_from_extracting():
    fsm = InvoiceFSM()
    fsm.transition(InvoiceState.EXTRACTING)
    fsm.transition(InvoiceState.RETRYING)
    fsm.transition(InvoiceState.EXTRACTING)
    assert fsm.state == InvoiceState.EXTRACTING


def test_invalid_transition_raises():
    fsm = InvoiceFSM()
    with pytest.raises(InvalidTransitionError):
        fsm.transition(InvoiceState.COMPLETED)


def test_can_transition_check():
    fsm = InvoiceFSM()
    assert fsm.can_transition(InvoiceState.EXTRACTING)
    assert not fsm.can_transition(InvoiceState.LOCKED)
