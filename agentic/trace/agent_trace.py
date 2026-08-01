"""Agent trace logger — records Plan/Execute/Review/Decide for judges and UI."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class TraceStep:
    """One observable step in the agent pipeline."""

    agent: str
    phase: str  # plan | execute | review | decide
    decision: str
    input_summary: dict[str, Any] = field(default_factory=dict)
    output_summary: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AgentTrace:
    """
    Append-only trace log for a session.

    Backend exposes via GET /api/sessions/{id}/trace using repository.get_trace().
    """

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._steps: list[TraceStep] = []

    @property
    def steps(self) -> list[TraceStep]:
        return list(self._steps)

    def log(
        self,
        agent: str,
        phase: str,
        decision: str,
        input_summary: dict[str, Any] | None = None,
        output_summary: dict[str, Any] | None = None,
    ) -> TraceStep:
        step = TraceStep(
            agent=agent,
            phase=phase,
            decision=decision,
            input_summary=input_summary or {},
            output_summary=output_summary or {},
        )
        self._steps.append(step)
        return step

    def plan(
        self,
        agent: str,
        input_summary: dict[str, Any],
        decision: str = "planned",
    ) -> TraceStep:
        return self.log(agent, "plan", decision, input_summary=input_summary)

    def execute(
        self,
        agent: str,
        input_summary: dict[str, Any],
        output_summary: dict[str, Any],
        decision: str = "executed",
    ) -> TraceStep:
        return self.log(
            agent, "execute", decision,
            input_summary=input_summary,
            output_summary=output_summary,
        )

    def review(
        self,
        agent: str,
        output_summary: dict[str, Any],
        decision: str,
    ) -> TraceStep:
        return self.log(
            agent, "review", decision,
            output_summary=output_summary,
        )

    def decide(
        self,
        agent: str,
        decision: str,
        output_summary: dict[str, Any] | None = None,
    ) -> TraceStep:
        return self.log(
            agent, "decide", decision,
            output_summary=output_summary or {},
        )

    def to_list(self) -> list[dict[str, Any]]:
        return [step.to_dict() for step in self._steps]

    def load_from_dicts(self, steps: list[dict[str, Any]]) -> None:
        self._steps = [TraceStep(**step) for step in steps]
