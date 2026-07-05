"""3-day-scale probe regressions (2026-07-04) — multi-day temporal semantics.

The probe (evaluation/scale_probe_3day.py, 23k rows) caught two firm-wrong-class defects
that only surface when the store spans days:
  - 'what did I see yesterday' refused with 21k rows dated yesterday (S1 grounded on the
    literal token "yesterday"; temporal words are WHEN, never WHAT),
  - 'did I see the laptop before the bed' (plain form, no "or after") fell to the
    EXISTENCE owner, which read "laptop before bed" as ONE subject and authored a firm
    wrong "No — I have no record of laptop before bed" @0.75.
Locked here: the window-browse owner, temporal grounding exclusion, plain-form order
routing, and the existence owner's refusal to own comparison phrases.
"""
from __future__ import annotations

import time

from trace_memory.brain import TraceMemoryAgent
from trace_memory.store import TraceMemoryStore

NOW_MS = int(time.time() * 1000)
DAY_MS = 24 * 3600 * 1000


def _write(store, text, t_ms, helper="detector", label=None, tid="trk-1"):
    meta = {"helper": helper, "track_id": tid}
    if label:
        meta["detector_label"] = label
    store.write_observation(
        text=text, t_ms=t_ms, source="phone_camera",
        provenance={"kind": "phone_helper"}, metadata=meta,
    )


def test_yesterday_browse_summarizes_the_window(tmp_path):
    store = TraceMemoryStore(tmp_path / "s.sqlite3")
    for i in range(4):
        _write(store, "OBJECT | bottle | detected by on-device tracker",
               NOW_MS - DAY_MS + i * 60_000, label="bottle", tid=f"trk-{i}")
    _write(store, "OBJECT | laptop | detected by on-device tracker",
           NOW_MS - DAY_MS + 300_000, label="laptop", tid="trk-9")
    agent = TraceMemoryAgent(store, reasoner="heuristic")
    a = agent.answer("what did I see yesterday?")
    assert not a.refused
    assert "Yesterday" in a.answer and "bottle" in a.answer
    assert a.retrieval_mode == "temporal:window-browse"
    assert a.evidence_chain  # receipts, always


def test_empty_yesterday_refuses_honestly(tmp_path):
    store = TraceMemoryStore(tmp_path / "s.sqlite3")
    _write(store, "OBJECT | bottle | detected by on-device tracker", NOW_MS, label="bottle")
    agent = TraceMemoryAgent(store, reasoner="heuristic")
    a = agent.answer("what did I see yesterday?")
    assert a.refused
    assert "no memories" in a.answer


def test_subjectful_temporal_question_is_not_browsed(tmp_path):
    store = TraceMemoryStore(tmp_path / "s.sqlite3")
    _write(store, "OBJECT | truck | detected by on-device tracker",
           NOW_MS - DAY_MS + 60_000, label="truck")
    agent = TraceMemoryAgent(store, reasoner="heuristic")
    a = agent.answer("did I see a truck yesterday?")
    # The existence owner keeps subject-ful questions; browse must not swallow them.
    assert a.retrieval_mode != "temporal:window-browse"
    assert not a.refused and "truck" in a.answer.lower()


def test_plain_before_question_gets_the_order_owner(tmp_path):
    store = TraceMemoryStore(tmp_path / "s.sqlite3")
    _write(store, "OBJECT | laptop | detected by on-device tracker",
           NOW_MS - 3_600_000, label="laptop", tid="trk-1")
    _write(store, "OBJECT | bed | detected by on-device tracker",
           NOW_MS - 600_000, label="bed", tid="trk-2")
    agent = TraceMemoryAgent(store, reasoner="heuristic")
    a = agent.answer("did I see the laptop before the bed?")
    assert a.retrieval_mode == "temporal:deterministic-order"
    assert "before" in a.answer


def test_order_phrase_never_becomes_a_firm_existence_no(tmp_path):
    store = TraceMemoryStore(tmp_path / "s.sqlite3")
    # Neither object observed: the order owner falls through (honest), and the existence
    # owner must NOT author "No — I have no record of laptop before bed".
    _write(store, "OBJECT | mug | detected by on-device tracker", NOW_MS, label="mug")
    agent = TraceMemoryAgent(store, reasoner="heuristic")
    a = agent.answer("did I see the laptop before the bed?")
    assert "no record of laptop before bed" not in a.answer.lower()


def test_still_at_says_no_after_a_move(tmp_path):
    # TP03's shape: thermos seen on the desk, then later on the kitchen shelf. The LLM
    # narrated the stale desk sightings as the present (@0.7, nightly gate 2026-07-04);
    # the deterministic owner must answer from the LATEST sighting.
    store = TraceMemoryStore(tmp_path / "s.sqlite3")
    _write(store, "OBJECT | thermos | steel thermos on the desk | likely",
           NOW_MS - 600_000, label="thermos")
    _write(store, "OBJECT | thermos | steel thermos on the kitchen shelf | likely",
           NOW_MS - 60_000, label="thermos")
    agent = TraceMemoryAgent(store, reasoner="heuristic")
    a = agent.answer("Is the thermos still on the desk?")
    assert a.retrieval_mode == "move:deterministic-latest-location"
    assert a.answer.lower().startswith("no")
    assert "kitchen shelf" in a.answer.lower()


def test_still_at_says_yes_when_it_never_moved(tmp_path):
    store = TraceMemoryStore(tmp_path / "s.sqlite3")
    _write(store, "OBJECT | thermos | steel thermos on the desk | likely",
           NOW_MS - 600_000, label="thermos")
    _write(store, "OBJECT | thermos | steel thermos on the desk | likely",
           NOW_MS - 60_000, label="thermos")
    agent = TraceMemoryAgent(store, reasoner="heuristic")
    a = agent.answer("Is the thermos still on the desk?")
    assert a.retrieval_mode == "move:deterministic-latest-location"
    assert a.answer.lower().startswith("yes")


def test_still_at_never_witnessed_place_falls_through(tmp_path):
    # Thermos exists but was NEVER seen on the piano — the owner must not invent a move
    # story; absence keeps its honest owners downstream.
    store = TraceMemoryStore(tmp_path / "s.sqlite3")
    _write(store, "OBJECT | thermos | steel thermos on the desk | likely",
           NOW_MS - 60_000, label="thermos")
    agent = TraceMemoryAgent(store, reasoner="heuristic")
    a = agent.answer("Is the thermos still on the piano?")
    assert a.retrieval_mode != "move:deterministic-latest-location"
