"""P11 — appearance fingerprints (things pin to identities).

Coordinates alone mis-count movable things: keys occupy six coordinates in a day → six
"objects" by geometry, one by identity. Every confirmed track gets a compact, non-reversible
visual signature (computed ON the phone; crops never leave it) so the binder can ask "same
thing?". These are seam tests + a SYNTHETIC ROC proving the cosine machinery separates
same-object from different-object — the REAL ROC on ≥20 device object pairs is the walk's job."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.trace_hub import Hub  # noqa: E402
from trace_memory.contract import is_valid_fingerprint, normalize_fingerprint  # noqa: E402
from trace_memory.store.sqlite_store import FINGERPRINT_MATCH_THRESHOLD  # noqa: E402

# Two sightings of the SAME mug (slightly different view) and a DIFFERENT mug.
MUG_A1 = [0.90, 0.10, 0.00, 0.00, 0.20, 0.00, 0.00, 0.10]
MUG_A2 = [0.85, 0.15, 0.05, 0.00, 0.18, 0.02, 0.00, 0.12]
MUG_B = [0.00, 0.10, 0.90, 0.20, 0.00, 0.10, 0.00, 0.00]


def _legacy(fp, **over):
    base = {
        "memory_text": "OBJECT | mug | detected by on-device tracker",
        "source": "detector_track",
        "timestamp": "2026-07-04T10:00:00.000Z",
        "fingerprint": fp,
    }
    base.update(over)
    return base


# ---- contract: fingerprints are validated, non-reversible, coerced --------------------------
def test_fingerprint_validation():
    assert is_valid_fingerprint([0.1, 0.2, 0.3])
    assert not is_valid_fingerprint([])            # empty is not a signature
    assert not is_valid_fingerprint(["a", "b"])    # not numbers
    assert not is_valid_fingerprint([0.1] * 5000)  # over the cap (fits a ~2048-float featureprint)
    assert normalize_fingerprint([1, 2]) == [1.0, 2.0]
    assert normalize_fingerprint("not a vector") is None


# ---- the fingerprint reaches the store TYPED, on both ingest shapes -------------------------
def test_fingerprint_flows_through_legacy_shape(tmp_path):
    # The phone streams the legacy shape — fingerprints must flow through it or the substrate
    # stays empty on the one path that runs on-device (same lesson as P10 anchors).
    hub = Hub(str(tmp_path / "hub.sqlite3"))
    hub.ingest(_legacy(MUG_A1))
    node = next(iter(hub.store.nodes(node_types=("observation",))))
    assert hub.store.fingerprint_of(node) == tuple(MUG_A1)
    assert "fingerprint" not in node.text  # typed in metadata, never dumped into the text


def test_fingerprint_flows_through_contract_shape(tmp_path):
    hub = Hub(str(tmp_path / "hub.sqlite3"))
    hub.ingest({"contract": 1, "helper_id": "vlm_object", "text": "mug crop",
                "t_ms": 1783000000000, "fingerprint": MUG_A2})
    node = next(iter(hub.store.nodes(node_types=("observation",))))
    assert hub.store.fingerprint_of(node) == tuple(MUG_A2)


def test_garbage_fingerprint_dropped_row_survives(tmp_path):
    # A bad vector must never poison the row — nor take the observation down with it.
    hub = Hub(str(tmp_path / "hub.sqlite3"))
    hub.ingest(_legacy(["not", "a", "vector"]))
    node = next(iter(hub.store.nodes(node_types=("observation",))))
    assert hub.store.fingerprint_of(node) is None
    assert "mug" in node.text


# ---- the "same thing?" primitive -----------------------------------------------------------
def test_same_appearance_separates_same_from_different(tmp_path):
    store = Hub(str(tmp_path / "hub.sqlite3")).store
    assert store.same_appearance(MUG_A1, MUG_A2) is True    # same mug, two views → same
    assert store.same_appearance(MUG_A1, MUG_B) is False    # different mug → different
    # and the numbers actually separate, comfortably around the threshold
    assert store.fingerprint_similarity(MUG_A1, MUG_A2) > FINGERPRINT_MATCH_THRESHOLD
    assert store.fingerprint_similarity(MUG_A1, MUG_B) < FINGERPRINT_MATCH_THRESHOLD


def test_fingerprint_neighbors_ranks_the_same_object_first(tmp_path):
    hub = Hub(str(tmp_path / "hub.sqlite3"))
    hub.ingest(_legacy(MUG_A1, memory_text="OBJECT | mug A view 1"))
    hub.ingest(_legacy(MUG_A2, memory_text="OBJECT | mug A view 2"))
    hub.ingest(_legacy(MUG_B, memory_text="OBJECT | mug B"))
    a1 = next(n for n in hub.store.nodes(node_types=("observation",)) if "view 1" in n.text)
    neighbors = hub.store.fingerprint_neighbors(hub.store.fingerprint_of(a1), exclude_ids=[a1.id])
    assert neighbors, "expected fingerprinted neighbors"
    top_node, top_score = neighbors[0]
    assert "view 2" in top_node.text          # the other sighting of the same mug wins
    assert top_score > 0.9


def test_fingerprint_coverage_is_honest(tmp_path):
    hub = Hub(str(tmp_path / "hub.sqlite3"))
    assert hub.store.fingerprint_coverage()["fraction"] == 0.0  # empty store never flatters
    hub.ingest(_legacy(MUG_A1))
    hub.ingest(_legacy(None))  # a track with no crop yet → no fingerprint
    cov = hub.store.fingerprint_coverage()
    assert cov["rows_total"] == 2 and cov["rows_with_fingerprint"] == 1
    assert abs(cov["fraction"] - 0.5) < 1e-9


# ---- synthetic ROC: within-object closer than between-object -------------------------------
def test_synthetic_roc_within_beats_between(tmp_path):
    """Proves the cosine substrate is sound: same-object pairs score measurably higher than
    different-object pairs, and the default threshold classifies every synthetic pair right.
    (The real featureprint's separation on our crops is the device-gated unknown the walk
    resolves; if it fails to separate, P11's RED branch swaps in a distilled model.)"""
    store = Hub(str(tmp_path / "hub.sqlite3")).store
    objects = {
        "mug": [MUG_A1, MUG_A2, [0.88, 0.12, 0.02, 0.0, 0.19, 0.01, 0.0, 0.11]],
        "book": [MUG_B, [0.02, 0.12, 0.88, 0.22, 0.0, 0.09, 0.0, 0.0]],
        "lamp": [[0.0, 0.0, 0.05, 0.1, 0.0, 0.1, 0.95, 0.2],
                 [0.02, 0.0, 0.04, 0.12, 0.0, 0.08, 0.90, 0.22]],
    }
    within, between = [], []
    for label, vecs in objects.items():
        for i in range(len(vecs)):
            for j in range(i + 1, len(vecs)):
                within.append(store.fingerprint_similarity(vecs[i], vecs[j]))
    labels = list(objects)
    for a in range(len(labels)):
        for b in range(a + 1, len(labels)):
            for va in objects[labels[a]]:
                for vb in objects[labels[b]]:
                    between.append(store.fingerprint_similarity(va, vb))

    assert min(within) > max(between), "same-object pairs must all beat different-object pairs"
    # the synthetic default threshold sits cleanly in the gap
    assert max(between) < FINGERPRINT_MATCH_THRESHOLD <= min(within)
