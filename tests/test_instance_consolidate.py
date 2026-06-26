"""Acceptance tests for cross-frame instance consolidation."""
from __future__ import annotations

from scripts.instance_consolidate import consolidate


def _inst(**kwargs) -> dict:
    base = {
        "type": "object",
        "name": "",
        "brand": "",
        "text": "",
        "colour": "",
        "material": "",
        "state": "",
        "orient": "",
        "box": [0.1, 0.1, 0.2, 0.2],
    }
    base.update(kwargs)
    return base


def test_same_texted_jar_across_five_frames_is_one_distinct_instance():
    frames = [[_inst(type="jar", text="nutella")] for _ in range(5)]
    result = consolidate(frames, [0.0, 5.0, 10.0, 15.0, 20.0])

    assert len(result["instances"]) == 1
    assert result["counts_by_type"]["jar"] == {"distinct": 1, "hedge": "1"}
    assert result["instances"][0]["frames"] == [0, 1, 2, 3, 4]
    assert result["instances"][0]["count_frames"] == 5


def test_three_distinct_texted_jars_stay_three_distinct_instances():
    jars = ["nutella", "pesto", "pringles"]
    frames = [
        [_inst(type="jar", text=text, box=[0.1 + index * 0.2, 0.1, 0.1, 0.2]) for index, text in enumerate(jars)],
        [_inst(type="jar", text=text, box=[0.1 + index * 0.2, 0.12, 0.1, 0.2]) for index, text in enumerate(jars)],
        [_inst(type="jar", text=text, box=[0.1 + index * 0.2, 0.11, 0.1, 0.2]) for index, text in enumerate(jars)],
    ]

    result = consolidate(frames, [0.0, 8.0, 15.0])

    assert len(result["instances"]) == 3
    assert result["counts_by_type"]["jar"] == {"distinct": 3, "hedge": "3"}
    assert sorted(instance["text"] for instance in result["instances"]) == jars


def test_mixed_texted_and_untexted_jars_are_hedged_honestly():
    frames = [
        [
            _inst(type="jar", text="nutella"),
            _inst(type="jar", text="pesto"),
            _inst(type="jar", text="pringles"),
            _inst(type="jar"),
        ],
        [
            _inst(type="jar", text="nutella"),
            _inst(type="jar", text="pesto"),
            _inst(type="jar", text="pringles"),
            _inst(type="jar"),
        ],
    ]

    result = consolidate(frames, [0.0, 5.0])

    assert result["counts_by_type"]["jar"]["distinct"] >= 3
    assert result["counts_by_type"]["jar"]["hedge"] == "3-4"


def test_untexted_cups_with_different_colours_stay_distinct():
    frames = [
        [_inst(type="cup", colour="red")],
        [_inst(det_label="cups", colour="blue")],
    ]

    result = consolidate(frames)

    assert len(result["instances"]) == 2
    assert result["counts_by_type"]["cup"] == {"distinct": 2, "hedge": "2"}


def test_same_text_split_by_opposite_yaws_is_not_merged():
    frames = [
        [_inst(type="jar", text="nutella")],
        [_inst(type="jar", text="nutella")],
    ]

    result = consolidate(frames, [0.0, 180.0])

    assert len(result["instances"]) == 2
    assert result["counts_by_type"]["jar"] == {"distinct": 2, "hedge": "2"}


def test_empty_input_returns_empty_instances_and_nonempty_summary():
    result = consolidate([])

    assert result["instances"] == []
    assert result["counts_by_type"] == {}
    assert isinstance(result["summary"], str)
    assert result["summary"].strip()
