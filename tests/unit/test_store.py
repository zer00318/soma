from __future__ import annotations

from trace_memory.store import TraceMemoryStore


class StubEmbedder:
    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        vectors: list[tuple[float, ...]] = []
        for text in texts:
            lowered = text.lower()
            vectors.append(
                (
                    1.0 if "nutella" in lowered else 0.0,
                    1.0 if "jar" in lowered else 0.0,
                    1.0 if "pesto" in lowered else 0.0,
                )
            )
        return vectors


def test_write_read_search_and_neighbors(tmp_path) -> None:
    store = TraceMemoryStore(tmp_path / "trace_store.sqlite3", embedder=StubEmbedder())
    frame = store.write_observation(
        text="frame 0001 saw Nutella jar and pesto jar",
        t_ms=1000,
        source="test.frame",
        place="yaw:0|pitch:0",
        provenance={"frame": "0001"},
    )
    entity = store.write_observation(
        text="entity jar | Nutella | state=empty",
        t_ms=1000,
        source="test.entity",
        provenance={"frame_support": [0]},
        node_type="entity",
    )
    abstraction = store.write_observation(
        text="derived note: nutella jars were grouped together",
        t_ms=2000,
        source="test.sleep",
        provenance={"builder": "test"},
        node_type="abstraction",
        derived=True,
    )
    link = store.link(entity.id, frame.id, "same_entity")

    fetched = store.read_observation(entity.id)
    assert fetched is not None
    assert fetched.text == entity.text

    search = store.search("nutella jar", k=2)
    assert search.hits
    assert search.hits[0].node.id == entity.id
    assert any(found.id == link.id for found in search.links)

    neighbors = store.neighbors(entity.id)
    assert len(neighbors) == 1
    assert neighbors[0].node.id == frame.id
    assert neighbors[0].edge.link_type == "same_entity"

    abstractions = store.get_abstractions()
    assert abstractions[0].node == abstraction
    assert search.retrieval_mode == "semantic"
    assert search.degraded is False

    store.close()
