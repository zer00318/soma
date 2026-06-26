from __future__ import annotations

import math

from trace_memory.adapters.live_eventlog import HONEST_REFUSAL, answer_question, append_perception_observations


def _append_object(
    db_path,
    *,
    subject: str,
    t_seconds: float,
    yaw_degrees: float | None,
) -> None:
    pose = None
    if yaw_degrees is not None:
        pose = {
            "qw": 1.0,
            "qx": 0.0,
            "qy": 0.0,
            "qz": 0.0,
            "pitch": 0.0,
            "roll": 0.0,
            "yaw": math.radians(yaw_degrees),
        }
    append_perception_observations(
        db_path,
        moment_id="scene",
        t_seconds=t_seconds,
        memory_text=f"OBJECT | {subject} | demo object | likely",
        ocr_lines=[],
        pose=pose,
        location_hint="demo shelf",
    )


def _seed_ab_fixture(db_path) -> None:
    _append_object(db_path, subject="A", t_seconds=1.0, yaw_degrees=10.0)
    _append_object(db_path, subject="B", t_seconds=3.0, yaw_degrees=80.0)


def test_temporal_first_returns_earliest_object_with_time(tmp_path) -> None:
    db_path = tmp_path / "events.db"
    _seed_ab_fixture(db_path)

    result = answer_question("what did I see first", db_path)

    assert result.supported is True
    assert result.refused is False
    assert "a" in result.answer.lower()
    assert "1.0s" in result.answer.lower()


def test_temporal_relative_and_order_answers_use_event_times(tmp_path) -> None:
    db_path = tmp_path / "events.db"
    _seed_ab_fixture(db_path)

    before = answer_question("what came before B", db_path)
    after = answer_question("what came after A", db_path)
    order = answer_question("in what order", db_path)

    assert before.refused is False
    assert "a at 1.0s" in before.answer.lower()
    assert after.refused is False
    assert "b at 3.0s" in after.answer.lower()
    assert order.refused is False
    assert "a at 1.0s" in order.answer.lower()
    assert "b at 3.0s" in order.answer.lower()


def test_spatial_relative_side_uses_yaw_buckets(tmp_path) -> None:
    db_path = tmp_path / "events.db"
    _seed_ab_fixture(db_path)

    result = answer_question("which side was A relative to B", db_path)

    assert result.supported is True
    assert result.refused is False
    assert "a was to the left of b" in result.answer.lower()


def test_spatial_side_of_reference_returns_other_objects(tmp_path) -> None:
    db_path = tmp_path / "events.db"
    _seed_ab_fixture(db_path)

    result = answer_question("what was to the left of B", db_path)

    assert result.refused is False
    assert "to the left of b" in result.answer.lower()
    assert "a at 1.0s" in result.answer.lower()


def test_where_absent_subject_refuses(tmp_path) -> None:
    db_path = tmp_path / "events.db"
    _seed_ab_fixture(db_path)

    result = answer_question("where was a zebra", db_path)

    assert result.supported is True
    assert result.refused is True
    assert result.answer == HONEST_REFUSAL


def test_where_seen_without_pose_is_honest_about_missing_location(tmp_path) -> None:
    db_path = tmp_path / "events.db"
    _append_object(db_path, subject="water bottle", t_seconds=1.0, yaw_degrees=None)

    result = answer_question("where was the water bottle", db_path)

    assert result.refused is False
    assert "didn't track exactly where" in result.answer.lower()
