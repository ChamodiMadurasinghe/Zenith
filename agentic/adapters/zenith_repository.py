"""Repository adapter — orchestration memory/trace in-process; holidays from Zenith DB."""

from __future__ import annotations

import copy
from datetime import date
from typing import Any

from agentic.adapters.in_memory_repo import InMemoryRepository
from agentic.contracts.models import InvoiceDraft


class ZenithAgenticRepository(InMemoryRepository):
    """
    Extends in-memory orchestration store with Zenith DB reads.

    Does not modify db/repositories.py — only calls existing get_holidays().
    """

    def get_holidays(self) -> list[str]:
        try:
            from db import repositories as zenith_repo

            raw = zenith_repo.get_holidays()
            return sorted(str(d) for d in raw)
        except Exception:
            return super().get_holidays()

    def get_holidays_as_dates(self) -> list[date]:
        result = []
        for h in self.get_holidays():
            try:
                result.append(date.fromisoformat(h[:10]))
            except ValueError:
                continue
        return result
