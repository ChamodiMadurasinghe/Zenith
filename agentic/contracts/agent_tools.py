"""Tool interfaces — AI tools team implements these protocols."""

from __future__ import annotations

from typing import Protocol

from agentic.contracts.models import (
    AuditResult,
    ChequePlan,
    ForecastConstraints,
    InvoiceDraft,
    LiaisonResult,
)


class VisionExtractor(Protocol):
    """Agent 1: Multilingual Vision Data Extractor."""

    def extract(self, image_bytes: bytes, lang: str = "en") -> InvoiceDraft:
        """Extract structured invoice data from image bytes."""
        ...


class AnomalyGuard(Protocol):
    """Agent 2: Smart Anomaly Guard."""

    def audit(self, draft: InvoiceDraft, dealer_id: str) -> AuditResult:
        """Audit draft against historical price logs; may recommend lock."""
        ...


class LiquidityForecaster(Protocol):
    """Agent 3: Liquidity & Cheque Forecaster."""

    def forecast(
        self,
        draft: InvoiceDraft,
        constraints: ForecastConstraints,
    ) -> ChequePlan:
        """Compute optimal cheque date given holidays and deadlines."""
        ...


class DealerLiaison(Protocol):
    """Agent 4: Automated Dealer Liaison."""

    def draft_message(self, plan: ChequePlan, lang: str = "en") -> str:
        """Draft outbound WhatsApp message asking dealer to confirm pickup date."""
        ...

    def handle_reply(
        self,
        plan: ChequePlan,
        reply: str,
        negotiation_round: int = 0,
    ) -> LiaisonResult:
        """Parse dealer reply; return confirmed, rejected, or alternative date."""
        ...


class AgentTools(Protocol):
    """Bundle of all agent tools — injected into orchestrator."""

    vision: VisionExtractor
    anomaly: AnomalyGuard
    liquidity: LiquidityForecaster
    liaison: DealerLiaison
