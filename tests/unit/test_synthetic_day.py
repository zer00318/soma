"""P34 — the synthetic day: end-to-end truth the system cannot argue with.

Founder order 2026-07-06: author our OWN adversarial cases per architecture
(binder, episodes, digest, brain) instead of waiting for real days. This
harness GENERATES a full synthetic day with KNOWN ground truth — a morning
desk session (physical), a browsing session (digital, two sites, one active
tab), a walk (place change), an evening video session — runs the WHOLE
pipeline (episodes → digest → pyramid → owners → slices) and asserts what a
non-dumb brain must get right. Every case here is a contract, not a vibe.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from trace_memory.brain.agent import TraceMemoryAgent
from trace_memory.brain.slices import build_slice
from trace_memory.store import TraceMemoryStore
from trace_memory.store.digest import DigestBuilder
from trace_memory.store.episodes import EpisodeBuilder


class StubEmbedder:
    mode = "sentence-transformer"

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [(1.0, 0.0, 0.0) for _ in texts]


DESK = "GPS 48.26232, 11.67535, accuracy ~23m | Waldstrasse, Garching, Bavaria"
LAB = "GPS 48.29901, 11.66802, accuracy ~15m | Boltzmannstrasse, Garching, Bavaria"


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def build_synthetic_day(store) -> dict:
    """One believable day; returns the ground truth the assertions use."""
    day = (datetime.now() - timedelta(days=1)).replace(
        hour=8, minute=0, second=0, microsecond=0)

    # 08:00 desk session: laptop + TWO mugs (binder truth: 2 distinct mugs)
    t = day
    for i in range(30):
        store.write_observation(
            text="OBJECT | laptop | on the desk", t_ms=_ms(t) + i * 2_000,
            source="phone_camera", provenance={"location_hint": DESK},
            metadata={"detector_label": "laptop", "track_id": "trk-lap-1", "helper": "detector"},
            immutable_raw=True)
    for i in range(10):
        store.write_observation(
            text="OBJECT | mug | middle-left of frame", t_ms=_ms(t) + i * 3_000,
            source="phone_camera", provenance={"location_hint": DESK},
            metadata={"detector_label": "mug", "track_id": "trk-mug-1", "helper": "detector"},
            immutable_raw=True)
        store.write_observation(
            text="OBJECT | mug | middle-right of frame", t_ms=_ms(t) + i * 3_000 + 100,
            source="phone_camera", provenance={"location_hint": DESK},
            metadata={"detector_label": "mug", "track_id": "trk-mug-2", "helper": "detector"},
            immutable_raw=True)

    # 10:30 browsing session (after a 2.5h gap): docs on site A (main),
    # while site B exists only as another tab (top-chrome region)
    t2 = day.replace(hour=10, minute=30)
    for i in range(12):
        store.write_observation(
            text="SCREEN | app=Brave Browser | url=https://docs.python.org/3/library/sqlite3.html"
                 " | region=main | text: sqlite3 — DB-API interface ; connection objects",
            t_ms=_ms(t2) + i * 30_000, source="mac_screen",
            provenance={"app": "Brave Browser",
                        "url": "https://docs.python.org/3/library/sqlite3.html",
                        "region": "main"},
            immutable_raw=True)
        store.write_observation(
            text="SCREEN | app=Brave Browser | url=https://docs.python.org/3/library/sqlite3.html"
                 " | region=top-chrome | text: Recipe: overnight oats — tasty.example",
            t_ms=_ms(t2) + i * 30_000 + 200, source="mac_screen",
            provenance={"app": "Brave Browser",
                        "url": "https://docs.python.org/3/library/sqlite3.html",
                        "region": "top-chrome"},
            immutable_raw=True)

    # 14:00 walk to the lab (place change after gap)
    t3 = day.replace(hour=14, minute=0)
    for i in range(8):
        store.write_observation(
            text="OBJECT | bicycle | passing", t_ms=_ms(t3) + i * 5_000,
            source="phone_camera", provenance={"location_hint": LAB},
            metadata={"detector_label": "bicycle", "helper": "detector", "track_id": "trk-bike-1"}, immutable_raw=True)

    return {
        "day": day.date().isoformat(),
        "desk_start": _ms(day), "browse_start": _ms(t2), "lab_start": _ms(t3),
        "mug_count": 2, "main_site": "docs.python.org",
        "tab_only_text": "overnight oats",
    }


def _pipeline(tmp_path):
    store = TraceMemoryStore(tmp_path / "day.sqlite3", embedder=StubEmbedder())
    truth = build_synthetic_day(store)
    # mirror the REAL nightly exactly: consolidate (binder/individuation),
    # then episodes, then digests — a partial pipeline tests a fiction.
    from trace_memory.store.author import deterministic_author
    from trace_memory.store.sleep import SleepConsolidator
    SleepConsolidator(store, author=deterministic_author).consolidate()
    EpisodeBuilder(store).build()
    DigestBuilder(store, use_llm=False).build()
    return store, truth


def test_episodes_segment_the_day_with_honest_gaps(tmp_path):
    store, truth = _pipeline(tmp_path)
    try:
        eps = [n for n in store.nodes(node_types=["episode"])
               if n.metadata.get("kind") == "episode"
               and n.metadata.get("day") == truth["day"]]
        gaps = [n for n in store.nodes(node_types=["episode"])
                if n.metadata.get("kind") == "gap"
                and n.metadata.get("day") == truth["day"]]
    finally:
        store.close()
    assert len(eps) == 3          # desk, browse, lab — no more, no less
    assert len(gaps) >= 2         # the 2.5h and 3h holes are episodes too
    # the browsing episode is named by its SITE, not by channel telemetry
    browse = next(e for e in eps if e.t_ms == truth["browse_start"])
    assert "docs.python.org" in browse.metadata["label"]
    assert browse.metadata["containers"].get("docs.python.org")


def test_digest_names_sites_and_places_not_telemetry(tmp_path):
    store, truth = _pipeline(tmp_path)
    try:
        digest = next(n for n in store.nodes(node_types=["digest_day"])
                      if n.metadata.get("day") == truth["day"])
    finally:
        store.close()
    assert "docs.python.org" in digest.text     # life, not "object and track data"
    assert "Waldstrasse" in digest.text
    assert all(b["episode_ids"] for b in digest.metadata["bullets"])


def test_slice_keeps_tab_text_out_of_main(tmp_path):
    store, truth = _pipeline(tmp_path)
    try:
        rows = [n for n in store.nodes() if not n.derived
                and n.t_ms >= truth["browse_start"]]
        scene = build_slice(rows)
    finally:
        store.close()
    main_block = scene.rendered.split("region:main")[1].split("▸")[0]
    assert "sqlite3" in main_block
    assert truth["tab_only_text"] not in main_block  # the founder's Rao-Bahadur law


def test_brain_counts_the_two_mugs_and_refuses_the_absent(tmp_path):
    store, truth = _pipeline(tmp_path)
    try:
        agent = TraceMemoryAgent(store, restrict_sources=("phone_camera", "mac_screen"))
        mugs = agent.answer("how many mugs are on the desk")
        unicorn = agent.answer("how many unicorns are on the desk")
        yesterday = agent.answer("what happened yesterday")
    finally:
        store.close()
    # binder truth: two tracks, two positions -> the answer must include 2
    assert not mugs.refused and "2" in mugs.answer
    # absence stays absent — the unicorn law
    assert unicorn.refused or "no" in unicorn.answer.lower() \
        or "0" in unicorn.answer or "not" in unicorn.answer.lower()
    # the pyramid serves the day from its digest
    assert yesterday.retrieval_mode == "temporal:digest-pyramid"
    assert "docs.python.org" in yesterday.answer


def test_unknown_cell_simultaneity_hedges_never_firm_wrong(tmp_path):
    """Two tracks alive at the same instant with NO cell info: dup-box vs two
    objects is unknowable — the answer must be a hedged range containing the
    truth, never a firm single number (the harness's first catch: '1' @0.8)."""
    store = TraceMemoryStore(tmp_path / "amb.sqlite3", embedder=StubEmbedder())
    try:
        base = 1_782_900_000_000
        for i in range(10):
            for tid in ("trk-a", "trk-b"):
                store.write_observation(
                    text="OBJECT | plant | on the shelf", t_ms=base + i * 3_000
                    + (0 if tid == "trk-a" else 100),
                    source="phone_camera", provenance={"location_hint": DESK},
                    metadata={"detector_label": "plant", "track_id": tid,
                              "helper": "detector"},
                    immutable_raw=True)
        from trace_memory.store.author import deterministic_author
        from trace_memory.store.sleep import SleepConsolidator
        SleepConsolidator(store, author=deterministic_author).consolidate()
        agent = TraceMemoryAgent(store, restrict_sources=("phone_camera",))
        a = agent.answer("how many plants are on the shelf")
    finally:
        store.close()
    assert not a.refused
    assert "1" in a.answer and "2" in a.answer  # a range spanning the ambiguity
    assert a.confidence < 0.7                   # hedged, never firm
