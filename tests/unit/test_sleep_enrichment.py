"""M6 seam tests — sleep-time enrichment.

  - LANDMARK EXPANSION: verbatim text read on an object gets one flagged world-knowledge
    note (cited, 'not observed'), and the note is retrievable for questions asked in
    world-vocabulary the raw capture never contained ("which university...").
  - SUCCESSION: after an object moves, the authored memory's current location is the
    LATEST place, and it supersedes earlier observations.
All deterministic (LLM stubbed).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.trace_hub import Hub  # noqa: E402
from trace_memory.brain.agent import TraceMemoryAgent  # noqa: E402
from trace_memory.store.author import deterministic_author  # noqa: E402
from trace_memory.store.sleep import SleepConsolidator  # noqa: E402


def _hub(tmp_path, rows):
    hub = Hub(str(tmp_path / "m6.sqlite3"))
    for i, (text, source, meta) in enumerate(rows):
        assert hub.ingest({"memory_text": text, "source": source,
                           "timestamp": f"2026-07-02T12:{i // 60:02d}:{i % 60:02d}.000Z",
                           "metadata": meta})["ok"]
    return hub


def _stub_landmark(verbatim, **_kwargs):
    if "michigan" in verbatim.lower():
        return "Michigan State is a large public university in East Lansing, Michigan."
    return None


def test_landmark_note_authored_and_bridges_vocabulary(tmp_path):
    hub = _hub(tmp_path, [
        ('OBJECT | sweatshirt | detected by on-device tracker | label text: "MICHIGAN STATE"; '
         "middle-center of frame | likely", "detector_track",
         {"track_id": "trk-1", "detector_label": "sweatshirt", "bound_text": "MICHIGAN STATE"}),
        ('OBJECT | sweatshirt | detected by on-device tracker | label text: "MICHIGAN STATE"; '
         "middle-center of frame | likely", "detector_track",
         {"track_id": "trk-1", "detector_label": "sweatshirt", "bound_text": "MICHIGAN STATE"}),
    ])
    SleepConsolidator(hub.store, author=deterministic_author,
                      landmark_context=_stub_landmark).consolidate()
    notes = [n for n in hub.store.nodes(node_types=("abstraction",))]
    assert len(notes) == 1
    assert "not observed" in notes[0].text and "university" in notes[0].text.lower()
    assert (notes[0].metadata or {}).get("support_ids"), "landmark note is uncited"

    # The question uses 'university' — a word the raw capture never contained.
    agent = TraceMemoryAgent(hub.store, restrict_sources=("phone_camera",))
    answer = agent.answer("Which university was on the sweatshirt?")
    joined = " ".join(str(r.get("text", "")) for r in answer.evidence_chain).lower()
    assert "michigan" in joined, f"landmark note missing from evidence: {joined[:200]}"


def test_landmark_expansion_absent_llm_is_a_noop(tmp_path):
    hub = _hub(tmp_path, [
        ('OBJECT | mug | detected by on-device tracker | label text: "ACME CO"; '
         "middle-center of frame | likely", "detector_track",
         {"track_id": "trk-2", "detector_label": "mug", "bound_text": "ACME CO"}),
    ])
    SleepConsolidator(hub.store, author=deterministic_author,
                      landmark_context=lambda *a, **k: None).consolidate()
    assert not list(hub.store.nodes(node_types=("abstraction",)))


def test_succession_current_location_is_latest(tmp_path):
    hub = _hub(tmp_path, [
        ("OBJECT | thermos | steel thermos on the desk | middle-center of frame | likely",
         "detector_track", {"track_id": "trk-3", "detector_label": "thermos"}),
        ("OBJECT | thermos | steel thermos on the desk | middle-center of frame | likely",
         "detector_track", {"track_id": "trk-3", "detector_label": "thermos"}),
        ("OBJECT | thermos | steel thermos on the kitchen shelf | middle-center of frame | likely",
         "detector_track", {"track_id": "trk-3", "detector_label": "thermos"}),
    ])
    SleepConsolidator(hub.store, author=deterministic_author,
                      landmark_expansion=False).consolidate()
    mems = [n for n in hub.store.nodes(node_types=("entity_memory",))
            if "thermos" in (n.metadata or {}).get("subject_hint", "")]
    assert mems, "no thermos memory authored"
    current = " ".join((n.metadata or {}).get("current_location") or "" for n in mems).lower()
    assert "kitchen shelf" in current, f"current location not the latest: {current!r}"
    # supersedes links point from the authored memory at the OLDER observations
    supersedes = [l for l in hub.store.links() if l.link_type == "supersedes"]
    assert supersedes, "no supersedes links authored for the moved object"
