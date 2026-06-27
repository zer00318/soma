from __future__ import annotations

from scripts.world_binder import bind_world_instances, count_of, sample_world


IMG_WH = [100.0, 100.0]
GRID_WH = (5, 5)


def _inst(box: list[float], **overrides: object) -> dict[str, object]:
    inst: dict[str, object] = {
        "type": "jar",
        "text": "",
        "name": "",
        "brand": "",
        "box": box,
        "img_wh": list(IMG_WH),
    }
    inst.update(overrides)
    return inst


def _box_for_cell(col: int, row: int, *, size: float = 8.0) -> list[float]:
    grid_w, grid_h = GRID_WH
    cell_w = IMG_WH[0] / grid_w
    cell_h = IMG_WH[1] / grid_h
    center_x = (col + 0.5) * cell_w
    center_y = (row + 0.5) * cell_h
    half = size / 2.0
    return [center_x - half, center_y - half, center_x + half, center_y + half]


def _grid(points: dict[tuple[int, int], list[float] | None]) -> dict[str, object]:
    grid_w, grid_h = GRID_WH
    pts: list[list[float] | None] = [None] * (grid_w * grid_h)
    for (row, col), value in points.items():
        pts[row * grid_w + col] = value
    return {"w": grid_w, "h": grid_h, "pts": pts}


def _same_jar_result() -> dict[str, object]:
    frames = [
        [_inst(_box_for_cell(2, 2), text="Nutella")],
        [_inst(_box_for_cell(2, 2), text="Aleksandar")],
        [_inst(_box_for_cell(2, 2), text="Kinder")],
        [_inst(_box_for_cell(2, 2), text="nutella")],
    ]
    grids = [
        _grid({(2, 2): [1.00, 0.50, 2.00]}),
        _grid({(2, 2): [1.02, 0.49, 2.01]}),
        _grid({(2, 2): [0.99, 0.50, 1.99]}),
        _grid({(2, 2): [1.01, 0.51, 2.00]}),
    ]
    return bind_world_instances(frames, grids)


def test_sample_world_returns_nearest_point_and_none_for_empty_grid() -> None:
    center_box = _box_for_cell(2, 2)
    grid = _grid({(2, 3): [1.2, 2.3, 3.4]})

    assert sample_world(center_box, IMG_WH, grid) == [1.2, 2.3, 3.4]
    assert sample_world(center_box, IMG_WH, _grid({})) is None


def test_same_jar_across_frames_merges_to_one_located_node() -> None:
    result = _same_jar_result()

    assert len(result["nodes"]) == 1
    assert result["counts_by_type"] == {"jar": {"distinct": 1, "located": 1}}
    node = result["nodes"][0]
    assert node["located"] is True
    assert node["count_frames"] == 4
    assert node["frames"] == [0, 1, 2, 3]
    assert node["texts"] == ["Nutella", "Aleksandar", "Kinder"]


def test_two_jars_thirty_centimeters_apart_stay_distinct() -> None:
    frames = [[
        _inst(_box_for_cell(1, 2), text="jar"),
        _inst(_box_for_cell(3, 2), text="jar"),
    ]]
    grids = [_grid({
        (2, 1): [0.00, 0.00, 0.00],
        (2, 3): [0.30, 0.00, 0.00],
    })]

    result = bind_world_instances(frames, grids)

    assert len(result["nodes"]) == 2
    assert result["counts_by_type"] == {"jar": {"distinct": 2, "located": 2}}


def test_two_detections_within_eps_merge_to_one_node() -> None:
    frames = [[
        _inst(_box_for_cell(1, 2), text="jar-a"),
        _inst(_box_for_cell(2, 2), text="jar-b"),
    ]]
    grids = [_grid({
        (2, 1): [0.00, 0.00, 0.00],
        (2, 2): [0.05, 0.00, 0.00],
    })]

    result = bind_world_instances(frames, grids)

    assert len(result["nodes"]) == 1
    assert result["counts_by_type"] == {"jar": {"distinct": 1, "located": 1}}
    assert result["nodes"][0]["count_frames"] == 1


def test_missing_grid_coverage_creates_unlocated_node() -> None:
    frames = [[_inst(_box_for_cell(2, 2), text="Nutella")]]
    result = bind_world_instances(frames, [None])

    assert len(result["nodes"]) == 1
    assert result["counts_by_type"] == {"jar": {"distinct": 1, "located": 0}}
    assert result["nodes"][0]["located"] is False
    assert result["nodes"][0]["world_xyz"] is None


def test_count_of_matches_node_texts_across_cluster_reads() -> None:
    result = _same_jar_result()

    assert count_of(result, "nutella") == 1
