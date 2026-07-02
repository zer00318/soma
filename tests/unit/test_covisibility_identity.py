"""M2 regression battery — object identity on real capture (canonical spec M2).

A track is a SIGHTING, not an object. Locked behaviours:
  - sequential same-label tracks with no distinctness evidence MERGE (fragmentation:
    measured 1 keyboard -> 12 tracks on the live desk store),
  - near-simultaneous tracks in non-adjacent grid cells are DISTINCT (co-visibility),
  - same-cell simultaneity is a duplicate detector box, not a second object,
  - adjacent-cell simultaneity is ambiguous -> authored as an honest count RANGE,
  - contradictory identity attributes (500g vs 825g) split even without co-visibility,
  - the sleep binder authors co-visibility-resolved counts the resolver treats as
    authoritative bounds; legacy per-track counts only widen a hedge.
"""
from __future__ import annotations

import os
import tempfile

from trace_memory.brain.agent import TraceMemoryAgent
from trace_memory.store import TraceMemoryStore
from trace_memory.store.author import deterministic_author
from trace_memory.store.individuate import individuate
from trace_memory.store.sleep import SleepConsolidator

T0 = 1_700_000_000_000


def _write(store, text, t_ms, tid, helper="detector"):
    store.write_observation(
        text=text, t_ms=t_ms, source="phone_camera", provenance={"kind": "phone_helper"},
        metadata={"helper": helper, "track_id": tid, "detector_label": text.split("|")[1].strip()
                  if "|" in text else ""},
    )


def _entity_clusters(store, label):
    return [c for c in individuate(list(store.nodes(node_types=("observation",))))
            if c.kind == "entity" and label in c.label]


def test_sequential_fragmented_tracks_merge_to_one(tmp_path):
    store = TraceMemoryStore(str(tmp_path / "a.sqlite3"))
    # 6 keyboard tracks, strictly sequential (pan away and back) — one physical keyboard.
    for i in range(6):
        t = T0 + i * 10_000
        _write(store, "OBJECT | keyboard | detected by on-device tracker | lower-center of frame | likely",
               t, f"trk-{i}")
        _write(store, "OBJECT | keyboard | detected by on-device tracker | lower-center of frame | likely",
               t + 400, f"trk-{i}")
    clusters = _entity_clusters(store, "keyboard")
    assert len(clusters) == 1, f"fragmented tracks did not merge: {len(clusters)} instances"
    assert clusters[0].instance_count == 1 and clusters[0].count_low == 1


def test_covisible_nonadjacent_cells_are_two_objects(tmp_path):
    store = TraceMemoryStore(str(tmp_path / "b.sqlite3"))
    # Two mugs visible in the SAME moment at opposite corners of the frame.
    for i in range(3):
        t = T0 + i * 500
        _write(store, "OBJECT | mug | detected by on-device tracker | upper-left of frame | likely",
               t, "trk-a")
        _write(store, "OBJECT | mug | detected by on-device tracker | lower-right of frame | likely",
               t + 100, "trk-b")
    clusters = _entity_clusters(store, "mug")
    assert len(clusters) == 2
    assert all(c.instance_count == 2 and c.count_low == 2 for c in clusters)


def test_same_cell_simultaneity_is_a_duplicate_box(tmp_path):
    store = TraceMemoryStore(str(tmp_path / "c.sqlite3"))
    for i in range(3):
        t = T0 + i * 500
        _write(store, "OBJECT | keyboard | detected by on-device tracker | middle-center of frame | likely",
               t, "trk-a")
        _write(store, "OBJECT | keyboard | detected by on-device tracker | middle-center of frame | likely",
               t + 50, "trk-b")  # duplicate box, same cell, same moment
    clusters = _entity_clusters(store, "keyboard")
    assert len(clusters) == 1 and clusters[0].count_low == 1


def test_adjacent_cell_ambiguity_authors_a_range(tmp_path):
    store = TraceMemoryStore(str(tmp_path / "d.sqlite3"))
    # Co-visible in ADJACENT cells: could be one straddling object or two. low=1, high=2.
    for i in range(3):
        t = T0 + i * 500
        _write(store, "OBJECT | keyboard | detected by on-device tracker | middle-center of frame | likely",
               t, "trk-a")
        _write(store, "OBJECT | keyboard | detected by on-device tracker | lower-right of frame | likely",
               t + 100, "trk-b")
    clusters = _entity_clusters(store, "keyboard")
    assert len(clusters) == 2  # liberal reading drives instance structure
    assert all(c.instance_count == 2 and c.count_low == 1 for c in clusters)
    # The binder authors the range; the agent answers it honestly hedged.
    SleepConsolidator(store, author=deterministic_author).consolidate()
    agent = TraceMemoryAgent(store, restrict_sources=("phone_camera",))
    answer = agent.answer("How many keyboards do I have?")
    assert answer.answer == "between 1 and 2" and answer.confidence <= 0.5


def test_attribute_contradiction_splits_without_covisibility(tmp_path):
    store = TraceMemoryStore(str(tmp_path / "e.sqlite3"))
    # Never co-visible, but 500g vs 825g cannot be the same jar.
    _write(store, "OBJECT | nutella jar | 500g classic | middle-center of frame | likely",
           T0, "trk-a", helper="vlm_object")
    _write(store, "OBJECT | nutella jar | 825g family size | middle-center of frame | likely",
           T0 + 60_000, "trk-b", helper="vlm_object")
    clusters = _entity_clusters(store, "nutella jar")
    assert len(clusters) == 2
    assert all(c.count_low == 2 for c in clusters)


def test_resolved_count_is_authoritative_for_the_agent(tmp_path):
    store = TraceMemoryStore(str(tmp_path / "f.sqlite3"))
    # Two co-visible cups (non-adjacent cells) -> binder authors exact resolved count 2;
    # the agent answers a FIRM 2 even though attribute clustering alone would say 1.
    for i in range(3):
        t = T0 + i * 500
        _write(store, "OBJECT | cup | detected by on-device tracker | upper-left of frame | likely",
               t, "trk-a")
        _write(store, "OBJECT | cup | detected by on-device tracker | lower-right of frame | likely",
               t + 100, "trk-b")
    SleepConsolidator(store, author=deterministic_author).consolidate()
    agent = TraceMemoryAgent(store, restrict_sources=("phone_camera",))
    answer = agent.answer("How many cups did you see?")
    assert answer.answer == "2" and answer.confidence == 0.8
