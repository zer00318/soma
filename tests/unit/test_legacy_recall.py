from __future__ import annotations

from typing import Any

from trace_memory.adapters.legacy_ask_home import LegacyAskHome
from trace_memory.application import Recall
from trace_memory.domain import Query


class FakeAskHome:
    def ask(self, question: str, memory_path: str, model: str) -> dict[str, Any]:
        assert (question, memory_path, model) == ("Where?", "memory.json", "test")
        return {
            "answer": "On the desk.",
            "scenes": [{"frame": "frame-1", "t": 1.25}],
        }


def test_recall_wraps_legacy_answer_and_citations() -> None:
    recall = Recall(LegacyAskHome(FakeAskHome(), model="test"))

    answer = recall.execute(Query("Where?"), "memory.json")

    assert answer.text == "On the desk."
    assert answer.citations[0].node_id == "frame-1"
    assert answer.citations[0].t_ms == 1250
