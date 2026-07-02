"""Acceptance spec for category counting (worker task: graph_count_by_category)."""
from scripts.instance_graph import build_graph, count_by_category


def _inst(box, **kw):
    base = {"box": box, "det_label": "thing", "name": "", "text": "",
            "colour": "", "material": "", "state": "", "orient": ""}
    base.update(kw)
    return base


def test_counts_grouped_by_category():
    insts = [
        _inst([0, 0, 50, 50], name="Lays Xtra Flamin' Hot", det_label="blanket"),
        _inst([60, 0, 110, 50], name="Doritos Tortillas", det_label="bag"),
        _inst([0, 60, 50, 110], name="Apple iPhone", det_label="monitor"),
    ]
    g = build_graph(insts)
    cats = count_by_category(g)
    assert cats.get("snack") == 2     # Lays + Doritos
    assert cats.get("electronics") == 1


def test_skips_empty_and_object_category():
    g = build_graph([_inst([0, 0, 10, 10], det_label="object")])
    cats = count_by_category(g)
    assert "object" not in cats
