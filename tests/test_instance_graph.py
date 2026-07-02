"""Acceptance spec for the instance graph (binder + geometry).

The _categorize cases are the worker's task: prefer the VLM-read identity over the
detector's noisy class label. The geometry/count tests are regression guards.
"""
from __future__ import annotations

from scripts.instance_graph import _categorize, build_graph


# --- _categorize: identity beats detector label (worker task: instance_categorize) --- #

def test_categorize_prefers_identity_over_detector_label():
    # detector said 'blanket', but the VLM read a chip brand -> snack, not blanket
    assert _categorize("Lays Xtra Flamin' Hot", "Lays", "blanket") == "snack"
    assert _categorize("Doritos Tortillas", "Tortillas", "bag") == "snack"


def test_categorize_electronics():
    assert _categorize("Apple iPhone", "", "monitor") == "electronics"
    assert _categorize("Samsung Galaxy S21+", "SAMSUNG", "phone") == "electronics"


def test_categorize_condiment_and_beverage():
    assert _categorize("Heinz Tomato Ketchup", "HEINZ", "jar bottle") in ("condiment", "food")


def test_categorize_falls_back_to_detector_label_without_identity():
    # no identity signal -> keep the detector's label (cleaned)
    assert _categorize("", "", "jar") == "jar"
    assert _categorize("object", "NONE", "bottle") == "bottle"


# --- geometry + counting regression guards (must stay green) --- #

def _inst(box, **kw):
    base = {"box": box, "det_label": kw.get("det_label", "thing"), "name": "",
            "text": "", "colour": "", "material": "", "state": "", "orient": ""}
    base.update(kw)
    return base


def test_on_top_of_relation_from_geometry():
    # B sits directly above A (smaller y), strong x-overlap -> "B on top of A"
    lower = _inst([100, 200, 200, 300], det_label="box")
    upper = _inst([100, 110, 200, 205], det_label="box")
    g = build_graph([lower, upper])
    rels = {(e["from"], e["to"], e["rel"]) for e in g["edges"]}
    assert (1, 0, "on") in rels, f"expected #1 on top of #0, got {g['edges']}"


def test_counts_reflect_distinct_instances():
    insts = [_inst([0, 0, 50, 50], det_label="jar"),
             _inst([60, 0, 110, 50], det_label="jar"),
             _inst([0, 60, 50, 110], det_label="bottle")]
    g = build_graph(insts)
    assert g["counts"].get("jar") == 2
    assert g["counts"].get("bottle") == 1


def test_graph_shape():
    g = build_graph([_inst([0, 0, 10, 10])])
    assert {"nodes", "edges", "counts"} <= set(g)
    assert {"id", "type", "category", "name", "box"} <= set(g["nodes"][0])
