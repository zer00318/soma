from __future__ import annotations

from copy import deepcopy

from scripts.perception_consensus import confident_instances, tier_instances


def _instance(inst_type: str, count_frames: int, frames: list[int], **extra: object) -> dict:
    instance = {
        "type": inst_type,
        "label": inst_type,
        "count_frames": count_frames,
        "frames": frames,
    }
    instance.update(extra)
    return instance


def test_tier_instances_demotes_one_off_and_counts_only_confirmed() -> None:
    consolidated = {
        "instances": [
            _instance("jar", 4, [0, 1, 2, 3], text="nutella"),
            _instance("jar", 3, [2, 3, 4], text="pesto"),
            _instance("doritos", 1, [6], text="doritos"),
        ],
        "counts_by_type": {
            "doritos": {"distinct": 1, "hedge": "1"},
            "jar": {"distinct": 2, "hedge": "2"},
        },
        "summary": "upper bound summary",
    }

    result = tier_instances(consolidated, total_frames=8)

    assert [instance["tier"] for instance in result["instances"]] == [
        "confirmed",
        "confirmed",
        "provisional",
    ]
    assert result["confirmed_counts_by_type"]["jar"] == 2
    assert result["confirmed_counts_by_type"]["doritos"] == 0


def test_tier_instances_assigns_expected_confidence_values() -> None:
    consolidated = {
        "instances": [
            _instance("mug", 1, [0]),
            _instance("mug", 2, [0, 1]),
            _instance("mug", 3, [0, 1, 2]),
            _instance("mug", 7, [0, 1, 2, 3, 4, 5, 6]),
        ],
        "counts_by_type": {"mug": {"distinct": 4, "hedge": "4"}},
    }

    result = tier_instances(consolidated, total_frames=8)

    assert [instance["confidence"] for instance in result["instances"]] == [0.33, 0.67, 1.0, 1.0]


def test_confident_instances_returns_only_confirmed_instances() -> None:
    consolidated = tier_instances(
        {
            "instances": [
                _instance("jar", 4, [0, 1, 2, 3]),
                _instance("jar", 2, [3, 4]),
                _instance("doritos", 1, [6]),
            ],
            "counts_by_type": {"doritos": {"distinct": 1, "hedge": "1"}, "jar": {"distinct": 2, "hedge": "2"}},
        },
        total_frames=8,
    )

    result = confident_instances(consolidated)

    assert len(result) == 2
    assert {instance["type"] for instance in result} == {"jar"}
    assert all(instance["tier"] == "confirmed" for instance in result)


def test_all_provisional_input_has_no_confirmed_counts() -> None:
    consolidated = {
        "instances": [
            _instance("jar", 1, [0]),
            _instance("jar", 1, [4]),
            _instance("chips", 1, [6]),
        ],
        "counts_by_type": {
            "chips": {"distinct": 1, "hedge": "1"},
            "jar": {"distinct": 2, "hedge": "2"},
        },
    }

    result = tier_instances(consolidated, total_frames=8)

    assert all(count == 0 for count in result["confirmed_counts_by_type"].values())
    assert result["summary_confirmed"] == "Nothing confirmed across 8 frame(s)."


def test_tier_instances_does_not_mutate_input() -> None:
    consolidated = {
        "instances": [
            _instance("jar", 2, [0, 1]),
            _instance("chips", 1, [3]),
        ],
        "counts_by_type": {
            "chips": {"distinct": 1, "hedge": "1"},
            "jar": {"distinct": 1, "hedge": "1"},
        },
        "summary": "original summary",
    }
    snapshot = deepcopy(consolidated)

    result = tier_instances(consolidated, total_frames=4)

    assert consolidated == snapshot
    assert all("tier" not in instance for instance in consolidated["instances"])
    assert consolidated["counts_by_type"] == snapshot["counts_by_type"]
    assert result["counts_by_type"] == snapshot["counts_by_type"]


def test_tier_instances_handles_empty_input_safely() -> None:
    result = tier_instances({}, total_frames=0)

    assert result["instances"] == []
    assert result["counts_by_type"] == {}
    assert result["confirmed_counts_by_type"] == {}
    assert result["summary_confirmed"] == "Nothing confirmed across 0 frame(s)."
    assert confident_instances(result) == []

