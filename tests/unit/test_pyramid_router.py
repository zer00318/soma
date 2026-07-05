from __future__ import annotations

from datetime import datetime, timedelta

from trace_memory.brain.agent import TraceMemoryAgent
from trace_memory.store import TraceMemoryStore
from trace_memory.store.digest import DigestBuilder
from trace_memory.store.episodes import EpisodeBuilder


class StubEmbedder:
    mode = "sentence-transformer"

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [(1.0, 0.0, 0.0) for _ in texts]


HINT = "GPS 48.26232, 11.67535, accuracy ~23m | Waldstrasse, Garching, Bavaria"


def _seed_yesterday(store) -> None:
    y_noon = (datetime.now() - timedelta(days=1)).replace(
        hour=12, minute=0, second=0, microsecond=0)
    base = int(y_noon.timestamp() * 1000)
    for i in range(40):
        store.write_observation(
            text="OBJECT | laptop", t_ms=base + i * 2_000, source="phone_camera",
            provenance={"location_hint": HINT}, immutable_raw=True,
        )


def test_day_question_climbs_the_digest_pyramid(tmp_path) -> None:
    store = TraceMemoryStore(tmp_path / "p.sqlite3", embedder=StubEmbedder())
    try:
        _seed_yesterday(store)
        EpisodeBuilder(store).build()
        DigestBuilder(store, use_llm=False).build()
        agent = TraceMemoryAgent(store)
        a = agent.answer("what happened yesterday")
    finally:
        store.close()

    assert a.retrieval_mode == "temporal:digest-pyramid"
    assert a.refused is False and a.confidence == 0.75
    assert a.answer.startswith("Yesterday:") and "observations" in a.answer
    assert a.evidence_chain  # bullets carry episode receipts
    assert all(e["type"] == "episode" for e in a.evidence_chain)


def test_no_digest_falls_back_to_raw_window_browse(tmp_path) -> None:
    store = TraceMemoryStore(tmp_path / "p.sqlite3", embedder=StubEmbedder())
    try:
        _seed_yesterday(store)  # raw rows only — no sleep ran
        agent = TraceMemoryAgent(store)
        a = agent.answer("what did I see yesterday")
    finally:
        store.close()

    assert a.retrieval_mode == "temporal:window-browse"
    assert a.refused is False
