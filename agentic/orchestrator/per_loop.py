"""Plan → Execute → Review → Retry loop for one agent step."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Generic, TypeVar

from agentic.trace.agent_trace import AgentTrace

T = TypeVar("T")


@dataclass
class PERResult(Generic[T]):
    success: bool
    output: T | None
    decision: str  # continue | retry | lock | loop_to_agent3 | await_approval | fail
    retry: bool = False


class PERLoop:
    MAX_RETRIES = 3

    def __init__(self, trace: AgentTrace, agent_name: str) -> None:
        self._trace = trace
        self._agent = agent_name

    def run(
        self,
        plan_input: dict[str, Any],
        execute_fn: Callable[[], T],
        review_fn: Callable[[T], tuple[bool, str, str]],
        attempt: int = 1,
    ) -> PERResult[T]:
        self._trace.plan(
            self._agent,
            {**plan_input, "attempt": attempt},
            decision="planned",
        )

        try:
            output = execute_fn()
        except Exception as exc:
            self._trace.review(self._agent, {"error": str(exc)}, decision="fail")
            if attempt < self.MAX_RETRIES:
                self._trace.decide(self._agent, "retry", {"reason": str(exc)})
                return PERResult(success=False, output=None, decision="retry", retry=True)
            self._trace.decide(self._agent, "fail", {"reason": str(exc)})
            return PERResult(success=False, output=None, decision="fail")

        out_summary = _summarize(output)
        self._trace.execute(self._agent, plan_input, out_summary, decision="executed")

        ok, decision, reason = review_fn(output)
        self._trace.review(self._agent, {**out_summary, "reason": reason}, decision=decision)

        if not ok and attempt < self.MAX_RETRIES:
            self._trace.decide(self._agent, "retry", {"reason": reason})
            return PERResult(success=False, output=output, decision="retry", retry=True)

        self._trace.decide(self._agent, decision, out_summary)
        return PERResult(success=ok, output=output, decision=decision)


def _summarize(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "__dataclass_fields__"):
        from dataclasses import asdict

        return asdict(value)
    if isinstance(value, dict):
        return value
    return {"value": str(value)}
