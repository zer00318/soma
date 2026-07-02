from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from trace_memory.store.author import LocalLLMAuthor, deterministic_author
from trace_memory.store.individuate import ObjectCluster


@dataclass
class FakeNode:
    id: str
    text: str
    t_ms: int = 0
    helper_type: str = "vlm_object"
    place: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _cluster(label, texts, kind="entity", affordance=None):
    members = [FakeNode(id=str(i), text=t, t_ms=i * 1000) for i, t in enumerate(texts)]
    return ObjectCluster(
        label=label, kind=kind, member_ids=[m.id for m in members],
        members=members, affordance=affordance,
    )


def test_deterministic_author_extracts_location_colour_and_cites():
    c = _cluster("blanket throw", [
        "grey blanket folded on bed",
        "grey blanket draped over the open blue suitcase",
    ])
    rec = deterministic_author(c)
    assert rec.support_ids == ["0", "1"]              # cites all members
    assert rec.current_location and "suitcase" in rec.current_location  # latest location wins
    assert "grey" in rec.attributes.get("colour", "")  # deterministic colour extraction is greedy
    assert "blanket" in rec.node_text().lower()


def test_deterministic_author_never_guesses_count():
    c = _cluster("nutella jar", ["a nutella jar", "another nutella jar", "nutella jar"])
    rec = deterministic_author(c)
    assert rec.count is None  # rules must not fabricate a count from observation volume


def test_node_text_includes_count_and_contradictions():
    from trace_memory.store.author import AuthoredRecord
    rec = AuthoredRecord(
        label="nutella jar", kind="entity", summary="Nutella jars on the bedside table",
        support_ids=["a"], current_location="bedside table", count=5,
        count_reasoning="2 stacked + 1 separate + 2 empty",
        contradictions=["earlier seen on desk"],
    )
    text = rec.node_text()
    assert "5" in text and "bedside table" in text and "Conflicting" in text


def test_llm_author_falls_back_to_deterministic_when_llm_unreachable():
    # Point at a dead host -> _ollama_json returns None -> deterministic record, never empty.
    author = LocalLLMAuthor(host="http://127.0.0.1:9", timeout=1)
    c = _cluster("white pillow", ["white pillow on the bed", "white pillow near headboard"])
    rec = author(c)
    assert rec.authored_by == "deterministic"
    assert rec.support_ids and rec.node_text()
