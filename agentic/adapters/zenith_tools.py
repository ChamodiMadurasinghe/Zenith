"""Wrap existing Zenith agents/core as agentic tool protocols — no changes to originals."""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

from agentic.contracts.models import (
    AuditResult,
    ChequePlan,
    ForecastConstraints,
    InvoiceDraft,
    LiaisonResult,
    LineItem,
)
from core.dates import format_date, next_business_day, parse_date
from core.liquidity_engine import apply_liquidity_dates, true_settlement_date


def _draft_from_zenith_extracted(data: dict, lang: str = "en") -> InvoiceDraft:
    line_items = []
    for item in data.get("line_items") or []:
        qty = float(item.get("item_qty") or 0)
        price = float(item.get("item_price") or 0)
        name = item.get("item_name") or item.get("item_code") or "item"
        line_items.append(LineItem(product=name, quantity=qty, unit_price=price))

    due_date = None
    invoiced = data.get("invoiced_date")
    credit_days = int(data.get("credit_period_days") or 30)
    if invoiced:
        try:
            inv_dt = parse_date(invoiced)
            due_date = inv_dt + timedelta(days=credit_days)
        except Exception:
            due_date = None

    dealer_id = data.get("dealer_id")
    if dealer_id is not None:
        dealer_id = str(dealer_id)

    return InvoiceDraft(
        supplier_name=(data.get("supplier_name") or "").strip(),
        dealer_id=dealer_id,
        total_lkr=float(data.get("total_amount") or 0),
        due_date=due_date,
        payment_terms=f"{credit_days} days",
        line_items=line_items,
        language=lang,
        metadata={"raw": data},
    )


def _extracted_from_draft(draft: InvoiceDraft) -> dict:
    raw = dict(draft.metadata.get("raw") or {})
    raw.setdefault("supplier_name", draft.supplier_name)
    raw.setdefault("total_amount", draft.total_lkr)
    raw.setdefault("credit_period_days", 30)
    if draft.due_date and not raw.get("invoiced_date"):
        raw["invoiced_date"] = format_date(draft.due_date - timedelta(days=30))
    return raw


class ZenithVisionExtractor:
    def extract(self, image_bytes: bytes, lang: str = "en") -> InvoiceDraft:
        # Prefer image_path in session memory (set by route); fallback to temp write
        from agents.ingestion import extract_invoice

        image_path = getattr(self, "_image_path", None)
        if not image_path:
            import tempfile

            tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            tmp.write(image_bytes)
            tmp.close()
            image_path = tmp.name

        data = extract_invoice(str(image_path))
        if isinstance(data, dict):
            data = dict(data)
        else:
            data = {}
        return _draft_from_zenith_extracted(data, lang)

    def set_image_path(self, path: str | Path) -> None:
        self._image_path = str(path)


class ZenithAnomalyGuard:
    def audit_rules(self, draft: InvoiceDraft, dealer_id: str) -> tuple[AuditResult, list[dict]]:
        from agents.anomaly import check_invoice_anomalies

        extracted = _extracted_from_draft(draft)
        numeric_dealer = int(dealer_id) if str(dealer_id).isdigit() else None
        flags = check_invoice_anomalies(extracted, numeric_dealer)

        messages = [f.get("message", f.get("code", "anomaly")) for f in flags]
        high = any(f.get("severity") == "high" for f in flags)
        locked = high and len(flags) > 0

        result = AuditResult(
            passed=not locked,
            anomalies=messages,
            locked=locked,
            severity="critical" if locked else ("warning" if flags else "none"),
        )
        return result, flags

    def audit(self, draft: InvoiceDraft, dealer_id: str) -> AuditResult:
        result, _ = self.audit_rules(draft, dealer_id)
        return result


class ZenithLiquidityForecaster:
    def forecast_with_candidates(
        self,
        draft: InvoiceDraft,
        constraints: ForecastConstraints,
    ) -> tuple[ChequePlan, list[dict]]:
        holidays = {format_date(d) if isinstance(d, date) else str(d) for d in constraints.cbsl_holidays}
        holiday_set = set(holidays)

        deadline = constraints.supplier_deadline or draft.due_date or date.today() + timedelta(days=30)
        if constraints.alternative_pickup_date:
            deadline = constraints.alternative_pickup_date

        candidate = deadline
        best_date = candidate
        best_float = 0
        best_detail: dict = {}
        seen: list[dict] = []

        for _ in range(45):
            if candidate.weekday() == 6:
                candidate -= timedelta(days=1)
                continue
            stated_str = format_date(candidate)
            detail = apply_liquidity_dates(stated_str, holiday_set, is_interbank=False)
            float_days = int(
                detail.get("days_gained_total")
                if detail.get("days_gained_total") is not None
                else detail.get("days_gained_by_holiday_lag")
                or 0
            )
            settlement = parse_date(detail["true_settlement_date"])
            if settlement <= deadline:
                seen.append(
                    {
                        "stated_date": stated_str,
                        "float_days": float_days,
                        "true_settlement_date": detail.get("true_settlement_date"),
                    }
                )
                if float_days >= best_float:
                    best_float = float_days
                    best_date = candidate
                    best_detail = detail
            candidate -= timedelta(days=1)
            if candidate < date.today() - timedelta(days=5):
                break

        seen.sort(key=lambda x: x["float_days"], reverse=True)
        unique: list[dict] = []
        for item in seen:
            if not any(u["stated_date"] == item["stated_date"] for u in unique):
                unique.append(item)
            if len(unique) >= 5:
                break

        clearing = None
        if best_detail.get("true_settlement_date"):
            try:
                clearing = parse_date(best_detail["true_settlement_date"])
            except Exception:
                clearing = None

        rationale = (
            f"Optimized cheque date {format_date(best_date)} for {draft.total_lkr:,.0f} LKR "
            f"with {best_float} day(s) float before settlement "
            f"({best_detail.get('true_settlement_date', 'n/a')})."
        )

        plan = ChequePlan(
            recommended_date=best_date,
            float_days=best_float,
            rationale=rationale,
            amount_lkr=draft.total_lkr,
            clearing_resumes=clearing,
            constraints_used={
                "holidays_count": len(holiday_set),
                "deadline": format_date(deadline),
            },
        )
        return plan, unique

    def forecast(
        self,
        draft: InvoiceDraft,
        constraints: ForecastConstraints,
    ) -> ChequePlan:
        plan, _ = self.forecast_with_candidates(draft, constraints)
        return plan


class ZenithDealerLiaison:
    def draft_message(self, plan: ChequePlan, lang: str = "en") -> str:
        return (
            f"Please confirm cheque pickup on {format_date(plan.recommended_date)} "
            f"for LKR {plan.amount_lkr:,.0f}. Reply YES to confirm or NO with your preferred date."
        )

    def handle_reply(
        self,
        plan: ChequePlan,
        reply: str,
        negotiation_round: int = 0,
    ) -> LiaisonResult:
        text = (reply or "").strip().lower()
        if text in {"yes", "y", "ok", "confirm", "confirmed"}:
            return LiaisonResult(
                status="confirmed",
                message_to_dealer=self.draft_message(plan),
                negotiation_round=negotiation_round,
                notes="Dealer confirmed pickup date.",
            )

        alt = _parse_alternative_date(reply)
        if text.startswith("no") or alt is not None:
            return LiaisonResult(
                status="alternative_date",
                message_to_dealer=self.draft_message(plan),
                alternative_date=alt,
                negotiation_round=negotiation_round + 1,
                notes="Dealer requested alternative date." if alt else "Dealer rejected without date.",
            )

        return LiaisonResult(
            status="pending",
            message_to_dealer="Please reply YES or NO with a preferred date.",
            negotiation_round=negotiation_round,
        )


def _parse_alternative_date(text: str) -> date | None:
    if not text:
        return None
    # ISO date
    m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if m:
        try:
            return parse_date(m.group(1))
        except Exception:
            pass
    # "April 15" style
    m = re.search(r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})",
                  text, re.I)
    if m:
        month_names = {
            "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
            "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
        }
        month = month_names[m.group(1).lower()]
        day = int(m.group(2))
        year = date.today().year
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None


class ZenithAgentTools:
    """Bundle injected into orchestrator pipeline."""

    def __init__(self) -> None:
        self.vision = ZenithVisionExtractor()
        self.anomaly = ZenithAnomalyGuard()
        self.liquidity = ZenithLiquidityForecaster()
        self.liaison = ZenithDealerLiaison()
