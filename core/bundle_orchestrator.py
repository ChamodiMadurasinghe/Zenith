from __future__ import annotations

from agents.reviewer import apply_reviewer_suggestions, review_bundles
from core.guardrails import apply_proposed_actions, collect_bundle_issues


def auto_review_until_approved(
    dealer_id: int,
    bundles: list,
    ceiling_lkr: float,
    *,
    lang: str = "en",
    max_rounds: int = 3,
    allow_exceed_ceiling: bool = False,
) -> dict:
    history = []
    current = bundles
    verdict = "suggest_changes"
    issues = collect_bundle_issues(
        {"bundles": current},
        dealer_id,
        ceiling_lkr,
        allow_exceed_ceiling=allow_exceed_ceiling,
    )
    rounds = 0

    while rounds < max_rounds:
        rounds += 1
        review = review_bundles(dealer_id, current, ceiling_lkr, issues, lang, "compute")
        verdict = review.get("verdict", "approve")
        history.append({"round": rounds, "review": review.get("review", ""), "verdict": verdict})
        if verdict == "approve":
            break

        apply_result = apply_reviewer_suggestions(
            dealer_id,
            current,
            ceiling_lkr,
            issues,
            review.get("review", ""),
            lang,
        )
        proposed_actions = apply_result.get("proposed_actions") or []
        if not proposed_actions:
            break
        current, issues, allow_exceed_ceiling = apply_proposed_actions(
            current, proposed_actions, dealer_id, ceiling_lkr
        )
        history.append(
            {
                "round": rounds,
                "applied_actions": proposed_actions,
                "summary": apply_result.get("summary", ""),
            }
        )

    return {
        "bundles": current,
        "validation_issues": issues,
        "history": history,
        "verdict": verdict,
        "rounds": rounds,
        "allow_exceed_ceiling": allow_exceed_ceiling,
    }
