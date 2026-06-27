from scripts.spatial_relations import describe, relations


def _node(label, xyz):
    return {"label": label, "type": "object", "world_xyz": xyz}


def _has_relation(rows, source, target, rel):
    return any(
        row["from"] == source and row["to"] == target and row["rel"] == rel for row in rows
    )


def test_horizontal_left_right_relation():
    rows = relations([_node("A", (0.0, 0.0, 0.0)), _node("B", (0.3, 0.0, 0.0))])
    assert _has_relation(rows, "A", "B", "left of")
    assert _has_relation(rows, "B", "A", "right of")


def test_vertical_above_relation():
    rows = relations([_node("A", (0.0, 0.0, 0.0)), _node("B", (0.0, 0.3, 0.0))])
    assert _has_relation(rows, "B", "A", "above")


def test_depth_in_front_of_relation():
    rows = relations([_node("A", (0.0, 0.0, 0.0)), _node("B", (0.0, 0.0, 0.4))])
    assert _has_relation(rows, "B", "A", "in front of")


def test_next_to_relation_for_close_horizontal_neighbors():
    rows = relations([_node("A", (0.0, 0.0, 0.0)), _node("B", (0.1, 0.01, 0.01))])
    assert _has_relation(rows, "A", "B", "next to")
    assert _has_relation(rows, "B", "A", "next to")


def test_on_top_of_relation_for_close_vertical_stack():
    rows = relations([_node("A", (0.0, 0.0, 0.0)), _node("B", (0.01, 0.12, 0.0))])
    assert _has_relation(rows, "B", "A", "on top of")


def test_skips_missing_world_xyz_and_describe_is_readable():
    nodes = [
        _node("Nutella", (0.0, 0.0, 0.0)),
        {"label": "Ghost", "type": "object", "world_xyz": None},
        _node("Pesto", (0.08, 0.0, 0.0)),
    ]
    rows = relations(nodes)
    assert all("Ghost" not in (row["from"], row["to"]) for row in rows)
    assert describe(nodes) == ["Nutella is to the left of and next to Pesto (0.08 m)."]
