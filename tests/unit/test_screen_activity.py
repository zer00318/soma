from __future__ import annotations

from trace_memory.brain.agent import TraceMemoryAgent
from trace_memory.store import TraceMemoryStore


class StubEmbedder:
    mode = "sentence-transformer"

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [(1.0, 0.0, 0.0) for _ in texts]


CHROME = "+ Create ; Home ; Gaming ; Podcasts ; Fortnite Creative"


def _screen_row(store, t_ms, content):
    store.write_observation(
        text=f"SCREEN | app=Brave Browser window= | text: YouTube ; {content} ; "
             f"youtube.com ; {CHROME}",
        t_ms=t_ms, source="mac_screen",
        provenance={"app": "Brave Browser"}, immutable_raw=True,
    )


def test_watching_question_extracts_content_not_chrome(tmp_path) -> None:
    store = TraceMemoryStore(tmp_path / "s.sqlite3", embedder=StubEmbedder())
    try:
        base = 1_782_900_000_000
        # the founder's real case: same video title across captures, chrome everywhere
        for i in range(6):
            _screen_row(store, base + i * 60_000, "Rao Bahadur (2026) Telugu DVDS")
        _screen_row(store, base + 7 * 60_000, "Hikaru Nakamura ; Fast chess")
        agent = TraceMemoryAgent(store, restrict_sources=("mac_screen", "phone_camera"))
        a = agent.answer("What was I watching on YouTube")
    finally:
        store.close()

    assert a.retrieval_mode == "screen-activity:consensus"
    assert "Rao Bahadur (2026) Telugu DVDS" in a.answer
    assert a.answer != "YouTube" and "Gaming" not in a.answer  # never echo, never chrome
    assert a.refused is False and a.evidence_chain


def test_unseen_platform_falls_through_to_honest_paths(tmp_path) -> None:
    store = TraceMemoryStore(tmp_path / "s.sqlite3", embedder=StubEmbedder())
    try:
        _screen_row(store, 1_782_900_000_000, "Rao Bahadur (2026) Telugu DVDS")
        agent = TraceMemoryAgent(store, restrict_sources=("mac_screen", "phone_camera"))
        a = agent.answer("What was I watching on Netflix")
    finally:
        store.close()

    # no netflix rows -> the owner declines; the honest machinery answers
    assert a.retrieval_mode != "screen-activity:consensus"
    assert a.refused is True
