from __future__ import annotations

from trace_memory.store import EpisodeBuilder, TraceMemoryStore


class StubEmbedder:
    mode = "sentence-transformer"

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [(1.0, 0.0, 0.0) for _ in texts]


DESK = "GPS 48.26232, 11.67535, accuracy ~23m | Waldstrasse, Garching, Bavaria"
LAB = "GPS 48.29901, 11.66802, accuracy ~15m | Boltzmannstrasse, Garching, Bavaria"


def _write_raw(store, t_ms: int, hint: str = DESK, text: str = "OBJECT | laptop") -> None:
    store.write_observation(
        text=text,
        t_ms=t_ms,
        source="phone_camera",
        provenance={"location_hint": hint},
        immutable_raw=True,
    )


def _episodes(store):
    nodes = [n for n in store.nodes(node_types=["episode"])]
    return (
        [n for n in nodes if n.metadata.get("kind") == "episode"],
        [n for n in nodes if n.metadata.get("kind") == "gap"],
    )


def test_hard_gap_splits_and_authors_honest_gap(tmp_path) -> None:
    store = TraceMemoryStore(tmp_path / "e.sqlite3", embedder=StubEmbedder())
    try:
        base = 1_782_900_000_000
        for i in range(5):
            _write_raw(store, base + i * 2_000)
        # 20 minutes of blindness, then a second burst
        for i in range(5):
            _write_raw(store, base + 1_200_000 + i * 2_000)
        summary = EpisodeBuilder(store).build()
        episodes, gaps = _episodes(store)
    finally:
        store.close()

    assert summary.episode_count == 2 and len(episodes) == 2
    assert summary.gap_count == 1 and len(gaps) == 1
    gap = gaps[0]
    assert "no capture" in gap.text and "19m" in gap.text
    assert gap.time_range.end_ms - gap.time_range.start_ms == 1_200_000 - 8_000
    for ep in episodes:
        assert ep.derived and ep.node_type == "episode"
        assert ep.metadata["observation_count"] == 5


def test_soft_gap_splits_only_with_place_corroboration(tmp_path) -> None:
    store = TraceMemoryStore(tmp_path / "e.sqlite3", embedder=StubEmbedder())
    try:
        base = 1_782_900_000_000
        # same place, 2min pause: ambiguous band -> ONE episode
        _write_raw(store, base)
        _write_raw(store, base + 120_000)
        builder = EpisodeBuilder(store)
        one = builder.build()
        # rebuild with a place CHANGE across the same 2min pause -> TWO episodes
        _write_raw(store, base + 240_000, hint=LAB)
        two = builder.build()
        episodes, gaps = _episodes(store)
    finally:
        store.close()

    assert one.episode_count == 1
    assert two.episode_count == 2
    # sub-5min pause is a boundary, not blindness: no gap episode authored
    assert two.gap_count == 0 and not gaps
    assert episodes[-1].metadata["place"] == "Boltzmannstrasse"


def test_rebuild_reconsiders_instead_of_duplicating(tmp_path) -> None:
    store = TraceMemoryStore(tmp_path / "e.sqlite3", embedder=StubEmbedder())
    try:
        base = 1_782_900_000_000
        for i in range(3):
            _write_raw(store, base + i * 1_000)
        builder = EpisodeBuilder(store)
        builder.build()
        second = builder.build()
        episodes, gaps = _episodes(store)
        raw = [n for n in store.nodes() if not n.derived]
    finally:
        store.close()

    assert second.reconsidered == 1  # first run's episode was reconsidered, not kept
    assert len(episodes) == 1 and not gaps
    assert len(raw) == 3  # raw capture untouched — never-delete law
