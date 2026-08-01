"""Shared domain models for ChequeMate agent pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class LineItem:
    product: str
    quantity: float
    unit_price: float

    @property
    def total(self) -> float:
        return self.quantity * self.unit_price


@dataclass
class InvoiceDraft:
    """Structured output from Agent 1 (Vision Extractor)."""

    supplier_name: str
    dealer_id: str | None
    total_lkr: float
    due_date: date | None
    payment_terms: str
    line_items: list[LineItem] = field(default_factory=list)
    language: str = "en"
    raw_confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditResult:
    """Output from Agent 2 (Anomaly Guard)."""

    passed: bool
    anomalies: list[str] = field(default_factory=list)
    locked: bool = False
    severity: str = "none"  # none | warning | critical


@dataclass
class ChequePlan:
    """Output from Agent 3 (Liquidity Forecaster)."""

    recommended_date: date
    float_days: int
    rationale: str
    amount_lkr: float
    clearing_resumes: date | None = None
    constraints_used: dict[str, Any] = field(default_factory=dict)


@dataclass
class LiaisonResult:
    """Output from Agent 4 (Dealer Liaison)."""

    status: str  # pending | confirmed | rejected | alternative_date
    message_to_dealer: str = ""
    alternative_date: date | None = None
    negotiation_round: int = 0
    notes: str = ""


@dataclass
class PriceLog:
    """Historical price entry for anomaly detection."""

    product: str
    unit_price: float
    recorded_at: str


@dataclass
class ForecastConstraints:
    """Inputs for liquidity forecasting."""

    cbsl_holidays: list[date] = field(default_factory=list)
    supplier_deadline: date | None = None
    alternative_pickup_date: date | None = None
    weekend_clearing_delay_days: int = 2
