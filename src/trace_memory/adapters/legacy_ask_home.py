from __future__ import annotations

from typing import Any, Protocol

from trace_memory.domain.query import Citation, Query, RecallAnswer


class AskHomeModule(Protocol):
    def ask(self, _question: str, _memory_path: str, model: str) -> dict[str, Any]: ...


class LegacyAskHome:
    """Adapter that contains the legacy module until it is carved apart."""

    def __init__(self, module: AskHomeModule, model: str) -> None:
        self._module = module
        self._model = model

    def answer(self, query: Query, memory_reference: str) -> RecallAnswer:
        result = self._module.ask(query.text, memory_reference, model=self._model)
        scenes = result.get("scenes") or []
        citations = tuple(self._citation(scene) for scene in scenes)
        return RecallAnswer(text=str(result.get("answer") or ""), citations=citations)

    @staticmethod
    def _citation(scene: dict[str, Any]) -> Citation:
        node_id = str(scene.get("frame") or scene.get("source") or "legacy-scene")
        timestamp = scene.get("t")
        t_ms = round(float(timestamp) * 1000) if timestamp is not None else None
        return Citation(node_id=node_id, t_ms=t_ms)
