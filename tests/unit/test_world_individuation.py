"""P10 fusion regression battery — genesis-frame coordinates individuate identical objects.

The three-nutella-jar walk (2026-07-04) proved appearance CANNOT split same-kind objects
(same-jar cosines 0.28-0.68 overlap cross-kind 0.13-0.52) and coordinates CAN (repeat
raycasts of one static object agree to ≲0.15 m; different jars sit ≥0.33 m apart). Locked
behaviours:
  - sequential same-label tracks FAR APART in the genesis frame are DISTINCT objects, even
    though they were never co-visible (the case grid-cell co-visibility cannot see),
  - same-spot re-sightings stay ONE object (raycast noise below the split threshold),
  - the mid zone between merge radius and split distance asserts nothing — existing
    co-visibility/attribute evidence decides, counts stay honest,
  - coordinates from untrusted grades (Limited/relocalizing) are ignored, never split on,
  - a single outlier raycast does not move a track's median position.
"""
from __future__ import annotations

from trace_memory.store import TraceMemoryStore
from trace_memory.store.individuate import individuate

T0 = 1_700_000_000_000


def _write(store, tid, t_ms, world=None, grade="session", label="bottle"):
    meta = {"helper": "detector", "track_id": tid, "detector_label": label, "grade": grade}
    if world is not None:
        meta["track_world"] = list(world)
    store.write_observation(
        text=f"OBJECT | {label} | detected by on-device tracker | middle-center of frame",
        t_ms=t_ms, source="phone_camera", provenance={"kind": "phone_helper"},
        metadata=meta,
    )


def _clusters(store, label="bottle"):
    return [c for c in individuate(list(store.nodes(node_types=("observation",))))
            if c.kind == "entity" and label in c.label]


def test_three_identical_jars_far_apart_are_three_objects(tmp_path):
    store = TraceMemoryStore(tmp_path / "s.sqlite3")
    # Never co-visible (sequential, well outside the covis window) — pre-P10 these MERGE.
    _write(store, "trk-1", T0 + 0, world=(0.0, 0.0, 0.0))
    _write(store, "trk-1", T0 + 1000, world=(0.05, 0.0, 0.02))
    _write(store, "trk-2", T0 + 5000, world=(0.0, 0.0, -0.65))
    _write(store, "trk-2", T0 + 6000, world=(0.04, -0.03, -0.68))
    _write(store, "trk-3", T0 + 10000, world=(0.7, 0.1, 0.1))
    clusters = _clusters(store)
    assert len(clusters) == 3
    # Firm count: strict and liberal agree, so low == high == 3.
    assert all(c.instance_count == 3 and c.count_low == 3 for c in clusters)


def test_same_spot_resightings_stay_one_object(tmp_path):
    store = TraceMemoryStore(tmp_path / "s.sqlite3")
    # Two tracks of one static jar, raycast noise ~0.12 m — below the split threshold.
    _write(store, "trk-1", T0 + 0, world=(0.0, 0.0, 0.0))
    _write(store, "trk-8", T0 + 20000, world=(0.08, 0.05, -0.06))
    clusters = _clusters(store)
    assert len(clusters) == 1
    assert clusters[0].instance_count == 1


def test_mid_zone_widens_the_range_instead_of_asserting(tmp_path):
    store = TraceMemoryStore(tmp_path / "s.sqlite3")
    # 0.27 m apart, never co-visible: above the liberal split (0.15, measured same-object
    # median noise tops at 0.147) but below the strict one (0.30). Neither a firm merge nor
    # a firm second object — an honest [1,2] range. A firm split must be WITNESSED
    # (simultaneous stamps), never inferred from mid-zone medians.
    _write(store, "trk-1", T0 + 0, world=(0.0, 0.0, 0.0))
    _write(store, "trk-2", T0 + 5000, world=(0.27, 0.0, 0.0))
    clusters = _clusters(store)
    assert len(clusters) == 2  # one cluster per liberal instance
    assert all(c.count_low == 1 and c.instance_count == 2 for c in clusters)


def test_label_flip_on_one_object_unifies_across_labels(tmp_path):
    store = TraceMemoryStore(tmp_path / "s.sqlite3")
    # Walk 2 measured case: COCO flip-flopped ONE jar as cup-trk-16 / bottle-trk-17, world
    # stamps 0.000 m apart at the same instant. Per-label buckets could never see this; the
    # must-link graph unifies them into one object in one counting family.
    _write(store, "trk-16", T0 + 0, world=(0.610, -0.055, -0.569), label="cup")
    _write(store, "trk-17", T0 + 22, world=(0.610, -0.055, -0.569), label="bottle")
    all_clusters = [c for c in individuate(list(store.nodes(node_types=("observation",))))
                    if c.kind == "entity"]
    assert len(all_clusters) == 1
    assert all_clusters[0].instance_count == 1


def test_witnessed_pairs_and_unwitnessed_pair_give_two_to_three(tmp_path):
    store = TraceMemoryStore(tmp_path / "s.sqlite3")
    # Walk 2's exact evidence shape: A≠B and B≠C witnessed (simultaneous, ≥0.10 m apart);
    # A vs C never witnessed together, medians 0.27 m apart (mid-zone). Honest count: the
    # witnessed splits hold in BOTH passes, A-vs-C only in the liberal one -> [2,3].
    _write(store, "trk-1", T0 + 0, world=(0.42, -0.25, -0.61))     # A
    _write(store, "trk-2", T0 + 30, world=(0.45, -0.12, -0.60))    # B, simultaneous with A
    _write(store, "trk-2", T0 + 5000, world=(0.45, -0.12, -0.60))  # B again
    _write(store, "trk-3", T0 + 5030, world=(0.61, -0.06, -0.57))  # C, simultaneous with B
    clusters = _clusters(store)
    assert len(clusters) == 3
    assert all(c.count_low == 2 and c.instance_count == 3 for c in clusters)


def test_untrusted_grade_coordinates_never_split(tmp_path):
    store = TraceMemoryStore(tmp_path / "s.sqlite3")
    # Relocalizing-grade coords live in a shifted frame (measured ~0.7 m off on the jar
    # walk). Far-apart junk coords must NOT mint a second object.
    _write(store, "trk-1", T0 + 0, world=(0.0, 0.0, 0.0))
    _write(store, "trk-2", T0 + 5000, world=(2.0, 0.0, 0.0), grade="track")
    clusters = _clusters(store)
    assert len(clusters) == 1


def test_outlier_raycast_does_not_move_the_median(tmp_path):
    store = TraceMemoryStore(tmp_path / "s.sqlite3")
    # trk-1: three good stamps at origin + one glance-off-the-wall outlier. Median holds,
    # so trk-2 at the same spot still merges.
    _write(store, "trk-1", T0 + 0, world=(0.0, 0.0, 0.0))
    _write(store, "trk-1", T0 + 1000, world=(0.03, 0.01, -0.02))
    _write(store, "trk-1", T0 + 2000, world=(3.5, 1.0, 2.0))
    _write(store, "trk-1", T0 + 3000, world=(-0.02, 0.02, 0.03))
    _write(store, "trk-2", T0 + 9000, world=(0.05, 0.0, 0.0))
    clusters = _clusters(store)
    assert len(clusters) == 1


def test_covisible_adjacent_jars_split_by_metric_distance(tmp_path):
    store = TraceMemoryStore(tmp_path / "s.sqlite3")
    # Walk 2 measured case: three jars ~0.12 m apart, tracked SIMULTANEOUSLY (same instant,
    # shared camera pose -> relative distance near-exact). The 3x3 grid puts adjacent jars in
    # the SAME cell (dup-box rule would merge); metric co-visibility must split them.
    _write(store, "trk-1", T0 + 0, world=(0.42, -0.25, -0.61))
    _write(store, "trk-2", T0 + 30, world=(0.45, -0.12, -0.60))
    _write(store, "trk-3", T0 + 60, world=(0.61, -0.06, -0.57))
    clusters = _clusters(store)
    assert len(clusters) == 3
    assert all(c.instance_count == 3 and c.count_low == 3 for c in clusters)


def test_covisible_duplicate_boxes_stay_one_object(tmp_path):
    store = TraceMemoryStore(tmp_path / "s.sqlite3")
    # Walk 2 measured case: one jar double-boxed — two tracks at the same instant 0.001 m
    # apart. Simultaneous same-place = the same object twice, never a second object.
    _write(store, "trk-1", T0 + 0, world=(0.42, -0.253, -0.613))
    _write(store, "trk-2", T0 + 31, world=(0.421, -0.253, -0.613))
    clusters = _clusters(store)
    assert len(clusters) == 1
    assert clusters[0].instance_count == 1


def test_coordinate_free_tracks_keep_legacy_behaviour(tmp_path):
    store = TraceMemoryStore(tmp_path / "s.sqlite3")
    # No track_world anywhere -> pre-P10 path exactly: sequential same-label tracks merge.
    _write(store, "trk-1", T0 + 0)
    _write(store, "trk-2", T0 + 5000)
    clusters = _clusters(store)
    assert len(clusters) == 1
