import threading

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session, url_for

from config import Config
from core.amounts import amount_to_words
from core.auth import login_required
from core.i18n import flash_t, get_lang, translate
from core.bundle_session import hydrate_bundles, load_bundle_state, save_bundle_state, slim_bundles
from core.bundling import build_bundles_from_assignments, compute_bundles
from core.bundling_intent import infer_bundling_actions, normalize_proposed_actions
from core.guardrails import apply_proposed_actions, collect_bundle_issues, validate_bundle_state
from core.bundle_orchestrator import auto_review_until_approved
from db import repositories as repo

bundling_bp = Blueprint("bundling", __name__)


def _chat_error_hint(err: str) -> str:
    if "OPENAI_API_KEY not set" in err:
        return "Agent unavailable. Set OPENAI_API_KEY in .env and restart the app."
    if "GEMINI_API_KEY not set" in err:
        return "Vision agent unavailable. Set GEMINI_API_KEY in .env for invoice upload."
    if "401" in err or "invalid_api_key" in err.lower() or "incorrect api key" in err.lower():
        return "Invalid OpenAI API key. Replace OPENAI_API_KEY in .env and restart."
    err_l = err.lower()
    # Billing / prepaid balance (often confused with ChatGPT Plus credits).
    if (
        "insufficient_quota" in err_l
        or "credit_balance_exhausted" in err_l
        or "no credits remaining" in err_l
    ):
        return (
            "OpenAI API billing for this key's organization has no credits left "
            "(ChatGPT Plus ≠ API credits). Add funds at "
            "https://platform.openai.com/settings/organization/billing/ "
            "or set USE_FAKE_AI=true for UI testing."
        )
    # Match real API rate-limit errors — avoid false positives from other exception text.
    if (
        "429" in err
        or "rate_limit" in err_l
        or "rate limit" in err_l
        or "resourceexhausted" in err_l
    ) and "chatprompttemplate" not in err_l:
        return (
            "Rate limit exceeded. Try USE_FAKE_AI=true for UI testing, rotate API keys, "
            "or use Reset Chat to shorten the prompt."
        )
    return f"Agent unavailable: {err[:200]}"


def _bundle_session():
    return session.setdefault("bundle_state", {})


def _load_state(dealer_id: int) -> dict:
    return load_bundle_state(session, dealer_id)


def _save_state(
    dealer_id: int,
    bundles: list,
    ceiling_lkr: float,
    chat_history: list,
    validation_issues: list | None = None,
    allow_exceed_ceiling: bool = False,
    pending_review: str | None = None,
):
    save_bundle_state(
        session,
        dealer_id,
        bundles,
        ceiling_lkr,
        chat_history,
        validation_issues,
        allow_exceed_ceiling,
        pending_review=pending_review,
    )


def _dealer_cheques_url(dealer_id: int):
    return url_for("dealers.cheques", dealer_id=dealer_id)


@bundling_bp.route("/bundling")
@login_required
def bundling_home():
    return render_template(
        "bundling.html",
        dealers=repo.get_dealers(),
        dealer_summaries=repo.get_all_dealer_summaries(),
    )


@bundling_bp.route("/bundling/<int:dealer_id>")
@login_required
def bundling_dealer(dealer_id):
    return redirect(url_for("dealers.invoices", dealer_id=dealer_id))


@bundling_bp.route("/bundling/<int:dealer_id>/compute", methods=["POST"])
@login_required
def compute(dealer_id):
    invoice_ids = [int(x) for x in request.form.getlist("invoice_ids")]
    ceiling = float(request.form.get("ceiling_lkr", 500000))
    # If nothing ticked (common after AI already grouped), use all ready invoices.
    if not invoice_ids:
        invoice_ids = [
            int(inv["invoices_id"])
            for inv in repo.get_verified_unassigned_invoices(dealer_id)
        ]
    if not invoice_ids:
        flash_t("flash_select_invoice", "error")
        return redirect(_dealer_cheques_url(dealer_id))

    bundles = compute_bundles(dealer_id, invoice_ids, ceiling)
    state = _load_state(dealer_id)
    validation_issues = collect_bundle_issues({"bundles": bundles}, dealer_id, ceiling)
    _save_state(
        dealer_id,
        bundles,
        ceiling,
        state["chat_history"],
        validation_issues,
        pending_review="compute",
    )
    flash_t("flash_bundling_complete", "success", count=len(bundles))
    return redirect(_dealer_cheques_url(dealer_id))


@bundling_bp.route("/api/chat/bundling/<int:dealer_id>/health", methods=["GET"])
@login_required
def chat_health(dealer_id):
    dealer = repo.get_dealer(dealer_id)
    if not dealer:
        return jsonify({"ok": False, "error": "dealer_not_found"}), 404
    tool_agent = False
    try:
        from agents.bundling_assistant import bundling_tool_agent_available

        tool_agent = Config.use_bundling_tool_agent() and bundling_tool_agent_available()
    except Exception:
        tool_agent = False
    return jsonify(
        {
            "ok": True,
            "dealer_id": dealer_id,
            "demo_mode": Config.use_fake_ai(),
            "bundling_tool_agent": tool_agent,
        }
    )


@bundling_bp.route("/api/chat/bundling/<int:dealer_id>", methods=["POST"])
@login_required
def chat(dealer_id):
    try:
        data = request.get_json(silent=True) or {}
        message = (data.get("message") or "").strip()
        if not message:
            return jsonify({"error": "empty_message", "reply": "Please enter a message."}), 400

        current_app.logger.info("chat POST dealer=%s message=%r", dealer_id, message[:80])
        state = _load_state(dealer_id)
        bundles = state["bundles"]
        ceiling = state["ceiling_lkr"]
        dealer = repo.get_dealer(dealer_id)
        history = list(state["chat_history"])

        if not dealer:
            return jsonify({"error": "dealer_not_found", "reply": "Dealer not found."}), 404

        lang = get_lang()
        agentic_session_id = (
            data.get("agentic_session_id")
            or session.get("agentic_session_id")
            or state.get("agentic_session_id")
        )
        from core.agentic_bundling_bridge import load_agentic_hints_for_bundling

        agentic_hints = load_agentic_hints_for_bundling(agentic_session_id)

        use_tool_agent = (
            not Config.use_fake_ai()
            and Config.use_bundling_tool_agent()
        )
        tool_trace = []
        pending_commit = False

        try:
            if Config.use_fake_ai():
                from agents.mock import mock_bundling_chat

                result = mock_bundling_chat(
                    message, dealer_id, bundles, dealer, history, ceiling, lang
                )
                use_tool_agent = False
            elif use_tool_agent:
                try:
                    from agents.bundling_assistant import (
                        bundling_tool_agent_available,
                        run_bundling_assistant,
                    )

                    if not bundling_tool_agent_available():
                        raise ImportError("LangChain tool-calling agent unavailable")
                    result = run_bundling_assistant(
                        dealer_id=dealer_id,
                        message=message,
                        chat_history=history,
                        bundles=bundles,
                        ceiling_lkr=ceiling,
                        lang=lang,
                        agentic_hints=agentic_hints,
                    )
                except ImportError:
                    use_tool_agent = False
                    from agents.assistant import bundling_chat

                    result = bundling_chat(
                        message, dealer_id, bundles, dealer, history, ceiling, lang
                    )
            else:
                from agents.assistant import bundling_chat

                result = bundling_chat(
                    message, dealer_id, bundles, dealer, history, ceiling, lang
                )
        except Exception as e:
            err = str(e)
            return jsonify({"error": err, "reply": _chat_error_hint(err)}), 500

        allow_exceed = state.get("allow_exceed_ceiling", False)
        bundling_complete = False
        validation_issues: list = []

        if use_tool_agent and "pending_commit" in result:
            # Tools already ran through Python; persist when commit/dry_run=False happened.
            bundles = result.get("bundles") or bundles
            validation_issues = list(result.get("validation_issues") or [])
            allow_exceed = bool(result.get("allow_exceed_ceiling", allow_exceed))
            pending_commit = bool(result.get("pending_commit"))
            tool_trace = result.get("tool_trace") or []
            bundling_complete = pending_commit and bool(bundles)
            if not validation_issues:
                validation_issues = collect_bundle_issues(
                    {"bundles": bundles},
                    dealer_id,
                    ceiling,
                    allow_exceed_ceiling=allow_exceed,
                )
        else:
            proposed_actions = normalize_proposed_actions(result.get("proposed_actions"))
            if not proposed_actions:
                proposed_actions = infer_bundling_actions(message, bundles, dealer_id)

            if proposed_actions:
                bundles, validation_issues, allow_exceed = apply_proposed_actions(
                    bundles, proposed_actions, dealer_id, ceiling
                )
                if not bundles:
                    fallback_actions = infer_bundling_actions(message, bundles, dealer_id)
                    if fallback_actions:
                        bundles, validation_issues, allow_exceed = apply_proposed_actions(
                            bundles, fallback_actions, dealer_id, ceiling
                        )
                bundling_complete = bool(bundles)
            else:
                validation_issues = collect_bundle_issues(
                    {"bundles": bundles},
                    dealer_id,
                    ceiling,
                    allow_exceed_ceiling=allow_exceed,
                )

        history.append({"role": "user", "content": message})
        reply = (result.get("reply") or "").strip()
        if not reply:
            reply = "I couldn't generate a reply. Please try again or reset the chat."
        if bundling_complete:
            if validation_issues:
                issue_lines = "\n".join(f"• {issue}" for issue in validation_issues)
                reply += (
                    "\n\n"
                    + translate("chat_bundling_complete_with_issues", lang, count=len(bundles))
                    + "\n\n"
                    + issue_lines
                )
            else:
                reply += "\n\n" + translate("chat_bundling_complete", lang, count=len(bundles))
        elif validation_issues and not use_tool_agent:
            issue_lines = "\n".join(f"• {issue}" for issue in validation_issues)
            reply += (
                "\n\nPython verification found these issues with this bundle proposal:\n"
                f"{issue_lines}\n\n"
                "The proposed cheques are shown on the left. Review them, ask me to adjust, "
                "or tick the warning checkbox to preview and write the cheques anyway."
            )
        history.append({"role": "assistant", "content": reply})

        _save_state(
            dealer_id,
            bundles,
            ceiling,
            history,
            validation_issues,
            allow_exceed_ceiling=allow_exceed,
        )
        payload = {
            "reply": reply,
            "bundles": bundles,
            "validation_issues": validation_issues,
            "valid": not validation_issues,
            "bundling_complete": bundling_complete,
            "demo_mode": Config.use_fake_ai(),
            "assistant": "bundling_tool_agent" if use_tool_agent else "legacy_json",
        }
        if tool_trace:
            payload["tool_trace"] = tool_trace
        return jsonify(payload)
    except Exception as e:
        return jsonify({"error": str(e), "reply": f"Server error: {str(e)[:200]}"}), 500


@bundling_bp.route("/api/chat/bundling/<int:dealer_id>/reset", methods=["POST"])
@login_required
def reset_chat(dealer_id):
    state = _load_state(dealer_id)
    _save_state(dealer_id, state["bundles"], state["ceiling_lkr"], [], pending_review=None)
    return jsonify({"ok": True})


@bundling_bp.route("/api/bundling/<int:dealer_id>/review", methods=["POST"])
@login_required
def bundle_review(dealer_id):
    try:
        data = request.get_json(silent=True) or {}
        trigger = (data.get("trigger") or "compute").strip()
        if trigger not in ("compute", "preview"):
            trigger = "compute"

        state = _load_state(dealer_id)
        bundles = state["bundles"]
        ceiling = state["ceiling_lkr"]
        if not bundles:
            return jsonify({"error": "no_bundles", "review": "No cheque bundles to review."}), 400

        dealer = repo.get_dealer(dealer_id)
        if not dealer:
            return jsonify({"error": "dealer_not_found"}), 404

        validation_issues = collect_bundle_issues(
            {"bundles": bundles},
            dealer_id,
            ceiling,
            allow_exceed_ceiling=state.get("allow_exceed_ceiling", False),
        )
        lang = get_lang()

        try:
            if Config.use_fake_ai():
                from agents.mock import mock_bundle_review

                result = mock_bundle_review(
                    dealer_id, bundles, ceiling, validation_issues, lang, trigger
                )
            else:
                from agents.reviewer import review_bundles

                result = review_bundles(
                    dealer_id, bundles, ceiling, validation_issues, lang, trigger
                )
        except Exception as e:
            err = str(e)
            return jsonify({"error": err, "review": _chat_error_hint(err)}), 500

        review_text = (result.get("review") or "").strip()
        if not review_text:
            review_text = translate("reviewer_empty", lang)

        verdict = result.get("verdict", "approve")
        history = list(state["chat_history"])
        history.append(
            {
                "role": "reviewer",
                "content": review_text,
                "trigger": trigger,
                "verdict": verdict,
                "applied": False,
            }
        )

        _save_state(
            dealer_id,
            bundles,
            ceiling,
            history,
            validation_issues,
            allow_exceed_ceiling=state.get("allow_exceed_ceiling", False),
            pending_review=None,
        )

        return jsonify(
            {
                "review": review_text,
                "verdict": verdict,
                "chat_history": history,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e), "review": f"Server error: {str(e)[:200]}"}), 500


def _find_reviewer_message(history: list, review_index: int | None) -> tuple[int, dict] | tuple[None, None]:
    if review_index is not None and review_index >= 0:
        if review_index < len(history) and history[review_index].get("role") == "reviewer":
            return review_index, history[review_index]
        return None, None
    for idx in range(len(history) - 1, -1, -1):
        msg = history[idx]
        if msg.get("role") == "reviewer" and msg.get("verdict") == "suggest_changes" and not msg.get("applied"):
            return idx, msg
    return None, None


@bundling_bp.route("/api/bundling/<int:dealer_id>/review/apply", methods=["POST"])
@login_required
def apply_bundle_review(dealer_id):
    try:
        data = request.get_json(silent=True) or {}
        review_index = data.get("review_index")
        if review_index is not None:
            review_index = int(review_index)
            if review_index < 0:
                review_index = None

        state = _load_state(dealer_id)
        bundles = state["bundles"]
        ceiling = state["ceiling_lkr"]
        history = list(state["chat_history"])

        if not bundles:
            return jsonify({"error": "no_bundles"}), 400

        idx, reviewer_msg = _find_reviewer_message(history, review_index)
        if reviewer_msg is None:
            return jsonify({"error": "no_applicable_review", "summary": translate("reviewer_apply_none", get_lang())}), 400
        if reviewer_msg.get("verdict") == "approve":
            return jsonify({"error": "review_already_approved"}), 400
        if reviewer_msg.get("applied"):
            return jsonify({"error": "review_already_applied"}), 400

        validation_issues = collect_bundle_issues(
            {"bundles": bundles},
            dealer_id,
            ceiling,
            allow_exceed_ceiling=state.get("allow_exceed_ceiling", False),
        )
        lang = get_lang()
        review_text = reviewer_msg.get("content") or ""

        try:
            if Config.use_fake_ai():
                from agents.mock import mock_apply_reviewer_suggestions

                result = mock_apply_reviewer_suggestions(
                    dealer_id, bundles, ceiling, validation_issues, review_text, lang
                )
            else:
                from agents.reviewer import apply_reviewer_suggestions

                result = apply_reviewer_suggestions(
                    dealer_id, bundles, ceiling, validation_issues, review_text, lang
                )
        except Exception as e:
            err = str(e)
            return jsonify({"error": err, "summary": _chat_error_hint(err)}), 500

        proposed_actions = normalize_proposed_actions(result.get("proposed_actions"))
        if not proposed_actions:
            return jsonify(
                {
                    "error": "no_actions",
                    "summary": translate("reviewer_apply_no_actions", lang),
                }
            ), 400

        allow_exceed = state.get("allow_exceed_ceiling", False)
        bundles, validation_issues, allow_exceed = apply_proposed_actions(
            bundles, proposed_actions, dealer_id, ceiling
        )
        if not bundles:
            return jsonify(
                {
                    "error": "apply_failed",
                    "summary": translate("reviewer_apply_failed", lang),
                }
            ), 400

        summary = (result.get("summary") or "").strip() or translate("reviewer_apply_done", lang)
        history[idx] = {**reviewer_msg, "applied": True}
        history.append({"role": "assistant", "content": summary})

        _save_state(
            dealer_id,
            bundles,
            ceiling,
            history,
            validation_issues,
            allow_exceed_ceiling=allow_exceed,
            pending_review=None,
        )

        return jsonify(
            {
                "summary": summary,
                "bundles": bundles,
                "validation_issues": validation_issues,
                "chat_history": history,
                "bundling_complete": True,
                "valid": not validation_issues,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e), "summary": f"Server error: {str(e)[:200]}"}), 500


@bundling_bp.route("/bundling/<int:dealer_id>/manual", methods=["POST"])
@login_required
def manual_bundling(dealer_id):
    data = request.get_json() or {}
    assignments = data.get("invoice_assignments", {})
    cheque_dates = data.get("cheque_dates", {})
    ceiling = float(data.get("ceiling_lkr", 500000))
    separate = data.get("one_per_invoice", False)
    empty_groups = data.get("empty_groups") or []
    invoice_parts = data.get("invoice_parts") or {}
    actions = data.get("actions") or []

    state = _load_state(dealer_id)

    # Prefer explicit actions (split / move with part_index) on current draft
    if actions:
        bundles, validation_issues, allow_exceed = apply_proposed_actions(
            state["bundles"],
            actions,
            dealer_id,
            ceiling,
        )
        _save_state(
            dealer_id,
            bundles,
            ceiling,
            state["chat_history"],
            validation_issues,
            allow_exceed_ceiling=allow_exceed or state.get("allow_exceed_ceiling", False),
        )
        return jsonify(
            {
                "bundles": bundles,
                "validation_issues": validation_issues,
                "valid": not validation_issues,
                "bundling_complete": bool(bundles),
            }
        )

    if separate and assignments:
        invoice_ids = []
        for k in assignments.keys():
            from core.invoice_parts import parse_part_key

            invoice_ids.append(parse_part_key(k)[0])
        # unique preserve order
        seen = set()
        uniq = []
        for i in invoice_ids:
            if i not in seen:
                seen.add(i)
                uniq.append(i)
        manual_assignments = {str(inv_id): i + 1 for i, inv_id in enumerate(uniq)}
        bundles = build_bundles_from_assignments(dealer_id, manual_assignments, cheque_dates, ceiling)
    elif assignments or empty_groups:
        bundles = build_bundles_from_assignments(
            dealer_id,
            assignments,
            cheque_dates,
            ceiling,
            empty_groups=empty_groups,
            invoice_parts=invoice_parts,
        )
    else:
        return jsonify({"error": "No invoice assignments provided"}), 400

    validation_issues = collect_bundle_issues({"bundles": bundles}, dealer_id, ceiling)
    _save_state(dealer_id, bundles, ceiling, state["chat_history"], validation_issues)
    return jsonify(
        {
            "bundles": bundles,
            "validation_issues": validation_issues,
            "valid": not validation_issues,
            "bundling_complete": bool(bundles),
        }
    )


@bundling_bp.route("/api/bundling/<int:dealer_id>/auto-review", methods=["POST"])
@login_required
def auto_review(dealer_id):
    state = _load_state(dealer_id)
    bundles = state["bundles"]
    ceiling = state["ceiling_lkr"]
    if not bundles:
        return jsonify({"error": "no_bundles"}), 400
    max_rounds = int((request.get_json(silent=True) or {}).get("max_rounds", 3))
    result = auto_review_until_approved(
        dealer_id,
        bundles,
        ceiling,
        lang=get_lang(),
        max_rounds=max_rounds,
        allow_exceed_ceiling=state.get("allow_exceed_ceiling", False),
    )
    history = list(state["chat_history"])
    history.append(
        {
            "role": "assistant",
            "content": f"Auto-review finished in {result['rounds']} round(s). Final verdict: {result['verdict']}.",
        }
    )
    _save_state(
        dealer_id,
        result["bundles"],
        ceiling,
        history,
        result["validation_issues"],
        allow_exceed_ceiling=result.get("allow_exceed_ceiling", False),
        pending_review=None,
    )
    return jsonify(
        {
            "bundles": result["bundles"],
            "validation_issues": result["validation_issues"],
            "verdict": result["verdict"],
            "rounds": result["rounds"],
            "history": result["history"],
            "chat_history": history,
        }
    )


@bundling_bp.route("/bundling/<int:dealer_id>/preview", methods=["POST"])
@login_required
def preview(dealer_id):
    state = _load_state(dealer_id)
    bundles = state["bundles"]
    ceiling = state["ceiling_lkr"]
    validation_issues = collect_bundle_issues({"bundles": bundles}, dealer_id, ceiling)
    acknowledge = request.form.get("acknowledge_warnings") == "1"

    if validation_issues and not acknowledge:
        flash_t("flash_review_bundle_warnings", "error")
        return redirect(_dealer_cheques_url(dealer_id))

    accounts = repo.get_bank_accounts()
    bundles_with_invoices = [b for b in bundles if b.get("invoices")]
    previews = []
    for b in bundles_with_invoices:
        previews.append(
            {
                **b,
                "amount_in_words": amount_to_words(b["total_lkr"]),
            }
        )
    session["pending_cheques"] = {
        "dealer_id": dealer_id,
        "bundles": slim_bundles(bundles_with_invoices),
        "validation_issues": validation_issues,
        "warnings_acknowledged": bool(validation_issues and acknowledge),
    }
    session.modified = True
    dealer = repo.get_dealer(dealer_id)
    return render_template(
        "cheque_preview.html",
        bundles=previews,
        dealer=dealer,
        accounts=accounts,
        default_user_bank_acc_id=dealer.get("default_user_bank_acc_id") if dealer else None,
        validation_issues=validation_issues,
        warnings_acknowledged=bool(validation_issues and acknowledge),
    )


@bundling_bp.route("/bundling/commit", methods=["POST"])
@login_required
def commit():
    pending = session.get("pending_cheques")
    if not pending:
        flash_t("flash_no_cheques", "error")
        return redirect(url_for("bundling.bundling_home"))

    dealer_id = int(pending.get("dealer_id") or 0)
    bundles = hydrate_bundles(pending.get("bundles") or [])
    bundles = [b for b in bundles if b.get("invoices")]
    if not bundles:
        flash_t("flash_no_cheques", "error")
        return redirect(
            url_for("dealers.cheques", dealer_id=dealer_id)
            if dealer_id
            else url_for("bundling.bundling_home")
        )

    bank_raw = (request.form.get("user_bank_acc_id") or "").strip()
    if not bank_raw:
        flash_t("flash_select_paying_account", "error")
        return redirect(
            url_for("dealers.cheques", dealer_id=dealer_id)
            if dealer_id
            else url_for("bundling.bundling_home")
        )
    bank_acc_id = int(bank_raw)
    if not repo.get_bank_account(bank_acc_id):
        flash_t("flash_bank_account_missing", "error")
        return redirect(
            url_for("dealers.cheques", dealer_id=dealer_id)
            if dealer_id
            else url_for("bundling.bundling_home")
        )

    cheques = []
    invoice_map = {}
    for i, b in enumerate(bundles):
        clearance = (
            b.get("predicted_clearance_date")
            or b.get("target_funding_date")
            or b.get("true_settlement_date")
            or b.get("cheque_date")
        )
        if not b.get("cheque_date") or not clearance:
            flash_t("flash_no_cheques", "error")
            return redirect(url_for("dealers.cheques", dealer_id=dealer_id))
        cheque_no = (request.form.get(f"cheque_no_{i}") or "").strip() or f"DRAFT-{i+1}"
        cheques.append(
            {
                "user_bank_acc_id": bank_acc_id,
                "cheque_no": cheque_no,
                "cheque_date": b["cheque_date"],
                "amount_in_words": amount_to_words(b["total_lkr"]),
                "amount_in_numerals": b["total_lkr"],
                "predicted_clearance_date": clearance,
            }
        )
        invoice_map[i] = [
            {
                "invoices_id": inv["invoices_id"],
                "amount": float(inv["total_amount"]),
                "part_index": int(inv.get("part_index") or 1),
                "part_count": int(inv.get("part_count") or 1),
            }
            for inv in b["invoices"]
        ]

    try:
        repo.save_cheques(cheques, invoice_map)
    except Exception:
        current_app.logger.exception("Cheque commit failed")
        flash_t("flash_cheques_commit_failed", "error")
        return redirect(url_for("dealers.cheques", dealer_id=dealer_id))

    session.pop("pending_cheques", None)
    _bundle_session().pop(str(dealer_id), None)
    try:
        repo.clear_bundle_draft(dealer_id)
    except Exception:
        current_app.logger.exception("Failed to clear bundle draft after commit")
    session.modified = True
    flash_t("flash_cheques_committed", "success")

    def run_analyst():
        try:
            from agents.analyst import build_report_markdown

            metrics = repo.get_analytics_metrics()
            report = build_report_markdown(metrics)
            repo.save_analyst_report(report)
        except Exception:
            current_app.logger.exception("Background analyst report failed")

    threading.Thread(target=run_analyst, daemon=True).start()
    return redirect(url_for("dealers.cheques", dealer_id=dealer_id))
