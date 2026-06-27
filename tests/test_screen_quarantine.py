from __future__ import annotations

from scripts.screen_quarantine import mark_on_screen, physical_only


IMG_WH = [1000.0, 1000.0]


def _inst(type_name: str, box: list[float], **overrides: object) -> dict[str, object]:
    inst: dict[str, object] = {
        "type": type_name,
        "box": box,
        "img_wh": list(IMG_WH),
    }
    inst.update(overrides)
    return inst


def test_marks_detection_inside_laptop_as_on_screen_without_mutating_input() -> None:
    instances = [
        _inst("laptop", [0, 0, 1000, 700]),
        _inst("jar", [100, 100, 300, 300]),
    ]

    annotated = mark_on_screen(instances)

    assert annotated[0]["on_screen"] is False
    assert annotated[1]["on_screen"] is True
    assert annotated[1]["screen_type"] == "laptop"
    assert "on_screen" not in instances[0]
    assert "on_screen" not in instances[1]
    assert "screen_type" not in instances[1]


def test_leaves_outside_detection_as_physical() -> None:
    annotated = mark_on_screen(
        [
            _inst("laptop", [0, 0, 1000, 700]),
            _inst("jar", [800, 800, 950, 950]),
        ]
    )

    assert annotated[0]["on_screen"] is False
    assert annotated[1]["on_screen"] is False
    assert "screen_type" not in annotated[1]


def test_physical_only_drops_on_screen_detections() -> None:
    annotated = mark_on_screen(
        [
            _inst("laptop", [0, 0, 1000, 700]),
            _inst("jar", [100, 100, 300, 300]),
            _inst("jar", [800, 800, 950, 950]),
        ]
    )

    physical = physical_only(annotated)

    assert len(physical) == 2
    assert physical[0]["type"] == "laptop"
    assert physical[1]["box"] == [800, 800, 950, 950]


def test_no_screen_present_marks_nothing_on_screen() -> None:
    annotated = mark_on_screen(
        [
            _inst("jar", [100, 100, 300, 300]),
            _inst("cup", [400, 400, 550, 600]),
        ]
    )

    assert [inst["on_screen"] for inst in annotated] == [False, False]
    assert physical_only(annotated) == annotated


def test_partial_overlap_below_threshold_is_not_quarantined() -> None:
    annotated = mark_on_screen(
        [
            _inst("monitor", [0, 0, 500, 500]),
            _inst("jar", [300, 100, 800, 300]),
        ]
    )

    assert annotated[1]["on_screen"] is False
    assert "screen_type" not in annotated[1]


def test_marks_detection_with_containing_screen_type_when_multiple_screens_exist() -> None:
    annotated = mark_on_screen(
        [
            _inst("monitor", [0, 0, 250, 250]),
            _inst("tablet", [500, 500, 900, 900]),
            _inst("jar", [600, 600, 700, 700]),
        ]
    )

    assert annotated[2]["on_screen"] is True
    assert annotated[2]["screen_type"] == "tablet"
