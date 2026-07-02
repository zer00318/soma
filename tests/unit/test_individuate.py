from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from trace_memory.store.individuate import canonical_label, individuate


@dataclass
class FakeNode:
    id: str
    text: str
    t_ms: int = 0
    helper_type: str = "vlm_object"
    place: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _n(id, text, **kw) -> FakeNode:
    return FakeNode(id=id, text=text, **kw)


def test_canonical_label_strips_qualifiers_and_context():
    assert canonical_label(_n("a", "Large Nutella jar, brown label")) == "nutella jar"
    assert canonical_label(_n("b", "Second Nutella jar below, same label")) == "nutella jar"
    # Colour is kept as part of identity (a "blue suitcase" is more specific than "suitcase").
    assert canonical_label(_n("c", "", metadata={"subject_hint": "Blue Suitcase"})) == "blue suitcase"


def test_same_object_variants_merge_but_distinct_objects_do_not():
    nodes = [
        _n("1", "Large Nutella jar"),
        _n("2", "Second Nutella jar below"),
        _n("3", "Barilla pesto jar"),
        _n("4", "jar of pesto, Barilla brand"),
    ]
    clusters = {c.label: c for c in individuate(nodes) if c.kind == "entity"}
    # nutella variants collapse to one cluster...
    nutella = [c for c in clusters.values() if "nutella" in c.label]
    assert len(nutella) == 1
    assert len(nutella[0].members) == 2
    # ...but pesto jars must NOT merge into the nutella cluster just because both are "jar".
    assert all("pesto" not in c.label for c in nutella)


def test_screen_text_is_excluded_from_physical_binding():
    nodes = [
        _n("1", "white pillow on bed"),
        _n("2", "Claude chat sidebar text", metadata={"section_kind": "screen_text"}),
    ]
    labels = [c.label for c in individuate(nodes) if c.kind == "entity"]
    assert any("pillow" in lab for lab in labels)
    assert not any("claude" in lab or "sidebar" in lab for lab in labels)


def test_affordance_group_forms_for_water_and_excludes_eyewear():
    nodes = [
        _n("1", "silver stainless steel water bottle"),
        _n("2", "white water bottle"),
        _n("3", "stainless steel cup"),
        _n("4", "round black frame glasses"),  # eyewear -> must NOT join "drink water"
    ]
    groups = [c for c in individuate(nodes) if c.kind == "group"]
    water = [g for g in groups if g.affordance == "drink water"]
    assert water, "expected a 'ways to drink water' group"
    joined = " ".join(canonical_label(m) for m in water[0].members)
    assert "bottle" in joined and "cup" in joined
    assert "glass" not in joined  # eyewear excluded


def test_no_mega_blob_from_hub_word():
    # A generic "jar" hub plus many distinct branded jars must stay separate, not collapse.
    nodes = [_n("0", "jar")]
    for i, brand in enumerate(["nutella", "pesto", "honey", "jam", "coffee"]):
        nodes.append(_n(str(i + 1), f"{brand} jar"))
    ents = [c for c in individuate(nodes) if c.kind == "entity"]
    assert max(len(c.members) for c in ents) <= 2
