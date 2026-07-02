"""M5 seam test — per-track crop enrichment fuses into the track instance.

The app emits a crop-zoom VLM read as source=fastvlm_track_crop carrying the SAME
(track_id, detector_label) as the detector rows. Locked behaviours (through real Hub.ingest):
  - the crop read joins the detector track's instance (one cluster, two helper aspects),
  - its attributes (colour/brand) enrich the instance's identity signature and reads,
  - it does NOT create a second phantom instance of the object.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.trace_hub import Hub  # noqa: E402
from trace_memory.store import permanence  # noqa: E402
from trace_memory.store.individuate import individuate  # noqa: E402


def _store(tmp_path):
    hub = Hub(str(tmp_path / "m5.sqlite3"))
    rows = [
        ("OBJECT | backpack | detected by on-device tracker | middle-center of frame | likely",
         "detector_track", {"track_id": "trk-9", "detector_label": "backpack"}),
        ("OBJECT | backpack | detected by on-device tracker | middle-center of frame | likely",
         "detector_track", {"track_id": "trk-9", "detector_label": "backpack"}),
        ("OBJECT | backpack | navy blue canvas backpack, Deuter logo, side mesh pockets | "
         "crop-zoom | likely",
         "fastvlm_track_crop", {"track_id": "trk-9", "detector_label": "backpack",
                                "crop_zoom": True}),
    ]
    for i, (text, source, meta) in enumerate(rows):
        assert hub.ingest({"memory_text": text, "source": source,
                           "timestamp": f"2026-07-02T11:00:{i:02d}.000Z",
                           "metadata": meta})["ok"]
    return hub.store


def test_crop_read_fuses_into_the_track_instance(tmp_path):
    store = _store(tmp_path)
    clusters = [c for c in individuate(list(store.nodes(node_types=("observation",))))
                if c.kind == "entity" and "backpack" in c.label]
    assert len(clusters) == 1, f"crop read split the instance: {len(clusters)}"
    helpers = {(_m.metadata or {}).get("helper") for _m in clusters[0].members}
    assert {"detector", "vlm_object"} <= helpers, f"aspects not fused: {helpers}"


def test_crop_attributes_enrich_the_resolver_reads(tmp_path):
    store = _store(tmp_path)
    res = permanence.count_instances(store, "backpack", sources=("phone_camera",), use_llm=False)
    assert res.count == 1  # enrichment never inflates the count
    reads = permanence.gather_reads(store, "backpack", sources=("phone_camera",))
    assert any("navy" in r.desc.lower() or "deuter" in r.desc.lower() for r in reads), \
        "crop attributes missing from reads"
