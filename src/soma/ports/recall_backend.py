from __future__ import annotations

from typing import Protocol

from soma.domain.query import Query, RecallAnswer


class RecallBackend(Protocol):
    def answer(self, query: Query, memory_reference: str) -> RecallAnswer: ...
