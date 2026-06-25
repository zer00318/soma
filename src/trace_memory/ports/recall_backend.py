from __future__ import annotations

from typing import Protocol

from trace_memory.domain.query import Query, RecallAnswer


class RecallBackend(Protocol):
    def answer(self, query: Query, memory_reference: str) -> RecallAnswer: ...
