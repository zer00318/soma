from __future__ import annotations

from trace_memory.store import SleepConsolidator, TraceMemoryStore


class StubEmbedder:
    mode = "sentence-transformer"

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [(1.0, 0.0, 0.0) for _ in texts]


def test_sleep_consolidator_creates_abstractions_and_links(tmp_path) -> None:
    store = TraceMemoryStore(tmp_path / "sleep.sqlite3", embedder=StubEmbedder())
    try:
        store.write_observation(
            text="entity jar | Nutella | state=empty",
            t_ms=1000,
            source="fixture.entity",
            place="shelf-a",
            provenance={"frame_support": [0]},
            node_type="entity",
        )
        store.write_observation(
            text="entity jar | Nutella | state=empty",
            t_ms=1100,
            source="fixture.entity",
            place="shelf-a",
            provenance={"frame_support": [1]},
            node_type="entity",
        )
        summary = SleepConsolidator(store).consolidate()
        abstractions = store.get_abstractions()
        links = [link for link in store.links() if link.link_type == "same_entity"]
    finally:
        store.close()

    assert summary.abstraction_count == 1
    assert summary.link_count >= 1
    assert abstractions
    assert links
