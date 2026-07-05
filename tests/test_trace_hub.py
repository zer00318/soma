"""Live-path seam tests for scripts/trace_hub.py — replaces the orphaned tests that imported
the deleted cockpit/brain servers. Covers: helper attribution at ingest, the store write shape
the agent depends on (metadata.helper, source=phone_camera), and track_id passthrough."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.trace_hub import Hub, helper_of  # noqa: E402


def test_helper_of_maps_known_sources():
    assert helper_of("fastvlm") == "vlm_object"
    assert helper_of("apple_vision_ocr") == "ocr"
    assert helper_of("apple_speech") == "asr"
    assert helper_of("detector_track") == "detector"


def test_ingest_writes_tagged_observation(tmp_path):
    hub = Hub(str(tmp_path / "hub.sqlite3"))
    result = hub.ingest({
        "memory_text": "OBJECT | keyboard | detected by on-device tracker | likely",
        "source": "detector_track",
        "timestamp": "2026-07-01T10:00:00.000Z",
        "metadata": {"track_id": "trk-7", "detector_label": "keyboard"},
    })
    assert result["ok"] and result["helper"] == "detector"
    nodes = list(hub.store.nodes(node_types=("observation",), sources=("phone_camera",)))
    assert len(nodes) == 1
    node = nodes[0]
    assert node.source == "phone_camera"
    assert node.metadata["helper"] == "detector"
    assert node.metadata["track_id"] == "trk-7"  # the binder's individuation anchor


def test_ingest_rejects_empty_text(tmp_path):
    hub = Hub(str(tmp_path / "hub2.sqlite3"))
    assert hub.ingest({"memory_text": "", "source": "fastvlm"})["ok"] is False


def test_timeline_serves_episodes_and_digest(tmp_path):
    from trace_memory.store.digest import DigestBuilder
    from trace_memory.store.episodes import EpisodeBuilder

    hub = Hub(str(tmp_path / "hub3.sqlite3"))
    base = 1_782_900_000_000
    for i in range(40):
        hub.store.write_observation(
            text="OBJECT | laptop", t_ms=base + i * 2_000, source="phone_camera",
            provenance={"location_hint": "GPS 48.26232, 11.67535 | Waldstrasse, Garching"},
            immutable_raw=True,
        )
    EpisodeBuilder(hub.store).build()
    DigestBuilder(hub.store, use_llm=False).build()

    eps = hub.timeline(kind="episodes", day=None)
    assert eps["ok"] and eps["count"] == 1
    row = eps["rows"][0]
    assert row["kind"] == "episode" and row["observation_count"] == 40
    assert row["start_ms"] == base and row["day"] == "2026-07-01"

    dig = hub.timeline(kind="digest", day="2026-07-01")
    assert dig["ok"] and dig["count"] == 1
    assert dig["rows"][0]["bullets"] and dig["rows"][0]["thin_day"] is False
    # wrong day filters to empty, honestly
    assert hub.timeline(kind="digest", day="2026-07-02")["count"] == 0
