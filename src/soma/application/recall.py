from __future__ import annotations

from soma.domain.query import Query, RecallAnswer
from soma.ports.recall_backend import RecallBackend


class Recall:
    """Strangler boundary around the current answer implementation."""

    def __init__(self, backend: RecallBackend) -> None:
        self._backend = backend

    def execute(self, query: Query, memory_reference: str) -> RecallAnswer:
        return self._backend.answer(query, memory_reference)
