from __future__ import annotations

from trace_memory.store import TraceMemoryStore
from trace_memory.store.retrieval import precise_retrieve


class StubEmbedder:
    """Deterministic 3-dim bag: [water, bottle, nutella]."""

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        out: list[tuple[float, ...]] = []
        for text in texts:
            low = text.lower()
            out.append((
                1.0 if "water" in low else 0.0,
                1.0 if "bottle" in low else 0.0,
                1.0 if "nutella" in low else 0.0,
            ))
        return out


def _seed_store(tmp_path):
    store = TraceMemoryStore(tmp_path / "precise.sqlite3", embedder=StubEmbedder())
    bottle = store.write_observation(
        text="A steel water bottle stands on the bedside table.",
        t_ms=1000, source="phone_camera", provenance={"frame": "0001"},
    )
    # context that should ride along via a co-occurrence link, not via the query embedding
    glass = store.write_observation(
        text="A clear drinking glass sits beside it.",
        t_ms=1001, source="phone_camera", provenance={"frame": "0001"},
    )
    nutella = store.write_observation(
        text="A Nutella jar on the dresser.",
        t_ms=2000, source="phone_camera", provenance={"frame": "0050"},
    )
    composed = store.write_observation(
        text="Entity: bedside table cluster.",
        t_ms=1002, source="phone_camera", node_type="entity_memory",
        derived=True, provenance={"composed": True},
    )
    store.link(bottle.id, glass.id, "candidate_same_context", weight=0.8)
    store.link(bottle.id, composed.id, "supports_memory", weight=1.0)
    return store, bottle, glass, nutella, composed


def test_precise_retrieve_surfaces_raw_observation_for_query(tmp_path) -> None:
    store, bottle, glass, nutella, composed = _seed_store(tmp_path)
    sl = precise_retrieve(store, "how can I drink water", sources=["phone_camera"])
    # the raw bottle observation must be in the slice (not only the composed memory)
    assert bottle.id in sl.ids
    top = sl.nodes[0]
    assert top.node.id == bottle.id and top.reason == "seed"
    assert "bottle" in top.node.text.lower()


def test_precise_retrieve_expands_along_links(tmp_path) -> None:
    store, bottle, glass, nutella, composed = _seed_store(tmp_path)
    sl = precise_retrieve(store, "water bottle", sources=["phone_camera"])
    by_id = {item.node.id: item for item in sl.nodes}
    # the co-occurring glass has no query-term overlap; it should arrive via expansion
    assert glass.id in by_id
    assert by_id[glass.id].reason.startswith("expand")
    # provenance survives into the rendered slice
    assert "frame=" in sl.render()


def test_precise_retrieve_trims_to_minimal_slice(tmp_path) -> None:
    store, *_ = _seed_store(tmp_path)
    sl = precise_retrieve(store, "water bottle", sources=["phone_camera"], max_nodes=2)
    assert len(sl.nodes) == 2
