"""M4 seam tests — OCR text bound to a track on-device must serve brand questions and must
never leak into counting.

The app now emits `OBJECT | drill | detected by on-device tracker | label text: "DEWALT 20V
MAX"; ...` when an OCR box intersects the track's box. Locked behaviours:
  - the bound row is retrieved as evidence for a brand question about that object,
  - digits inside bound label text are VERBATIM WORLD TEXT for the count floor
    (a bus-stop sign bound to a toy bus must not floor 'how many buses' at 5),
  - the bound text joins the track instance's attribute signature downstream (desc).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.trace_hub import Hub  # noqa: E402
from trace_memory.brain.agent import TraceMemoryAgent  # noqa: E402
from trace_memory.store import TraceMemoryStore  # noqa: E402
from trace_memory.store import permanence  # noqa: E402


def _hub_store(tmp_path, rows):
    hub = Hub(str(tmp_path / "m4.sqlite3"))
    for i, (text, source, meta) in enumerate(rows):
        r = hub.ingest({
            "memory_text": text, "source": source,
            "timestamp": f"2026-07-02T10:00:{i:02d}.000Z", "metadata": meta,
        })
        assert r["ok"]
    return hub.store


DRILL_ROW = ('OBJECT | drill | detected by on-device tracker | label text: "DEWALT 20V MAX XR"; '
             "middle-center of frame; visible frame | likely")


def test_bound_brand_text_reaches_brand_question_evidence(tmp_path):
    store = _hub_store(tmp_path, [
        (DRILL_ROW, "detector_track",
         {"track_id": "trk-1", "detector_label": "drill", "bound_text": "DEWALT 20V MAX XR"}),
        ("OBJECT | workbench, drill", "fastvlm", {}),
    ])
    agent = TraceMemoryAgent(store, restrict_sources=("phone_camera",))
    answer = agent.answer("What brand is the drill?")
    joined = " ".join(str(r.get("text", "")) for r in answer.evidence_chain)
    assert "DEWALT" in joined, f"bound text missing from evidence: {joined[:200]}"


def test_bound_digits_never_floor_counts(tmp_path):
    store = _hub_store(tmp_path, [
        ('OBJECT | bus | detected by on-device tracker | label text: "PLATFORM 5 BUSES DEPART '
         'DAILY"; lower-left of frame | likely', "detector_track",
         {"track_id": "trk-2", "detector_label": "bus", "bound_text": "PLATFORM 5 BUSES DEPART DAILY"}),
    ])
    res = permanence.count_instances(store, "bus", sources=("phone_camera",), use_llm=False)
    assert res.floor == 0, f"bound sign text poisoned the floor: {res.floor}"
    assert res.count == 1


def test_bound_text_rides_the_reads_descriptor(tmp_path):
    store = _hub_store(tmp_path, [
        (DRILL_ROW, "detector_track",
         {"track_id": "trk-1", "detector_label": "drill", "bound_text": "DEWALT 20V MAX XR"}),
    ])
    reads = permanence.gather_reads(store, "drill", sources=("phone_camera",))
    assert len(reads) == 1
    assert "dewalt" in reads[0].desc.lower()
