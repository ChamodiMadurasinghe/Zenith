"""LangChain tools wrapping core/bundling.py + guardrails (deterministic authority)."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any, Optional

from pydantic import BaseModel, Field

from config import Config
from core.bundling import compute_bundles
from core.cheque_batcher import audit_bundle_day_limits
from core.guardrails import apply_proposed_actions, collect_bundle_issues
from db import repositories as repo


@dataclass
class BundlingToolContext:
    """Mutable working state shared by all bundling tools in one chat turn."""

    dealer_id: int
    ceiling_lkr: float
    bundles: list = field(default_factory=list)
    allow_exceed_ceiling: bool = False
    pending_commit: bool = False
    validation_issues: list[str] = field(default_factory=list)
    last_preview: list | None = None


# --- Pydantic input schemas ---


class ComputeBundlesInput(BaseModel):
    invoice_ids: list[int] = Field(
        default_factory=list,
        description="Invoice IDs to pack. Empty = all ready unassigned invoices for the dealer.",
    )
    dry_run: bool = Field(True, description="If true, preview only; do not commit draft state.")


class DivideIntoChequesInput(BaseModel):
    num_cheques: int = Field(..., ge=1, description="Number of cheque groups to create.")
    invoice_ids: list[int] = Field(default_factory=list)
    allow_exceed_ceiling: bool = False
    dry_run: bool = True


class MoveInvoiceInput(BaseModel):
    invoice_id: int
    to_group: int = Field(..., ge=1, description="1-based cheque group number.")
    part_index: int | None = Field(
        None, description="When invoice is split, which part to move (1-based)."
    )
    dry_run: bool = True


class RebatchInvoiceInput(BaseModel):
    """Alias for move_invoice + recalculate_dates."""

    invoice_id: int
    to_group: int = Field(..., ge=1)
    dry_run: bool = True


class SetChequeDateInput(BaseModel):
    cheque_group: int = Field(..., ge=1)
    date: str = Field(..., description="YYYY-MM-DD cheque stated date.")
    dry_run: bool = True


class PostponeChequeInput(BaseModel):
    cheque_group: int = Field(..., ge=1)
    days: int = Field(1, ge=1)
    dry_run: bool = True


class SplitInvoiceInput(BaseModel):
    invoice_id: int
    num_parts: int | None = Field(
        None,
        ge=2,
        description="Split into N equal amount parts (each typically on its own cheque). Omit to put whole invoice alone.",
    )
    amounts: list[float] | None = Field(
        None,
        description="Explicit part amounts in LKR that sum to the invoice total.",
    )
    separate_cheques: bool = Field(
        True,
        description="If true, each part goes on its own cheque group.",
    )
    dry_run: bool = True


class RecalculateDatesInput(BaseModel):
    dry_run: bool = True


class CreateBundlesInput(BaseModel):
    groups: list[dict[str, Any]] = Field(
        ...,
        description='[{invoice_ids: [...], cheque_date?: "YYYY-MM-DD"}, ...]',
    )
    dry_run: bool = True


class AssignInvoicesInput(BaseModel):
    assignments: dict[str, int] = Field(
        ...,
        description='Map invoice_id string -> group number, e.g. {"12": 1, "13": 2}',
    )
    cheque_dates: dict[str, str] = Field(default_factory=dict)
    dry_run: bool = True


class CheckRiskInput(BaseModel):
    """Read-only day-limit / settlement risk check on current or preview bundles."""

    use_preview: bool = Field(
        False,
        description="If true, audit last_preview when available; else current bundles.",
    )


class DealerPatternsInput(BaseModel):
    """Read-only historical payment pattern lookup for this dealer."""

    invoice_total: float = Field(
        ...,
        description="Total LKR amount of current invoice(s) being discussed.",
    )


class ApplyBundleChangesInput(BaseModel):
    """Commit the last dry-run preview (or current working bundles) into draft state."""

    confirm: bool = Field(
        ...,
        description="Must be true to persist the working/preview bundles for the UI draft.",
    )


def _slim_bundles_for_tool(bundles: list) -> list[dict]:
    out = []
    for b in bundles or []:
        audit = b.get("day_limit_audit") or {}
        out.append(
            {
                "group": b.get("group"),
                "cheque_date": b.get("cheque_date"),
                "true_settlement_date": b.get("true_settlement_date"),
                "target_funding_date": b.get("target_funding_date"),
                "total_lkr": b.get("total_lkr"),
                "days_gained_by_holiday_lag": b.get("days_gained_by_holiday_lag"),
                "days_gained_total": b.get("days_gained_total"),
                "day_limit_verdict": audit.get("verdict"),
                "total_day_exposure": audit.get("total_day_exposure"),
                "invoice_ids": [int(i["invoices_id"]) for i in b.get("invoices") or []],
                "invoice_nos": [i.get("invoice_no") for i in b.get("invoices") or []],
            }
        )
    return out


def _diff_summary(before: list, after: list) -> str:
    return (
        f"groups {len(before or [])} → {len(after or [])}; "
        f"totals {[round(float(b.get('total_lkr') or 0), 2) for b in (after or [])]}"
    )


def _resolve_invoice_ids(ctx: BundlingToolContext, invoice_ids: list[int]) -> list[int]:
    if invoice_ids:
        return [int(x) for x in invoice_ids]
    ready = repo.get_verified_unassigned_invoices(ctx.dealer_id)
    ids = [int(i["invoices_id"]) for i in ready]
    for b in ctx.bundles or []:
        for inv in b.get("invoices") or []:
            iid = int(inv["invoices_id"])
            if iid not in ids:
                ids.append(iid)
    return ids


def _finish_mutation(
    ctx: BundlingToolContext,
    *,
    new_bundles: list,
    issues: list[str],
    allow_exceed: bool,
    dry_run: bool,
    ok: bool = True,
    error: str | None = None,
) -> str:
    audits = [
        b.get("day_limit_audit")
        for b in (new_bundles or [])
        if b.get("day_limit_audit")
    ]
    payload: dict[str, Any] = {
        "ok": ok and not error,
        "dry_run": dry_run,
        "error": error,
        "issues": issues,
        "day_limit_audits": audits,
        "diff_summary": _diff_summary(ctx.bundles, new_bundles),
        "bundles_preview": _slim_bundles_for_tool(new_bundles),
        "allow_exceed_ceiling": allow_exceed,
    }
    if dry_run:
        ctx.last_preview = copy.deepcopy(new_bundles)
        payload["committed"] = False
    else:
        ctx.bundles = new_bundles
        ctx.allow_exceed_ceiling = allow_exceed
        ctx.validation_issues = list(issues)
        ctx.pending_commit = True
        ctx.last_preview = copy.deepcopy(new_bundles)
        payload["committed"] = True
    return json.dumps(payload, default=str)


def _apply_actions(
    ctx: BundlingToolContext,
    actions: list[dict],
    dry_run: bool,
) -> str:
    try:
        new_bundles, issues, allow_exceed = apply_proposed_actions(
            ctx.bundles,
            actions,
            ctx.dealer_id,
            ctx.ceiling_lkr,
        )
    except Exception as exc:
        return json.dumps(
            {
                "ok": False,
                "dry_run": dry_run,
                "error": str(exc),
                "issues": [str(exc)],
                "bundles_preview": [],
                "committed": False,
            }
        )
    return _finish_mutation(
        ctx,
        new_bundles=new_bundles,
        issues=issues,
        allow_exceed=allow_exceed,
        dry_run=dry_run,
    )


def build_bundling_tools(ctx: BundlingToolContext) -> list:
    """Create LangChain tools bound to this chat-turn context."""
    from langchain_core.tools import StructuredTool

    def compute_cheque_bundles(invoice_ids: Optional[list[int]] = None, dry_run: bool = True) -> str:
        """Greedy LKR-ceiling pack via core/bundling.compute_bundles. Never invent dates yourself."""
        ids = _resolve_invoice_ids(ctx, list(invoice_ids or []))
        if not ids:
            return json.dumps(
                {
                    "ok": False,
                    "dry_run": dry_run,
                    "error": "No invoices available to bundle.",
                    "issues": ["No invoices available to bundle."],
                    "committed": False,
                }
            )
        try:
            new_bundles = compute_bundles(ctx.dealer_id, ids, ctx.ceiling_lkr)
            issues = collect_bundle_issues(
                {"bundles": new_bundles},
                ctx.dealer_id,
                ctx.ceiling_lkr,
                allow_exceed_ceiling=ctx.allow_exceed_ceiling,
            )
        except Exception as exc:
            return json.dumps({"ok": False, "dry_run": dry_run, "error": str(exc), "issues": [str(exc)]})
        return _finish_mutation(
            ctx,
            new_bundles=new_bundles,
            issues=issues,
            allow_exceed=ctx.allow_exceed_ceiling,
            dry_run=dry_run,
        )

    def divide_into_cheques(
        num_cheques: int,
        invoice_ids: Optional[list[int]] = None,
        allow_exceed_ceiling: bool = False,
        dry_run: bool = True,
    ) -> str:
        """Split invoices into N balanced cheque groups via core/bundling.divide_invoices_into_cheques."""
        ids = _resolve_invoice_ids(ctx, list(invoice_ids or []))
        return _apply_actions(
            ctx,
            [
                {
                    "action": "divide_into_cheques",
                    "num_cheques": int(num_cheques),
                    "invoice_ids": ids,
                    "allow_exceed_ceiling": bool(allow_exceed_ceiling),
                }
            ],
            dry_run,
        )

    def move_invoice(
        invoice_id: int,
        to_group: int,
        part_index: int | None = None,
        dry_run: bool = True,
    ) -> str:
        """Move one invoice (or split part) to another cheque group (1-based). Uses Python guardrails."""
        action = {"action": "move_invoice", "invoice_id": int(invoice_id), "to_group": int(to_group)}
        if part_index is not None:
            action["part_index"] = int(part_index)
        return _apply_actions(ctx, [action], dry_run)

    def rebatch_invoice(invoice_id: int, to_group: int, dry_run: bool = True) -> str:
        """Move invoice to another group and recalculate liquidity dates in Python."""
        return _apply_actions(
            ctx,
            [
                {"action": "move_invoice", "invoice_id": int(invoice_id), "to_group": int(to_group)},
                {"action": "recalculate_dates"},
            ],
            dry_run,
        )

    def set_cheque_date(cheque_group: int, date: str, dry_run: bool = True) -> str:
        """Set stated cheque date; Python recalculates settlement/funding dates."""
        return _apply_actions(
            ctx,
            [{"action": "set_cheque_date", "cheque_group": int(cheque_group), "date": date}],
            dry_run,
        )

    def postpone_cheque(cheque_group: int, days: int = 1, dry_run: bool = True) -> str:
        """Postpone a cheque by N calendar days; Python refreshes liquidity dates."""
        return _apply_actions(
            ctx,
            [
                {
                    "action": "postpone_cheque",
                    "cheque_group": int(cheque_group),
                    "days": int(days),
                }
            ],
            dry_run,
        )

    def split_invoice(
        invoice_id: int,
        num_parts: int | None = None,
        amounts: list[float] | None = None,
        separate_cheques: bool = True,
        dry_run: bool = True,
    ) -> str:
        """Split an invoice into amount parts (red ·1 ·2 labels) or put whole invoice alone on its own cheque."""
        action: dict = {"action": "split_invoice", "invoice_id": int(invoice_id)}
        if amounts:
            action["amounts"] = amounts
            action["separate_cheques"] = bool(separate_cheques)
        elif num_parts is not None and int(num_parts) >= 2:
            action["num_parts"] = int(num_parts)
            action["separate_cheques"] = bool(separate_cheques)
        return _apply_actions(ctx, [action], dry_run)

    def recalculate_dates(dry_run: bool = True) -> str:
        """Re-run enrich_bundle_liquidity on all current groups."""
        return _apply_actions(ctx, [{"action": "recalculate_dates"}], dry_run)

    def create_bundles(groups: list[dict[str, Any]], dry_run: bool = True) -> str:
        """Replace layout with explicit groups from invoice IDs (dates optional)."""
        return _apply_actions(
            ctx,
            [{"action": "create_bundles", "groups": groups}],
            dry_run,
        )

    def assign_invoices(
        assignments: dict[str, int],
        cheque_dates: Optional[dict[str, str]] = None,
        dry_run: bool = True,
    ) -> str:
        """Assign invoices to groups via map invoice_id→group."""
        return _apply_actions(
            ctx,
            [
                {
                    "action": "assign_invoices",
                    "assignments": assignments,
                    "cheque_dates": cheque_dates or {},
                }
            ],
            dry_run,
        )

    def check_day_limit_risk(use_preview: bool = False) -> str:
        """Read-only audit of casual daily limit / settlement exposure (cheque_batcher)."""
        bundles = (
            ctx.last_preview
            if use_preview and ctx.last_preview is not None
            else ctx.bundles
        )
        if not bundles:
            return json.dumps(
                {
                    "ok": True,
                    "verdicts": [],
                    "notes": "No bundles to audit yet.",
                }
            )
        audits = audit_bundle_day_limits(
            copy.deepcopy(bundles),
            account_id=repo.paying_account_id_for_dealer(ctx.dealer_id),
        )
        return json.dumps(
            {
                "ok": True,
                "verdicts": audits,
                "has_limit_breach": any(
                    a.get("verdict") == "LIMIT_BREACH_WARNING" for a in audits
                ),
            },
            default=str,
        )

    def get_dealer_historical_payment_patterns(invoice_total: float) -> str:
        """Read-only: past bundling, aging, account, and split patterns for this dealer."""
        from core.vector_store import query_dealer_patterns

        patterns_text = query_dealer_patterns(ctx.dealer_id, float(invoice_total))
        return json.dumps(
            {
                "ok": True,
                "patterns_text": patterns_text,
                "dealer_id": ctx.dealer_id,
                "invoice_total": float(invoice_total),
                "source": "vector_store",
            },
            default=str,
        )

    def apply_bundle_changes(confirm: bool) -> str:
        """Commit last dry-run preview into the working draft (UI session). Requires confirm=true."""
        if not confirm:
            return json.dumps(
                {
                    "ok": False,
                    "error": "Set confirm=true after the user agrees to apply changes.",
                    "committed": False,
                }
            )
        source = ctx.last_preview if ctx.last_preview is not None else ctx.bundles
        if not source:
            return json.dumps(
                {
                    "ok": False,
                    "error": "Nothing to apply. Run a dry_run tool first.",
                    "committed": False,
                }
            )
        issues = collect_bundle_issues(
            {"bundles": source},
            ctx.dealer_id,
            ctx.ceiling_lkr,
            allow_exceed_ceiling=ctx.allow_exceed_ceiling,
        )
        ctx.bundles = copy.deepcopy(source)
        ctx.validation_issues = list(issues)
        ctx.pending_commit = True
        return json.dumps(
            {
                "ok": True,
                "committed": True,
                "issues": issues,
                "bundles_preview": _slim_bundles_for_tool(ctx.bundles),
                "diff_summary": "Draft state updated for UI save.",
            },
            default=str,
        )

    tools = [
        StructuredTool.from_function(
            compute_cheque_bundles,
            name="compute_cheque_bundles",
            description="Pack invoices into cheques with LKR ceiling using core/bundling.compute_bundles.",
            args_schema=ComputeBundlesInput,
        ),
        StructuredTool.from_function(
            divide_into_cheques,
            name="divide_into_cheques",
            description="Split invoices into N cheque groups via Python.",
            args_schema=DivideIntoChequesInput,
        ),
        StructuredTool.from_function(
            move_invoice,
            name="move_invoice",
            description="Move an invoice to another cheque group.",
            args_schema=MoveInvoiceInput,
        ),
        StructuredTool.from_function(
            rebatch_invoice,
            name="rebatch_invoice",
            description="Move invoice and recalculate dates in Python.",
            args_schema=RebatchInvoiceInput,
        ),
        StructuredTool.from_function(
            set_cheque_date,
            name="set_cheque_date",
            description="Set cheque stated date; Python computes settlement.",
            args_schema=SetChequeDateInput,
        ),
        StructuredTool.from_function(
            postpone_cheque,
            name="postpone_cheque",
            description="Postpone a cheque by N days via Python.",
            args_schema=PostponeChequeInput,
        ),
        StructuredTool.from_function(
            split_invoice,
            name="split_invoice",
            description="Split invoice into amount parts (num_parts/amounts) or alone on its own cheque.",
            args_schema=SplitInvoiceInput,
        ),
        StructuredTool.from_function(
            recalculate_dates,
            name="recalculate_dates",
            description="Recalculate liquidity dates for all groups in Python.",
            args_schema=RecalculateDatesInput,
        ),
        StructuredTool.from_function(
            create_bundles,
            name="create_bundles",
            description="Replace bundle layout with explicit invoice groups.",
            args_schema=CreateBundlesInput,
        ),
        StructuredTool.from_function(
            assign_invoices,
            name="assign_invoices",
            description="Assign invoices to groups with optional cheque dates.",
            args_schema=AssignInvoicesInput,
        ),
        StructuredTool.from_function(
            check_day_limit_risk,
            name="check_day_limit_risk",
            description="Read-only casual daily limit / settlement risk audit.",
            args_schema=CheckRiskInput,
        ),
        StructuredTool.from_function(
            get_dealer_historical_payment_patterns,
            name="get_dealer_historical_payment_patterns",
            description=(
                "Read-only: retrieve past bundling habits, invoice aging records, "
                "preferred paying account, and split-payment patterns for this dealer."
            ),
            args_schema=DealerPatternsInput,
        ),
        StructuredTool.from_function(
            apply_bundle_changes,
            name="apply_bundle_changes",
            description="After user confirms, commit the last dry-run preview into the UI draft.",
            args_schema=ApplyBundleChangesInput,
        ),
    ]
    return tools


class SelectPayingAccountInput(BaseModel):
    cheque_group: int = Field(..., ge=1)
    account_id: int = Field(..., description="user_bank_acc_id from shop accounts")
    dry_run: bool = False


class SuggestMaxFloatDateInput(BaseModel):
    cheque_group: int = Field(..., ge=1)
    prefer_interbank: bool = True
    dry_run: bool = False


class ListInterbankOptionsInput(BaseModel):
    pass


class DealerPatternTextInput(BaseModel):
    invoice_total: float = Field(
        default=0.0,
        description="Total LKR of invoices being planned (for pattern context).",
    )


def build_strategist_tools(ctx: BundlingToolContext) -> list:
    """Agent 3 tools — Python bundling/guardrails authority, dry_run=False by default."""
    from langchain_core.tools import StructuredTool

    from core.dealer_patterns import build_dealer_pattern_document
    from core.strategist_dates import interbank_account_options, suggest_float_date_for_bundle

    chat_tools = {t.name: t for t in build_bundling_tools(ctx)}

    def list_interbank_account_options() -> str:
        return json.dumps(
            {"ok": True, "options": interbank_account_options(ctx.dealer_id)},
            default=str,
        )

    def get_dealer_payment_patterns(invoice_total: float = 0.0) -> str:
        doc = build_dealer_pattern_document(ctx.dealer_id)
        if Config.enable_vector_patterns() and not Config.use_fake_ai():
            try:
                from core.vector_store import query_dealer_patterns

                doc = query_dealer_patterns(ctx.dealer_id, float(invoice_total or 0))
            except Exception:
                pass
        return json.dumps(
            {
                "ok": True,
                "patterns_text": doc,
                "dealer_id": ctx.dealer_id,
                "invoice_total": float(invoice_total or 0),
            },
            default=str,
        )

    def select_paying_account(cheque_group: int, account_id: int, dry_run: bool = False) -> str:
        bundles = copy.deepcopy(ctx.bundles or [])
        found = False
        for b in bundles:
            if int(b.get("group") or 0) == int(cheque_group):
                b["paying_account_id"] = int(account_id)
                dealer_bank = repo.get_dealer_preferred_bank(ctx.dealer_id)
                payee = (dealer_bank or {}).get("bank_name") or ""
                acc = repo.get_bank_account(int(account_id))
                shop_bank = (acc or {}).get("bank_name") or ""
                if payee and shop_bank:
                    b["clearing_type"] = (
                        "INTRABANK" if shop_bank.lower() == payee.lower() else "INTERBANK"
                    )
                found = True
        if not found:
            return json.dumps({"ok": False, "error": f"Cheque group {cheque_group} not found."})
        from core.bundling import recalculate_all_bundles

        new_bundles = recalculate_all_bundles(bundles, ctx.dealer_id)
        issues = collect_bundle_issues(
            {"bundles": new_bundles},
            ctx.dealer_id,
            ctx.ceiling_lkr,
            allow_exceed_ceiling=ctx.allow_exceed_ceiling,
        )
        return _finish_mutation(
            ctx,
            new_bundles=new_bundles,
            issues=issues,
            allow_exceed=ctx.allow_exceed_ceiling,
            dry_run=dry_run,
        )

    def suggest_max_float_date(
        cheque_group: int, prefer_interbank: bool = True, dry_run: bool = False
    ) -> str:
        bundles = copy.deepcopy(ctx.bundles or [])
        target = None
        for b in bundles:
            if int(b.get("group") or 0) == int(cheque_group):
                target = b
                break
        if not target:
            return json.dumps({"ok": False, "error": f"Cheque group {cheque_group} not found."})
        suggestion = suggest_float_date_for_bundle(
            target, ctx.dealer_id, prefer_interbank=prefer_interbank
        )
        target["cheque_date"] = suggestion["proposed_date"]
        from core.bundling import recalculate_all_bundles

        new_bundles = recalculate_all_bundles(bundles, ctx.dealer_id)
        issues = collect_bundle_issues(
            {"bundles": new_bundles},
            ctx.dealer_id,
            ctx.ceiling_lkr,
            allow_exceed_ceiling=ctx.allow_exceed_ceiling,
        )
        payload = _finish_mutation(
            ctx,
            new_bundles=new_bundles,
            issues=issues,
            allow_exceed=ctx.allow_exceed_ceiling,
            dry_run=dry_run,
        )
        data = json.loads(payload)
        data["float_suggestion"] = suggestion
        return json.dumps(data, default=str)

    strategist_names = [
        "compute_cheque_bundles",
        "divide_into_cheques",
        "split_invoice",
        "postpone_cheque",
        "set_cheque_date",
        "recalculate_dates",
        "check_day_limit_risk",
    ]
    tools = [
        StructuredTool.from_function(
            list_interbank_account_options,
            name="list_interbank_account_options",
            description="List shop accounts and whether each is INTERBANK vs distributor bank.",
            args_schema=ListInterbankOptionsInput,
        ),
        StructuredTool.from_function(
            get_dealer_payment_patterns,
            name="get_dealer_payment_patterns",
            description="RAG: past cheque habits, preferred paying account, split patterns.",
            args_schema=DealerPatternTextInput,
        ),
        StructuredTool.from_function(
            select_paying_account,
            name="select_paying_account",
            description="Set paying shop account on a cheque group (prefer INTERBANK for float).",
            args_schema=SelectPayingAccountInput,
        ),
        StructuredTool.from_function(
            suggest_max_float_date,
            name="suggest_max_float_date",
            description="Python optimizer: best cheque date in credit window for max float (holidays/interbank).",
            args_schema=SuggestMaxFloatDateInput,
        ),
    ]
    for name in strategist_names:
        if name in chat_tools:
            tools.append(chat_tools[name])
    return tools
