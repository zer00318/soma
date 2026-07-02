"""The nutella model, coordinate-free: 5 jars = 5 on-device tracks, each described by several
helpers. The binder must fuse helper aspects PER TRACK and count 5 distinct instances — with no
world coordinates (the non-LiDAR phone reality). Mirrors the live hub write path exactly:
source=phone_camera, helper + track_id in metadata, no coordinate_frame, derived=False."""
from __future__ import annotations

import os
import tempfile

from trace_memory.store import TraceMemoryStore
from trace_memory.store.sleep import SleepConsolidator
from trace_memory.store.author import deterministic_author


def _live_write(store, text, t_ms, helper, track_id):
    # Exactly how scripts/trace_hub.py writes a live phone observation.
    store.write_observation(
        text=text,
        t_ms=t_ms,
        source="phone_camera",
        provenance={"kind": "phone_helper"},
        metadata={"helper": helper, "track_id": track_id},
    )


def _build_store(path):
    store = TraceMemoryStore(path)
    t0 = 1_700_000_000_000
    # 5 distinct jars, each a separate track, each seen by 3 helpers with different aspects.
    jars = [
        ("track-1", "500g classic hazelnut spread"),
        ("track-2", "825g family size"),
        ("track-3", "200g mini jar"),
        ("track-4", "1kg catering tub"),
        ("track-5", "400g glass jar, lid open"),
    ]
    t = t0
    for tid, detail in jars:
        _live_write(store, f"OBJECT | nutella jar | {detail}", t, "vlm_object", tid)
        _live_write(store, f"OBJECT | text surface | OCR text: \"NUTELLA {detail.split()[0]}\"", t + 500, "ocr", tid)
        _live_write(store, "OBJECT | nutella jar | brown label, white lid", t + 1000, "colour", tid)
        t += 3000
    return store


def test_binder_fuses_per_track_and_counts_five():
    with tempfile.TemporaryDirectory() as d:
        store = _build_store(os.path.join(d, "s.sqlite3"))
        # Deterministic author (no LLM) so the test is hermetic and reproducible.
        summary = SleepConsolidator(store, author=deterministic_author).consolidate()

        # It authored memories (the old gate produced ZERO on coordinate-free live data).
        assert summary.composed_memory_count > 0, "binder authored nothing from track-anchored data"
        assert summary.link_count > 0, "no support links created"

        derived = [n for n in store.nodes() if getattr(n, "derived", False)]
        entity_mems = [n for n in derived if (n.metadata or {}).get("memory_kind") == "entity_memory"]

        # 1) INDIVIDUATION: exactly 5 distinct nutella instances, one per track.
        assert len(entity_mems) == 5, f"expected 5 per-track instances, got {len(entity_mems)}"

        # 2) FUSION: each instance's support spans MORE THAN ONE helper (colour+ocr+vlm on that track).
        for mem in entity_mems:
            support_ids = (mem.metadata or {}).get("support_ids", [])
            helpers = set()
            for sid in support_ids:
                obs = store.read_observation(sid)
                if obs is not None:
                    helpers.add((obs.metadata or {}).get("helper"))
            assert len(helpers) >= 2, f"instance fused only one helper aspect: {helpers}"

        # 3) COUNT: a deterministic count memory that says 5 (not guessed, not coordinate-claimed).
        counts = [n for n in derived if (n.metadata or {}).get("authored_by") == "deterministic_count"]
        assert counts, "no count memory authored"
        assert any((n.metadata or {}).get("count") == 5 for n in counts), \
            f"count memory did not report 5: {[(n.metadata or {}).get('count') for n in counts]}"
        # Honesty: with no coordinates, it must NOT fabricate coordinate text.
        assert all("coordinates:" not in n.text for n in counts), "fabricated coordinates without xyz"
        store.close()


def test_no_track_and_no_coords_still_binds_nothing():
    """Guard: a raw observation with neither a track nor a coordinate has no anchor, so the binder
    must still abstain (no hallucinated fusion). This preserves the honesty invariant."""
    with tempfile.TemporaryDirectory() as d:
        store = TraceMemoryStore(os.path.join(d, "s.sqlite3"))
        t0 = 1_700_000_000_000
        store.write_observation(text="OBJECT | nutella jar | brown", t_ms=t0,
                                source="phone_camera", provenance={"k": "x"},
                                metadata={"helper": "vlm_object"})  # no track_id, no coords
        summary = SleepConsolidator(store, author=deterministic_author).consolidate()
        assert summary.composed_memory_count == 0
        store.close()
