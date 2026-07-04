"""P10 — the coordinate anchor substrate (spec §2).

Everything perceived pins to a place the moment it's perceived. Coordinates pin the world
(this packet); the anchor row is the world's own memory of a pinned spot — first/last seen,
how many sessions re-localized against it, and the firmest fidelity it ever earned. The
observation SAYS its grade, so a degraded fix is never dressed up as a world-locked one.

These are seam tests: real contract packets through the real Hub.ingest → real sqlite store.
The Done-when %-coverage number is device-gated (needs a walk on the ARKit build); here we
prove the substrate is correct and honest against synthetic anchor-bearing observations."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.trace_hub import Hub  # noqa: E402
from trace_memory.contract import best_grade, normalize_grade, validate_observation  # noqa: E402


def _anchored(**over):
    base = {
        "contract": 1,
        "helper_id": "detector",
        "text": "OBJECT | washing machine | gorenje",
        "t_ms": 1000,
        "anchor_id": "arkit:kitchen:7",
        "grade": "world",
        "room": "kitchen",
        "session_id": "walk-A",
        "pose": {"yaw": 1.2},
    }
    base.update(over)
    return base


# ---- contract: pose/grade/room are first-class, validated, honest ------------------------
def test_contract_accepts_and_normalizes_spatial_fields():
    norm, err = validate_observation(_anchored())
    assert err is None
    assert norm["pose"] == {"yaw": 1.2}
    assert norm["grade"] == "world"
    assert norm["room"] == "kitchen"


def test_contract_rejects_malformed_spatial_fields():
    for packet, needle in [
        ({**_anchored(), "pose": "north"}, "pose"),
        ({**_anchored(), "grade": 5}, "grade"),
        ({**_anchored(), "room": 12}, "room"),
    ]:
        norm, err = validate_observation(packet)
        assert norm is None and needle in err, f"{needle}: got {err!r}"


def test_unknown_grade_degrades_to_none_never_drops_the_row():
    # A grade typo must not throw away a real perception — it just loses the fidelity claim.
    norm, err = validate_observation({**_anchored(), "grade": "worldd"})
    assert err is None and norm["grade"] == "none"


def test_grade_helpers_are_monotone():
    assert normalize_grade("WORLD") == "world"
    assert normalize_grade("garbage") == "none"
    assert best_grade("track", "world", "session") == "world"
    assert best_grade("none", "track") == "track"


# ---- substrate: anchor rows live across sessions, honestly graded ------------------------
def test_anchor_row_written_and_row_pinned_to_place(tmp_path):
    hub = Hub(str(tmp_path / "hub.sqlite3"))
    hub.ingest(_anchored(anchor_id="a3", room="bathroom"))
    rec = hub.store.anchor("a3")
    assert rec is not None and rec.room == "bathroom" and rec.grade == "world"
    node = next(n for n in hub.store.nodes(node_types=("observation",))
                if (n.metadata or {}).get("anchor_id") == "a3")
    assert node.place == "bathroom"      # room becomes the row's place → free room retrieval
    assert node.pose == {"yaw": 1.2}     # pose is a first-class column, not buried in metadata


def test_reentered_room_relocalizes_across_sessions(tmp_path):
    hub = Hub(str(tmp_path / "hub.sqlite3"))
    hub.ingest(_anchored(session_id="walk-A", t_ms=1000))
    hub.ingest(_anchored(session_id="walk-A", t_ms=2000))   # same session → no re-localize
    hub.ingest(_anchored(session_id="walk-B", t_ms=3000))   # new session → re-localize
    rec = hub.store.anchor("arkit:kitchen:7")
    assert rec.sightings == 3
    assert rec.session_count == 2 and rec.relocalized is True
    assert rec.first_seen_ms == 1000 and rec.last_seen_ms == 3000
    assert hub.relocalizations == 1


def test_grade_never_downgrades(tmp_path):
    hub = Hub(str(tmp_path / "hub.sqlite3"))
    hub.ingest(_anchored(anchor_id="a2", grade="world", t_ms=1000, pose={"yaw": 0.1}))
    hub.ingest(_anchored(anchor_id="a2", grade="track", t_ms=2000, pose={"yaw": 9.9}))
    rec = hub.store.anchor("a2")
    assert rec.grade == "world"          # a later .limited frame cannot unpin a world lock
    assert rec.pose == {"yaw": 0.1}      # and the firmest pose is the one kept


def test_coverage_is_honest(tmp_path):
    hub = Hub(str(tmp_path / "hub.sqlite3"))
    assert hub.store.anchor_coverage()["fraction"] == 0.0      # empty store never flatters
    hub.ingest(_anchored(anchor_id="a1"))
    hub.ingest({  # legacy detector row carries no anchor — it counts against coverage
        "memory_text": "OBJECT | chair | detected by on-device tracker",
        "source": "detector_track",
        "timestamp": "2026-07-04T10:00:00.000Z",
    })
    cov = hub.store.anchor_coverage()
    assert cov["rows_total"] == 2 and cov["rows_with_anchor"] == 1
    assert abs(cov["fraction"] - 0.5) < 1e-9
    assert cov["by_grade"].get("world") == 1
    assert cov["anchors_total"] == 1 and cov["anchors_relocalized"] == 0


def test_legacy_phone_shape_feeds_the_substrate(tmp_path):
    # The phone streams the legacy (memory_text/source) shape; P10 anchors must flow through
    # it too, or the substrate would stay empty on the one path that actually runs on-device.
    hub = Hub(str(tmp_path / "hub.sqlite3"))
    hub.ingest({
        "memory_text": "OBJECT | washing machine | gorenje",
        "source": "detector_track",
        "timestamp": "2026-07-04T06:53:00.000Z",
        "anchor_id": "arkit:kitchen:origin",
        "grade": "world",
        "room": "kitchen",
        "session_id": "walk-A",
        "pose": {"position": [0.1, 0.2, 0.3]},
    })
    rec = hub.store.anchor("arkit:kitchen:origin")
    assert rec is not None and rec.grade == "world" and rec.room == "kitchen"
    node = next(iter(hub.store.nodes(node_types=("observation",))))
    assert node.place == "kitchen" and node.pose == {"position": [0.1, 0.2, 0.3]}
    assert node.metadata.get("anchor_id") == "arkit:kitchen:origin"


def test_anchorless_contract_row_still_ingests_untouched(tmp_path):
    # P02 packets without any spatial fields must keep working exactly as before.
    hub = Hub(str(tmp_path / "hub.sqlite3"))
    result = hub.ingest({
        "contract": 1, "helper_id": "asr", "text": "the washing machine goes from 1 to 8",
        "t_ms": 1783000000000,
    })
    assert result["ok"]
    assert hub.store.anchor_coverage()["anchors_total"] == 0
    node = next(iter(hub.store.nodes(node_types=("observation",))))
    assert node.pose is None and node.place is None
