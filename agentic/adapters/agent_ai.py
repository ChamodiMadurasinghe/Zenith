"""Conditional Gemini calls for Agent 2 (anomaly) and Agent 3 (liquidity)."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from agentic.contracts.models import AuditResult, ChequePlan, ForecastConstraints, InvoiceDraft
from config import Config
from core.dates import format_date, parse_date


def conditional_ai_enabled() -> bool:
    return Config.agent_conditional_ai()


def needs_ai_audit(rules_result: AuditResult, rule_flags: list[dict]) -> bool:
    """Run Gemini audit review when rules found issues or severity is not clean."""
    if not conditional_ai_enabled():
        return False
    if rules_result.locked:
        return True
    if rule_flags:
        return True
    if rules_result.severity in {"warning", "critical"}:
        return True
    return False


def needs_ai_forecast(
    plan: ChequePlan,
    draft: InvoiceDraft,
    constraints: ForecastConstraints,
    *,
    negotiation_round: int = 0,
    candidate_count: int = 1,
) -> bool:
    """Run Gemini when liquidity decision is strategic or ambiguous."""
    if not conditional_ai_enabled():
        return False
    if negotiation_round > 0 or constraints.alternative_pickup_date:
        return True
    if draft.total_lkr >= 500_000:
        return True
    if plan.float_days >= 1:
        return True
    if candidate_count > 1:
        return True
    return False


def ai_audit_review(
    draft: InvoiceDraft,
    dealer_id: str,
    rules_result: AuditResult,
    rule_flags: list[dict],
) -> AuditResult:
    """Second Agent 2 call — Gemini validates/explains rule-based audit."""
    from agents.providers.gemini import gemini_json

    system = """You are Agent 2: Smart Anomaly Guard for Sri Lankan SME invoices.
Review rule-based audit flags and decide pass, warning, or lock.
Respond JSON only with keys: passed (bool), locked (bool), severity ("none"|"warning"|"critical"), anomalies (list of strings)."""
    prompt = json.dumps(
        {
            "supplier": draft.supplier_name,
            "total_lkr": draft.total_lkr,
            "dealer_id": dealer_id,
            "rule_flags": rule_flags,
            "rules_result": {
                "passed": rules_result.passed,
                "locked": rules_result.locked,
                "severity": rules_result.severity,
                "anomalies": rules_result.anomalies,
            },
        },
        default=str,
    )
    try:
        data = gemini_json(
            f"Review this invoice audit:\n{prompt}",
            system=system,
            model=Config.gemini_text_model(),
        )
        return AuditResult(
            passed=bool(data.get("passed", rules_result.passed)),
            anomalies=[str(a) for a in (data.get("anomalies") or rules_result.anomalies)],
            locked=bool(data.get("locked", rules_result.locked)),
            severity=str(data.get("severity") or rules_result.severity),
        )
    except Exception:
        return rules_result


def ai_forecast_review(
    draft: InvoiceDraft,
    engine_plan: ChequePlan,
    candidates: list[dict[str, Any]],
    constraints: ForecastConstraints,
) -> ChequePlan:
    """Second Agent 3 call — Gemini picks cheque date and writes SME-facing rationale."""
    from agents.providers.gemini import gemini_json

    holidays = [
        format_date(d) if isinstance(d, date) else str(d)
        for d in constraints.cbsl_holidays
    ]
    system = """You are Agent 3: Liquidity & Cheque Forecaster for Sri Lankan SMEs.
Use CBSL holidays and candidate dates to maximize legal cheque float while meeting supplier deadlines.
Respond JSON only with keys: recommended_date (YYYY-MM-DD), float_days (int), rationale (string).
Pick recommended_date from candidate_dates when possible."""
    prompt = json.dumps(
        {
            "supplier": draft.supplier_name,
            "amount_lkr": draft.total_lkr,
            "due_date": format_date(draft.due_date) if draft.due_date else None,
            "supplier_deadline": (
                format_date(constraints.supplier_deadline)
                if constraints.supplier_deadline
                else None
            ),
            "alternative_pickup_date": (
                format_date(constraints.alternative_pickup_date)
                if constraints.alternative_pickup_date
                else None
            ),
            "cbsl_holidays_sample": holidays[:20],
            "engine_recommendation": {
                "recommended_date": format_date(engine_plan.recommended_date),
                "float_days": engine_plan.float_days,
                "rationale": engine_plan.rationale,
            },
            "candidate_dates": candidates[:5],
        },
        default=str,
    )
    try:
        data = gemini_json(
            f"Choose optimal cheque date:\n{prompt}",
            system=system,
            model=Config.gemini_text_model(),
        )
        rec = data.get("recommended_date") or format_date(engine_plan.recommended_date)
        try:
            rec_date = parse_date(str(rec)[:10])
        except Exception:
            rec_date = engine_plan.recommended_date
        return ChequePlan(
            recommended_date=rec_date,
            float_days=int(data.get("float_days", engine_plan.float_days)),
            rationale=str(data.get("rationale") or engine_plan.rationale),
            amount_lkr=draft.total_lkr,
            clearing_resumes=engine_plan.clearing_resumes,
            constraints_used={
                **engine_plan.constraints_used,
                "ai_review": True,
                "candidates_considered": len(candidates),
            },
        )
    except Exception:
        return engine_plan
