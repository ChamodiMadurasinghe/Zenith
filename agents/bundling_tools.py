"""LangChain tools wrapping core/bundling.py + guardrails (deterministic authority)."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any, Optional

from pydantic import BaseModel, Field

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

    def move_invoice(invoice_id: int, to_group: int, dry_run: bool = True) -> str:
        """Move one invoice to another cheque group (1-based). Uses Python guardrails."""
        return _apply_actions(
            ctx,
            [{"action": "move_invoice", "invoice_id": int(invoice_id), "to_group": int(to_group)}],
            dry_run,
        )

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

    def split_invoice(invoice_id: int, dry_run: bool = True) -> str:
        """Put one invoice alone on its own cheque."""
        return _apply_actions(
            ctx,
            [{"action": "split_invoice", "invoice_id": int(invoice_id)}],
            dry_run,
        )

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
        audits = audit_bundle_day_limits(copy.deepcopy(bundles))
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
            description="Put one invoice on its own cheque.",
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
            apply_bundle_changes,
            name="apply_bundle_changes",
            description="After user confirms, commit the last dry-run preview into the UI draft.",
            args_schema=ApplyBundleChangesInput,
        ),
    ]
    return tools
