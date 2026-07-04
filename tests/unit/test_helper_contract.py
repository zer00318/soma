"""P02 — the helper contract + plugin registry (spec §5, L7).

A helper is ANY process that emits a contract-shaped observation into the ingest seam.
The registry is DATA; unknown helper_ids ingest fine (flagged unregistered); schema
violations are rejected loudly; the legacy phone shape keeps working byte-for-byte."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.trace_hub import Hub  # noqa: E402
from trace_memory.contract import (  # noqa: E402
    PILLAR_SOURCES,
    load_registry,
    validate_observation,
)

GOOD = {
    "contract": 1,
    "helper_id": "mac_screen_ocr",
    "text": "SCREEN | terminal | error: ModuleNotFoundError: no module named requests",
    "t_ms": 1783000000000,
    "confidence": 0.9,
    "session_id": "s-1",
}


def test_validate_accepts_good_packet():
    norm, err = validate_observation(GOOD)
    assert err is None
    assert norm["helper_id"] == "mac_screen_ocr"
    assert norm["t_ms"] == 1783000000000


def test_validate_rejects_specifically():
    checks = [
        ({**GOOD, "helper_id": ""}, "helper_id"),
        ({**GOOD, "text": "  "}, "text"),
        ({**GOOD, "t_ms": "yesterday"}, "t_ms"),
        ({**GOOD, "confidence": 1.7}, "confidence"),
        ({**GOOD, "contract": 99}, "contract version"),
        ({**GOOD, "fingerprint": ["a", "b"]}, "fingerprint"),
        ({**GOOD, "fingerprint": [0.1] * 5000}, "fingerprint"),
    ]
    for packet, needle in checks:
        norm, err = validate_observation(packet)
        assert norm is None and needle in err, f"{needle}: got {err!r}"


def test_contract_ingest_lands_and_is_searchable(tmp_path):
    hub = Hub(str(tmp_path / "hub.sqlite3"))
    result = hub.ingest(GOOD)
    assert result["ok"] and result["helper"] == "mac_screen_ocr" and result["registered"]
    nodes = list(hub.store.nodes(node_types=("observation",),
                                 sources=tuple(PILLAR_SOURCES.values())))
    assert len(nodes) == 1
    node = nodes[0]
    assert node.source == PILLAR_SOURCES["mac"]  # pillar from the registry, not code
    assert node.metadata["helper"] == "mac_screen_ocr"
    assert node.metadata["contract"] == 1
    hits = hub.store.search("ModuleNotFoundError requests", k=3)
    hit_texts = [h.node.text for h in (getattr(hits, "hits", None) or list(hits))]
    assert any("ModuleNotFoundError" in t for t in hit_texts)


def test_unknown_helper_ingests_flagged_not_crashed(tmp_path):
    hub = Hub(str(tmp_path / "hub.sqlite3"))
    result = hub.ingest({**GOOD, "helper_id": "my_custom_plant_watcher"})
    assert result["ok"] and result["registered"] is False
    assert "my_custom_plant_watcher" in hub.unregistered_seen
    # defaults to the phone pillar when the registry doesn't know it
    nodes = list(hub.store.nodes(node_types=("observation",),
                                 sources=(PILLAR_SOURCES["phone"],)))
    assert len(nodes) == 1


def test_contract_reject_is_counted(tmp_path):
    hub = Hub(str(tmp_path / "hub.sqlite3"))
    bad = hub.ingest({**GOOD, "t_ms": None})
    assert bad["ok"] is False
    assert sum(hub.reject_counts.values()) == 1
    assert hub.store.node_count() == 0


def test_legacy_shape_unchanged(tmp_path):
    hub = Hub(str(tmp_path / "hub.sqlite3"))
    result = hub.ingest({
        "memory_text": "OBJECT | keyboard | detected by on-device tracker | likely",
        "source": "detector_track",
        "timestamp": "2026-07-01T10:00:00.000Z",
        "metadata": {"track_id": "trk-7"},
    })
    assert result["ok"] and result["helper"] == "detector"
    node = list(hub.store.nodes(node_types=("observation",)))[0]
    assert node.source == "phone_camera"
    assert node.metadata["helper"] == "detector"


def test_registry_loads_and_survives_malformed_entries(tmp_path):
    good = load_registry()  # the real config/helpers.json
    assert "detector" in good and good["mac_screen_ocr"]["pillar"] == "mac"
    broken = tmp_path / "helpers.json"
    broken.write_text(json.dumps({"helpers": [
        {"id": "fine", "kind": "standing", "pillar": "phone"},
        {"id": "", "kind": "standing", "pillar": "phone"},
        {"id": "badkind", "kind": "sometimes", "pillar": "phone"},
        {"id": "badpillar", "kind": "standing", "pillar": "cloud"},
    ]}))
    reg = load_registry(broken)
    assert set(reg) == {"fine"}
    assert load_registry(tmp_path / "missing.json") == {}
