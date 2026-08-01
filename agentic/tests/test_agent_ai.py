"""Tests for conditional AI triggers (Agents 2 & 3)."""

from datetime import date

from agentic.adapters.agent_ai import needs_ai_audit, needs_ai_forecast
from agentic.contracts.models import AuditResult, ChequePlan, ForecastConstraints, InvoiceDraft


def test_needs_ai_audit_clean_pass():
    result = AuditResult(passed=True, anomalies=[], locked=False, severity="none")
    assert needs_ai_audit(result, []) is False


def test_needs_ai_audit_with_flags():
    result = AuditResult(passed=True, anomalies=["price spike"], locked=False, severity="warning")
    assert needs_ai_audit(result, [{"code": "price_spike"}]) is True


def test_needs_ai_audit_locked():
    result = AuditResult(passed=False, anomalies=["high risk"], locked=True, severity="critical")
    assert needs_ai_audit(result, [{"severity": "high"}]) is True


def _draft(total: float) -> InvoiceDraft:
    return InvoiceDraft(
        supplier_name="Acme",
        dealer_id="1",
        total_lkr=total,
        due_date=date.today(),
        payment_terms="30 days",
    )


def test_needs_ai_forecast_simple_invoice():
    draft = _draft(100_000)
    plan = ChequePlan(
        recommended_date=date.today(),
        float_days=0,
        rationale="no float",
        amount_lkr=100_000,
    )
    constraints = ForecastConstraints(cbsl_holidays=[])
    assert needs_ai_forecast(plan, draft, constraints, candidate_count=1) is False


def test_needs_ai_forecast_holiday_float():
    draft = _draft(100_000)
    plan = ChequePlan(
        recommended_date=date.today(),
        float_days=2,
        rationale="holiday lag",
        amount_lkr=100_000,
    )
    constraints = ForecastConstraints(cbsl_holidays=[date(2026, 4, 13)])
    assert needs_ai_forecast(plan, draft, constraints, candidate_count=1) is True


def test_needs_ai_forecast_dealer_reforecast():
    draft = _draft(50_000)
    plan = ChequePlan(
        recommended_date=date.today(),
        float_days=0,
        rationale="plain",
        amount_lkr=50_000,
    )
    constraints = ForecastConstraints(
        cbsl_holidays=[],
        alternative_pickup_date=date.today(),
    )
    assert needs_ai_forecast(plan, draft, constraints, negotiation_round=1) is True
