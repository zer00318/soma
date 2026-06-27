from __future__ import annotations

import pytest

from scripts.instance_consolidate import (
    H_FOV_DEG,
    V_FOV_DEG,
    consolidate,
    consolidate_world,
    detection_bearing,
)


IMG_WH = [1000, 800]


def _inst(box: list[float], **kwargs) -> dict:
    base = {
        "type": "object",
        "name": "",
        "brand": "",
        "text": "",
        "colour": "",
        "material": "",
        "state": "",
        "orient": "",
        "box": box,
        "img_wh": list(IMG_WH),
    }
    base.update(kwargs)
    return base


def _box_for_world_bearing(
    world_azimuth_deg: float,
    cam_yaw_deg: float,
    *,
    world_elevation_deg: float = 0.0,
    cam_pitch_deg: float = 0.0,
    width_px: float = 120.0,
    height_px: float = 160.0,
) -> list[float]:
    width, height = IMG_WH
    center_x = width * (0.5 + (world_azimuth_deg - cam_yaw_deg) / H_FOV_DEG)
    center_y = height * (0.5 - (world_elevation_deg - cam_pitch_deg) / V_FOV_DEG)
    half_w = width_px / 2.0
    half_h = height_px / 2.0
    return [
        center_x - half_w,
        center_y - half_h,
        center_x + half_w,
        center_y + half_h,
    ]


def test_world_anchor_merges_same_jar_across_pan_despite_varying_text() -> None:
    yaws = [0.0, 5.0, 10.0, 15.0]
    texts = ["Nutella", "Aleksandar", "Kinder", "nutella"]
    frames = [
        [_inst(_box_for_world_bearing(2.0, yaw), type="jar", text=text)]
        for yaw, text in zip(yaws, texts)
    ]
    poses = [{"yaw": yaw, "pitch": 0.0} for yaw in yaws]

    result = consolidate_world(frames, poses)

    assert len(result["instances"]) == 1
    assert result["counts_by_type"]["jar"] == {"distinct": 1, "hedge": "1"}
    assert result["instances"][0]["count_frames"] == 4
    assert result["instances"][0]["frames"] == [0, 1, 2, 3]
    assert result["instances"][0]["text"] == "Nutella"


def test_two_side_by_side_jars_in_one_frame_stay_distinct() -> None:
    left_box = _box_for_world_bearing(-12.0, 0.0)
    right_box = _box_for_world_bearing(12.0, 0.0)
    left_bearing = detection_bearing(left_box, IMG_WH, 0.0, 0.0)
    right_bearing = detection_bearing(right_box, IMG_WH, 0.0, 0.0)

    result = consolidate_world(
        [[_inst(left_box, type="jar", text="jar"), _inst(right_box, type="jar", text="jar")]],
        [{"yaw": 0.0, "pitch": 0.0}],
    )

    assert right_bearing[0] - left_bearing[0] > 9.0
    assert len(result["instances"]) == 2
    assert result["counts_by_type"]["jar"] == {"distinct": 2, "hedge": "2"}


def test_three_distinct_jars_across_pan_stay_three() -> None:
    yaws = [0.0, 5.0, 10.0]
    world_azimuths = [-12.0, 2.0, 18.0]
    frames = []
    for yaw in yaws:
        frames.append(
            [
                _inst(_box_for_world_bearing(world_azimuth, yaw), type="jar", text=f"read-{index}-{yaw}")
                for index, world_azimuth in enumerate(world_azimuths)
            ]
        )

    result = consolidate_world(frames, [{"yaw": yaw, "pitch": 0.0} for yaw in yaws])

    assert len(result["instances"]) == 3
    assert result["counts_by_type"]["jar"] == {"distinct": 3, "hedge": "3"}


def test_detection_bearing_tracks_center_and_far_right_offsets() -> None:
    center_box = [450.0, 320.0, 550.0, 480.0]
    right_box = [950.0, 320.0, 1050.0, 480.0]

    center = detection_bearing(center_box, IMG_WH, 30.0, -5.0)
    right = detection_bearing(right_box, IMG_WH, 30.0, -5.0)

    assert center == pytest.approx((30.0, -5.0))
    assert right[0] == pytest.approx(30.0 + H_FOV_DEG / 2.0)
    assert right[1] == pytest.approx(-5.0)


def test_world_anchor_without_pose_falls_back_to_text_consolidation() -> None:
    frames = [
        [_inst(_box_for_world_bearing(2.0, 0.0), type="jar", text="Nutella")],
        [_inst(_box_for_world_bearing(2.0, 5.0), type="jar", text="Aleksandar")],
        [_inst(_box_for_world_bearing(2.0, 10.0), type="jar", text="Kinder")],
        [_inst(_box_for_world_bearing(2.0, 15.0), type="jar", text="nutella")],
    ]

    world_result = consolidate_world(frames, [None, None, None, None])
    legacy_result = consolidate(frames)

    assert world_result["counts_by_type"] == legacy_result["counts_by_type"]
    assert len(world_result["instances"]) == len(legacy_result["instances"])


def test_world_anchor_splits_same_azimuth_by_elevation() -> None:
    yaws = [0.0, 3.0]
    elevations = [12.0, -12.0]
    frames = []
    for yaw in yaws:
        frames.append(
            [
                _inst(
                    _box_for_world_bearing(4.0, yaw, world_elevation_deg=elevation),
                    type="jar",
                    text="jar",
                )
                for elevation in elevations
            ]
        )

    result = consolidate_world(frames, [{"yaw": yaw, "pitch": 0.0} for yaw in yaws])

    assert len(result["instances"]) == 2
    assert result["counts_by_type"]["jar"] == {"distinct": 2, "hedge": "2"}
