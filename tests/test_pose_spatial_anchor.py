from __future__ import annotations

import math

import scripts.trace_brain_server as brain
from trace_memory.adapters.sqlite_eventlog import SqliteEventLog
from trace_memory.application.entity_binder import bind_entities


_LOCATION_HINT = "GPS 48.2558, 11.6101 | Garching"
_MEMORY_TEXT = "OBJECT | water bottle | blue plastic bottle | likely"


def _capture_payload(*, yaw_degrees: float | None) -> dict[str, object]:
    payload: dict[str, object] = {
        "moment_id": "live",
        "source": "native_vision",
        "location_hint": _LOCATION_HINT,
        "memory_text": _MEMORY_TEXT,
    }
    if yaw_degrees is not None:
        payload["metadata"] = {
            "pose": {
                "qw": 1.0,
                "qx": 0.0,
                "qy": 0.0,
                "qz": 0.0,
                "pitch": 0.0,
                "roll": 0.0,
                "yaw": math.radians(yaw_degrees),
            }
        }
    return payload


def _object_observations(db_path: str) -> tuple:
    log = SqliteEventLog(db_path)
    try:
        return tuple(observation for observation in log.observations() if observation.kind == "object")
    finally:
        log.close()


def test_pose_anchor_splits_different_heading_buckets(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(brain, "CAPTURES", tmp_path)
    monkeypatch.setattr(brain, "TRACE_EVENTLOG", True)
    brain._LIVE.clear()

    brain._capture(_capture_payload(yaw_degrees=0.0))
    brain._capture(_capture_payload(yaw_degrees=40.0))

    observations = _object_observations(str(tmp_path / "live" / "events.db"))

    assert len(observations) == 2
    assert observations[0].spatial_anchor != observations[1].spatial_anchor
    [entity] = bind_entities(observations)
    assert entity.count == 2


def test_pose_anchor_merges_nearby_heading_buckets(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(brain, "CAPTURES", tmp_path)
    monkeypatch.setattr(brain, "TRACE_EVENTLOG", True)
    brain._LIVE.clear()

    brain._capture(_capture_payload(yaw_degrees=0.0))
    brain._capture(_capture_payload(yaw_degrees=5.0))

    observations = _object_observations(str(tmp_path / "live" / "events.db"))

    assert len(observations) == 2
    assert observations[0].spatial_anchor == observations[1].spatial_anchor
    [entity] = bind_entities(observations)
    assert entity.count == 1


def test_missing_pose_keeps_spatial_anchor_none(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(brain, "CAPTURES", tmp_path)
    monkeypatch.setattr(brain, "TRACE_EVENTLOG", True)
    brain._LIVE.clear()

    result = brain._capture(_capture_payload(yaw_degrees=None))
    [observation] = _object_observations(str(tmp_path / "live" / "events.db"))

    assert observation.spatial_anchor is None
    assert observation.t_ms == round(float(result["t"]) * 1000)
