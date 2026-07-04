from __future__ import annotations

from trace_memory.store import SleepConsolidator, TraceMemoryStore
from trace_memory.store.author import deterministic_author


class StubEmbedder:
    mode = "sentence-transformer"

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [(1.0, 0.0, 0.0) for _ in texts]


def _speech_row(store: TraceMemoryStore, verbatim: str, t_ms: int, *, session: str = "walk-1",
                node_id: str | None = None):
    return store.write_observation(
        text=f'EVENT | nearby speech | transcript: "{verbatim}"',
        t_ms=t_ms,
        source="phone_camera",
        provenance={"source": "apple_speech", "source_type": "audio"},
        metadata={"helper": "apple_speech", "helper_prompt": "apple_speech",
                  "session_id": session},
        node_type="observation",
        immutable_raw=True,
        node_id=node_id,
    )


def _run(store: TraceMemoryStore):
    return SleepConsolidator(store, author=deterministic_author,
                             landmark_expansion=False).consolidate()


def test_adjacent_fragments_stitch_into_one_utterance(tmp_path) -> None:
    store = TraceMemoryStore(tmp_path / "s.sqlite3", embedder=StubEmbedder())
    try:
        # Four shreds of one sentence, 1-2s apart (< 3s gap) -> one utterance.
        _speech_row(store, "Everything I", 1000)
        _speech_row(store, "do I do it just for you", 2500)
        _speech_row(store, "You're my only", 4000)
        _speech_row(store, "This is my bathroom", 5500)
        _run(store)

        stitched = [n for n in store.nodes(node_types=("event_memory",))
                    if (n.metadata or {}).get("authored_by") == "speech_stitcher"]
        assert len(stitched) == 1
        node = stitched[0]
        # Verbatim preserved, joined in time order, no rewriting.
        assert node.text == ('EVENT | speech utterance | transcript: '
                             '"Everything I do I do it just for you '
                             'You\'re my only This is my bathroom"')
        assert node.metadata["fragment_count"] == 4
    finally:
        store.close()


def test_wide_gap_fragments_stay_separate(tmp_path) -> None:
    store = TraceMemoryStore(tmp_path / "s.sqlite3", embedder=StubEmbedder())
    try:
        # Two fragments 1s apart (merge), then a 20s gap — a real pause between remarks,
        # measured on the founder's walks at 22s/47s/63s — then two more (merge) -> two
        # utterances. Gaps of 5-7s must MERGE: the old commit cadence sliced continuous
        # narration at exactly that spacing (0 of 71 real fragments joined at 3s).
        _speech_row(store, "You have your towels you", 1000)
        _speech_row(store, "can observe yourself", 2000)
        _speech_row(store, "You have a washing machine", 22000)
        _speech_row(store, "I guess it's 1 to 8 kilograms", 23200)
        _run(store)

        stitched = sorted(
            (n for n in store.nodes(node_types=("event_memory",))
             if (n.metadata or {}).get("authored_by") == "speech_stitcher"),
            key=lambda n: n.t_ms,
        )
        assert len(stitched) == 2
        assert 'towels you can observe yourself' in stitched[0].text
        assert 'washing machine I guess it' in stitched[1].text
    finally:
        store.close()


def test_citations_intact_and_raw_untouched(tmp_path) -> None:
    store = TraceMemoryStore(tmp_path / "s.sqlite3", embedder=StubEmbedder())
    try:
        r1 = _speech_row(store, "Everything I", 1000, node_id="raw-1")
        r2 = _speech_row(store, "do it just for you", 2000, node_id="raw-2")
        raw_text_before = {r1.id: r1.text, r2.id: r2.text}
        _run(store)

        stitched = [n for n in store.nodes(node_types=("event_memory",))
                    if (n.metadata or {}).get("authored_by") == "speech_stitcher"]
        assert len(stitched) == 1
        mem = stitched[0]
        # Citation links from every fragment to the authored utterance.
        support_links = [l for l in store.links()
                         if l.link_type == "supports_memory" and l.to_id == mem.id]
        cited = {l.from_id for l in support_links}
        assert cited == {"raw-1", "raw-2"}
        assert set(mem.metadata["support_ids"]) == {"raw-1", "raw-2"}

        # Raw fragments are byte-for-byte untouched (L3) and still immutable.
        for raw_id, before in raw_text_before.items():
            row = store.read_observation(raw_id)
            assert row is not None
            assert row.text == before
            assert row.immutable_raw is True
            assert row.derived is False
    finally:
        store.close()


def test_single_fragment_is_not_authored(tmp_path) -> None:
    store = TraceMemoryStore(tmp_path / "s.sqlite3", embedder=StubEmbedder())
    try:
        _speech_row(store, "This is my bathroom", 1000)
        _run(store)
        stitched = [n for n in store.nodes(node_types=("event_memory",))
                    if (n.metadata or {}).get("authored_by") == "speech_stitcher"]
        assert stitched == []
    finally:
        store.close()


def test_reconsolidation_is_idempotent(tmp_path) -> None:
    store = TraceMemoryStore(tmp_path / "s.sqlite3", embedder=StubEmbedder())
    try:
        _speech_row(store, "Everything I", 1000)
        _speech_row(store, "do it just for you", 2000)
        _run(store)
        _run(store)  # re-run: reconsider_derived wipes + re-authors, no accretion
        stitched = [n for n in store.nodes(node_types=("event_memory",))
                    if (n.metadata or {}).get("authored_by") == "speech_stitcher"]
        assert len(stitched) == 1
    finally:
        store.close()


def test_different_sessions_do_not_merge(tmp_path) -> None:
    store = TraceMemoryStore(tmp_path / "s.sqlite3", embedder=StubEmbedder())
    try:
        _speech_row(store, "Everything I", 1000, session="walk-A")
        _speech_row(store, "do it just for you", 1500, session="walk-B")
        _run(store)
        stitched = [n for n in store.nodes(node_types=("event_memory",))
                    if (n.metadata or {}).get("authored_by") == "speech_stitcher"]
        # Same 500ms gap but different sessions -> neither run has >=2 -> nothing authored.
        assert stitched == []
    finally:
        store.close()
