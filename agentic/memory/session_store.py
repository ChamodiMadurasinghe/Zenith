"""Session-scoped agent memory between pipeline steps."""

from __future__ import annotations

from typing import Any

from agentic.contracts.repositories import InvoiceRepository


class SessionStore:
    """Read/write orchestration memory via repository."""

    def __init__(self, repo: InvoiceRepository, session_id: str) -> None:
        self._repo = repo
        self._session_id = session_id

    def get(self, key: str, default: Any = None) -> Any:
        memory = self._repo.get_agent_memory(self._session_id)
        return memory.get(key, default)

    def set(self, key: str, value: Any) -> None:
        memory = self._repo.get_agent_memory(self._session_id)
        memory[key] = value
        self._repo.set_agent_memory(self._session_id, memory)

    def update(self, updates: dict[str, Any]) -> None:
        memory = self._repo.get_agent_memory(self._session_id)
        memory.update(updates)
        self._repo.set_agent_memory(self._session_id, memory)

    def all(self) -> dict[str, Any]:
        return self._repo.get_agent_memory(self._session_id)

    def increment(self, key: str, default: int = 0) -> int:
        current = int(self.get(key, default))
        new_value = current + 1
        self.set(key, new_value)
        return new_value
