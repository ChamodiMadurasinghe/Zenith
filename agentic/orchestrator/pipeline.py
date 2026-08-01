"""Multi-agent pipeline: Agent1 → Agent2 → Agent3 → Agent4 with FSM + PER loops."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from agentic.adapters.zenith_tools import ZenithAgentTools
from agentic.contracts.events import ActionType, OutboundAction
from agentic.contracts.models import ForecastConstraints, InvoiceDraft
from agentic.contracts.repositories import InvoiceRepository
from agentic.memory.session_store import SessionStore
from agentic.orchestrator.per_loop import PERLoop
from agentic.state.invoice_fsm import InvalidTransitionError, InvoiceFSM, InvoiceState
from agentic.trace.agent_trace import AgentTrace


class InvoicePipeline:
    def __init__(
        self,
        repo: InvoiceRepository,
        tools: ZenithAgentTools | None = None,
    ) -> None:
        self._repo = repo
        self._tools = tools or ZenithAgentTools()

    def run_invoice_image(
        self,
        session_id: str,
        payload: dict[str, Any],
        source: str = "web",
    ) -> list[OutboundAction]:
        self._repo.create_session(session_id)
        store = SessionStore(self._repo, session_id)
        trace = self._load_trace(session_id)

        image_path = payload.get("image_path")
        image_bytes = payload.get("image_bytes") or b""
        lang = payload.get("lang", "en")

        if image_path:
            self._tools.vision.set_image_path(image_path)
            store.set("image_path", image_path)

        fsm = InvoiceFSM(InvoiceState.RECEIVED)
        self._transition(fsm, InvoiceState.EXTRACTING, session_id, store)

        # --- Agent 1: Vision ---
        draft = self._run_agent1(session_id, store, trace, image_bytes, lang, fsm)
        if draft is None:
            return self._ui(session_id, fsm.state.value, "Extraction failed after retries.")

        invoice_id = self._repo.save_draft(session_id, draft)
        store.set("invoice_id", invoice_id)
        store.set("draft", _draft_dict(draft))

        dealer_id = draft.dealer_id or payload.get("dealer_id") or "unknown"
        store.set("dealer_id", str(dealer_id))

        # --- Agent 2: Anomaly ---
        self._transition(fsm, InvoiceState.AUDITING, session_id, store, invoice_id)
        audit = self._run_agent2(session_id, store, trace, draft, str(dealer_id), fsm)
        if audit.locked:
            self._transition(fsm, InvoiceState.LOCKED, session_id, store, invoice_id)
            self._persist_trace(session_id, trace)
            return self._ui(
                session_id,
                fsm.state.value,
                "Invoice locked due to anomalies.",
                extra={"anomalies": audit.anomalies, "locked": True},
            )

        # --- Agent 3: Liquidity ---
        self._transition(fsm, InvoiceState.FORECASTING, session_id, store, invoice_id)
        plan = self._run_agent3(session_id, store, trace, draft, fsm)
        if plan is None:
            self._persist_trace(session_id, trace)
            return self._ui(session_id, fsm.state.value, "Liquidity forecast failed.")
        store.set("cheque_plan", _plan_dict(plan))

        # --- Agent 4: Dealer liaison (draft message) ---
        self._transition(fsm, InvoiceState.AWAITING_DEALER, session_id, store, invoice_id)
        message = self._tools.liaison.draft_message(plan, lang)
        store.set("dealer_message", message)
        trace.plan("agent4", {"plan_date": str(plan.recommended_date)}, decision="message_drafted")
        trace.execute("agent4", {}, {"message": message}, decision="executed")

        self._persist_trace(session_id, trace)
        return [
            OutboundAction(
                ActionType.SEND_MESSAGE,
                {"session_id": session_id, "message": message, "channel": source},
            ),
            OutboundAction(
                ActionType.SHOW_UI,
                {
                    "session_id": session_id,
                    "state": fsm.state.value,
                    "cheque_plan": _plan_dict(plan),
                    "draft": _draft_dict(draft),
                },
            ),
        ]

    def resume_dealer_reply(
        self,
        session_id: str,
        reply: str,
    ) -> list[OutboundAction]:
        store = SessionStore(self._repo, session_id)
        trace = self._load_trace(session_id)
        invoice_id = store.get("invoice_id")
        fsm = self._fsm_from_store(store)

        plan_dict = store.get("cheque_plan") or {}
        from agentic.contracts.models import ChequePlan

        plan = ChequePlan(
            recommended_date=date.fromisoformat(plan_dict["recommended_date"]),
            float_days=int(plan_dict.get("float_days", 0)),
            rationale=plan_dict.get("rationale", ""),
            amount_lkr=float(plan_dict.get("amount_lkr", 0)),
        )
        round_no = int(store.get("negotiation_round", 0))
        liaison = self._tools.liaison.handle_reply(plan, reply, round_no)
        store.set("negotiation_round", liaison.negotiation_round)
        trace.execute("agent4", {"reply": reply}, {"status": liaison.status}, decision="executed")

        if liaison.status == "alternative_date" and liaison.alternative_date:
            self._transition(fsm, InvoiceState.REFORECASTING, session_id, store, invoice_id)
            draft = _draft_from_store(store)
            constraints = ForecastConstraints(
                cbsl_holidays=_holiday_dates(self._repo),
                alternative_pickup_date=liaison.alternative_date,
            )
            per = PERLoop(trace, "agent3")
            result = per.run(
                {"alternative_date": str(liaison.alternative_date)},
                lambda: self._tools.liquidity.forecast(draft, constraints),
                lambda p: (True, "continue", "re-forecast with dealer date"),
            )
            if result.output:
                plan = result.output
                store.set("cheque_plan", _plan_dict(plan))
            self._transition(fsm, InvoiceState.AWAITING_DEALER, session_id, store, invoice_id)
            msg = self._tools.liaison.draft_message(plan)
            self._persist_trace(session_id, trace)
            return [
                OutboundAction(ActionType.SEND_MESSAGE, {"session_id": session_id, "message": msg}),
                OutboundAction(ActionType.SHOW_UI, {"session_id": session_id, "state": fsm.state.value}),
            ]

        if liaison.status == "confirmed":
            self._transition(fsm, InvoiceState.AWAITING_APPROVAL, session_id, store, invoice_id)
            self._persist_trace(session_id, trace)
            return [
                OutboundAction(ActionType.AWAIT_APPROVAL, {"session_id": session_id, "invoice_id": invoice_id}),
                OutboundAction(ActionType.SHOW_UI, {"session_id": session_id, "state": fsm.state.value}),
            ]

        self._persist_trace(session_id, trace)
        return [OutboundAction(ActionType.SHOW_UI, {"session_id": session_id, "state": fsm.state.value})]

    def resume_approval(
        self,
        session_id: str,
        approved: bool,
    ) -> list[OutboundAction]:
        store = SessionStore(self._repo, session_id)
        trace = self._load_trace(session_id)
        invoice_id = store.get("invoice_id")
        fsm = self._fsm_from_store(store)

        if approved:
            self._transition(fsm, InvoiceState.APPROVED, session_id, store, invoice_id)
            self._transition(fsm, InvoiceState.COMPLETED, session_id, store, invoice_id)
            trace.decide("orchestrator", "completed", {"approved": True})
        else:
            self._transition(fsm, InvoiceState.REJECTED, session_id, store, invoice_id)
            trace.decide("orchestrator", "rejected", {"approved": False})

        self._persist_trace(session_id, trace)
        return [OutboundAction(ActionType.SHOW_UI, {"session_id": session_id, "state": fsm.state.value})]

    def _run_agent1(
        self,
        session_id: str,
        store: SessionStore,
        trace: AgentTrace,
        image_bytes: bytes,
        lang: str,
        fsm: InvoiceFSM,
    ) -> InvoiceDraft | None:
        per = PERLoop(trace, "agent1")
        attempt = 1
        while attempt <= PERLoop.MAX_RETRIES:
            result = per.run(
                {"lang": lang},
                lambda: self._tools.vision.extract(image_bytes, lang),
                self._review_draft,
                attempt=attempt,
            )
            if result.success and result.output:
                return result.output
            if not result.retry:
                break
            self._transition(fsm, InvoiceState.RETRYING, session_id, store)
            self._transition(fsm, InvoiceState.EXTRACTING, session_id, store)
            attempt += 1
        return None

    def _run_agent2(self, session_id, store, trace, draft, dealer_id, fsm):
        from agentic.contracts.models import AuditResult

        per = PERLoop(trace, "agent2")
        result = per.run(
            {"dealer_id": dealer_id},
            lambda: self._tools.anomaly.audit(draft, dealer_id),
            lambda a: (
                not a.locked,
                "lock" if a.locked else "continue",
                "; ".join(a.anomalies) if a.anomalies else "pass",
            ),
        )
        return result.output or AuditResult(passed=True)

    def _run_agent3(self, session_id, store, trace, draft, fsm):
        constraints = ForecastConstraints(
            cbsl_holidays=_holiday_dates(self._repo),
            supplier_deadline=draft.due_date,
        )
        per = PERLoop(trace, "agent3")
        result = per.run(
            {"amount": draft.total_lkr, "deadline": str(draft.due_date)},
            lambda: self._tools.liquidity.forecast(draft, constraints),
            lambda p: (True, "continue", p.rationale[:120]),
        )
        return result.output

    @staticmethod
    def _review_draft(draft: InvoiceDraft) -> tuple[bool, str, str]:
        if not draft.supplier_name:
            return False, "retry", "missing supplier_name"
        if draft.total_lkr <= 0:
            return False, "retry", "missing total_lkr"
        return True, "continue", "required fields present"

    def _transition(
        self,
        fsm: InvoiceFSM,
        target: InvoiceState,
        session_id: str,
        store: SessionStore,
        invoice_id: str | None = None,
    ) -> None:
        try:
            fsm.transition(target)
        except InvalidTransitionError:
            fsm.force_state(target)
        store.set("fsm_state", fsm.state.value)
        if invoice_id:
            self._repo.update_state(invoice_id, fsm.state.value)

    def _fsm_from_store(self, store: SessionStore) -> InvoiceFSM:
        state = store.get("fsm_state", InvoiceState.RECEIVED.value)
        fsm = InvoiceFSM()
        fsm.force_state(state)
        return fsm

    def _load_trace(self, session_id: str) -> AgentTrace:
        trace = AgentTrace(session_id)
        existing = self._repo.get_trace(session_id)
        if existing:
            trace.load_from_dicts(existing)
        return trace

    def _persist_trace(self, session_id: str, trace: AgentTrace) -> None:
        existing_count = len(self._repo.get_trace(session_id))
        for step in trace.to_list()[existing_count:]:
            self._repo.append_trace(session_id, step)

    @staticmethod
    def _ui(session_id: str, state: str, message: str, extra: dict | None = None) -> list[OutboundAction]:
        payload = {"session_id": session_id, "state": state, "message": message}
        if extra:
            payload.update(extra)
        return [OutboundAction(ActionType.SHOW_UI, payload)]


def _holiday_dates(repo: InvoiceRepository) -> list[date]:
    dates = []
    for h in repo.get_holidays():
        try:
            dates.append(date.fromisoformat(h[:10]))
        except ValueError:
            continue
    return dates


def _draft_dict(draft: InvoiceDraft) -> dict:
    return {
        "supplier_name": draft.supplier_name,
        "dealer_id": draft.dealer_id,
        "total_lkr": draft.total_lkr,
        "due_date": draft.due_date.isoformat() if draft.due_date else None,
        "payment_terms": draft.payment_terms,
    }


def _plan_dict(plan) -> dict:
    return {
        "recommended_date": plan.recommended_date.isoformat(),
        "float_days": plan.float_days,
        "rationale": plan.rationale,
        "amount_lkr": plan.amount_lkr,
    }


def _draft_from_store(store: SessionStore) -> InvoiceDraft:
    d = store.get("draft") or {}
    due = d.get("due_date")
    return InvoiceDraft(
        supplier_name=d.get("supplier_name", ""),
        dealer_id=d.get("dealer_id"),
        total_lkr=float(d.get("total_lkr") or 0),
        due_date=date.fromisoformat(due) if due else None,
        payment_terms=d.get("payment_terms", "30 days"),
    )
