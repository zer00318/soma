from __future__ import annotations

from trace_memory.brain import TraceMemoryAgent
from trace_memory.store import TraceMemoryStore


class StubEmbedder:
    mode = "sentence-transformer"

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        vectors: list[tuple[float, ...]] = []
        for text in texts:
            lowered = text.lower()
            vectors.append(
                (
                    1.0 if "nutella" in lowered else 0.0,
                    1.0 if "jar" in lowered else 0.0,
                    1.0 if "green" in lowered else 0.0,
                )
            )
        return vectors


def test_agent_answers_count_and_attribute_questions(tmp_path) -> None:
    store = TraceMemoryStore(tmp_path / "agent.sqlite3", embedder=StubEmbedder())
    try:
        store.write_observation(
            text="entity jar | Nutella | state=empty",
            t_ms=1000,
            source="fixture.entity",
            provenance={"frame_support": [0]},
            node_type="entity",
            metadata={"label": "Nutella", "attrs": {"state": "empty"}},
        )
        store.write_observation(
            text="entity ring | gemstone | colour=green",
            t_ms=1200,
            source="fixture.entity",
            provenance={"frame_support": [1]},
            node_type="entity",
            metadata={"label": "gemstone ring", "attrs": {"colour": "green"}},
        )
        agent = TraceMemoryAgent(store)
        count_answer = agent.answer("How many nutella jars are there?")
        colour_answer = agent.answer("What colour are the gemstones on the rings?")
    finally:
        store.close()

    assert count_answer.answer == "1"
    assert count_answer.refused is False
    assert count_answer.evidence_chain
    assert colour_answer.answer == "Green"
    assert colour_answer.refused is False
