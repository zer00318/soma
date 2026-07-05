from __future__ import annotations

from trace_memory.store import TraceMemoryStore
from trace_memory.store.digest import DigestBuilder
from trace_memory.store.episodes import EpisodeBuilder


class StubEmbedder:
    mode = "sentence-transformer"

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [(1.0, 0.0, 0.0) for _ in texts]


DESK = "GPS 48.26232, 11.67535, accuracy ~23m | Waldstrasse, Garching, Bavaria"


def _write_raw(store, t_ms: int) -> None:
    store.write_observation(
        text="OBJECT | laptop",
        t_ms=t_ms,
        source="phone_camera",
        provenance={"location_hint": DESK},
        immutable_raw=True,
    )


def _build_day(store, base_ms: int, obs: int) -> None:
    for i in range(obs):
        _write_raw(store, base_ms + i * 2_000)


def test_digest_cites_episodes_and_marks_thin_days(tmp_path) -> None:
    store = TraceMemoryStore(tmp_path / "d.sqlite3", embedder=StubEmbedder())
    try:
        rich_day = 1_782_900_000_000  # 2026-07-01
        thin_day = rich_day + 86_400_000
        _build_day(store, rich_day, 40)  # one rich episode
        _build_day(store, rich_day + 1_200_000, 35)  # second episode + gap between
        _build_day(store, thin_day, 4)  # thin day
        EpisodeBuilder(store).build()
        summary = DigestBuilder(store, use_llm=False).build()
        digests = store.nodes(node_types=["digest_day"])
    finally:
        store.close()

    assert summary.day_count == 2 and len(digests) == 2
    assert summary.thin_day_count == 1

    rich, thin = digests
    episode_ids_cited = {i for b in rich.metadata["bullets"] for i in b["episode_ids"]}
    assert rich.metadata["episode_count"] == 2
    assert len(episode_ids_cited) == 2  # every bullet carries receipts
    assert all(b["episode_ids"] for b in rich.metadata["bullets"])
    assert "blind:" in rich.text  # in-day gap is reported, not hidden

    assert thin.metadata["thin_day"] is True
    assert "Mostly uncaptured" in thin.text


def test_digest_rebuild_is_reconsidered_not_duplicated(tmp_path) -> None:
    store = TraceMemoryStore(tmp_path / "d.sqlite3", embedder=StubEmbedder())
    try:
        _build_day(store, 1_782_900_000_000, 40)
        EpisodeBuilder(store).build()
        builder = DigestBuilder(store, use_llm=False)
        builder.build()
        second = builder.build()
        digests = store.nodes(node_types=["digest_day"])
    finally:
        store.close()

    assert second.reconsidered == 1
    assert len(digests) == 1
