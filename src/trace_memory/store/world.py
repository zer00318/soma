from __future__ import annotations

import math
from typing import Any

from trace_memory.store.models import CoordinateFrame, MemoryNode, SpatialAnchor, TimeRange


def session_coordinate_frame(session_id: str, *, origin_id: str = "arkit_session_origin") -> CoordinateFrame:
    return CoordinateFrame(session_id=session_id, origin_id=origin_id)


def observation_time_range(t_ms: int, *, duration_ms: int = 0) -> TimeRange:
    return TimeRange(start_ms=t_ms, end_ms=t_ms + max(0, int(duration_ms)))


def scene_frustum_anchor(
    *,
    pose: dict[str, Any] | None,
    origin_xyz: tuple[float, float, float] | None = None,
    depth_m: float | None = None,
    frame_size: tuple[int, int] | None = None,
    metadata: dict[str, Any] | None = None,
) -> SpatialAnchor:
    pose = dict(pose or {})
    orientation = {
        key: float(pose[key])
        for key in ("yaw", "pitch", "roll", "yaw_deg", "pitch_deg", "roll_deg")
        if isinstance(pose.get(key), (int, float))
    }
    if origin_xyz is not None:
        coordinates = {"origin_xyz": [float(value) for value in origin_xyz]}
    else:
        coordinates = {}
    bounds: dict[str, Any] = {}
    if depth_m is not None:
        bounds["depth_m"] = float(depth_m)
    if frame_size is not None:
        bounds["frame_size"] = [int(frame_size[0]), int(frame_size[1])]
    return SpatialAnchor(
        kind="scene_frustum",
        coordinates=coordinates,
        orientation=orientation,
        bounds=bounds,
        metadata=dict(metadata or {}),
    )


def world_point_anchor(
    xyz: tuple[float, float, float],
    *,
    radius_m: float = 0.35,
    metadata: dict[str, Any] | None = None,
) -> SpatialAnchor:
    return SpatialAnchor(
        kind="world_point",
        coordinates={"xyz": [float(value) for value in xyz]},
        bounds={"radius_m": float(radius_m)},
        metadata=dict(metadata or {}),
    )


def world_region_anchor(
    center_xyz: tuple[float, float, float],
    size_xyz: tuple[float, float, float],
    *,
    metadata: dict[str, Any] | None = None,
) -> SpatialAnchor:
    return SpatialAnchor(
        kind="world_region",
        coordinates={"center_xyz": [float(value) for value in center_xyz]},
        bounds={"size_xyz": [float(value) for value in size_xyz]},
        metadata=dict(metadata or {}),
    )


def projected_crop_anchor(
    bbox_norm: tuple[float, float, float, float],
    *,
    world_xyz: tuple[float, float, float] | None = None,
    metadata: dict[str, Any] | None = None,
) -> SpatialAnchor:
    coordinates: dict[str, Any] = {}
    if world_xyz is not None:
        coordinates["world_xyz"] = [float(value) for value in world_xyz]
    return SpatialAnchor(
        kind="projected_crop",
        coordinates=coordinates,
        bounds={"bbox_norm": [float(value) for value in bbox_norm]},
        metadata=dict(metadata or {}),
    )


def audio_origin_anchor(
    xyz: tuple[float, float, float],
    *,
    radius_m: float = 0.75,
    metadata: dict[str, Any] | None = None,
) -> SpatialAnchor:
    return SpatialAnchor(
        kind="audio_origin",
        coordinates={"xyz": [float(value) for value in xyz]},
        bounds={"radius_m": float(radius_m)},
        metadata=dict(metadata or {}),
    )


def anchor_centroid(anchor: SpatialAnchor | dict[str, Any] | None) -> tuple[float, float, float] | None:
    if anchor is None:
        return None
    anchor = SpatialAnchor.from_value(anchor)
    coords = anchor.coordinates
    if "xyz" in coords:
        xyz = coords["xyz"]
        return float(xyz[0]), float(xyz[1]), float(xyz[2])
    if "center_xyz" in coords:
        xyz = coords["center_xyz"]
        return float(xyz[0]), float(xyz[1]), float(xyz[2])
    if "world_xyz" in coords:
        xyz = coords["world_xyz"]
        return float(xyz[0]), float(xyz[1]), float(xyz[2])
    if "origin_xyz" in coords:
        xyz = coords["origin_xyz"]
        return float(xyz[0]), float(xyz[1]), float(xyz[2])
    return None


def _orientation(anchor: SpatialAnchor) -> tuple[float | None, float | None]:
    orientation = anchor.orientation
    yaw = orientation.get("yaw_deg")
    pitch = orientation.get("pitch_deg")
    if not isinstance(yaw, (int, float)):
        yaw = orientation.get("yaw")
    if not isinstance(pitch, (int, float)):
        pitch = orientation.get("pitch")
    return (
        float(yaw) if isinstance(yaw, (int, float)) else None,
        float(pitch) if isinstance(pitch, (int, float)) else None,
    )


def _angular_distance(left: SpatialAnchor, right: SpatialAnchor) -> float | None:
    left_yaw, left_pitch = _orientation(left)
    right_yaw, right_pitch = _orientation(right)
    if left_yaw is None or right_yaw is None:
        return None
    pitch_term = 0.0
    if left_pitch is not None and right_pitch is not None:
        pitch_term = abs(left_pitch - right_pitch)
    return abs(left_yaw - right_yaw) + pitch_term


def _euclidean(left: tuple[float, float, float], right: tuple[float, float, float]) -> float:
    return math.sqrt(sum((l - r) ** 2 for l, r in zip(left, right)))


def time_overlap_score(
    left: TimeRange | dict[str, Any] | None,
    right: TimeRange | dict[str, Any] | None,
) -> float:
    if left is None or right is None:
        return 0.0
    left = TimeRange.from_value(left, default_t_ms=0)
    right = TimeRange.from_value(right, default_t_ms=0)
    overlap = max(0, min(left.end_ms, right.end_ms) - max(left.start_ms, right.start_ms))
    if overlap > 0:
        return 1.0
    gap = min(abs(left.end_ms - right.start_ms), abs(right.end_ms - left.start_ms))
    if gap <= 1_000:
        return 0.85
    if gap <= 3_000:
        return 0.6
    if gap <= 8_000:
        return 0.35
    return 0.0


def spatial_overlap_score(
    left: SpatialAnchor | dict[str, Any] | None,
    right: SpatialAnchor | dict[str, Any] | None,
) -> float:
    if left is None or right is None:
        return 0.0
    left = SpatialAnchor.from_value(left)
    right = SpatialAnchor.from_value(right)

    left_xyz = anchor_centroid(left)
    right_xyz = anchor_centroid(right)
    if left_xyz is not None and right_xyz is not None:
        distance = _euclidean(left_xyz, right_xyz)
        if distance <= 0.5:
            return 1.0
        if distance <= 1.0:
            return 0.75
        if distance <= 2.0:
            return 0.45
        return 0.0

    angle = _angular_distance(left, right)
    if angle is not None:
        if angle <= 12.0:
            return 0.9
        if angle <= 24.0:
            return 0.6
        if angle <= 40.0:
            return 0.35
        return 0.0

    left_frames = tuple(left.metadata.get("frame_ids") or ())
    right_frames = tuple(right.metadata.get("frame_ids") or ())
    if left_frames and right_frames and set(left_frames) & set(right_frames):
        return 0.8
    return 0.0


def same_coordinate_frame(left: MemoryNode, right: MemoryNode) -> bool:
    if left.coordinate_frame is None or right.coordinate_frame is None:
        return False
    return (
        left.coordinate_frame.session_id == right.coordinate_frame.session_id
        and left.coordinate_frame.origin_id == right.coordinate_frame.origin_id
    )


def observation_overlap_score(left: MemoryNode, right: MemoryNode) -> float:
    if not same_coordinate_frame(left, right):
        return 0.0
    spatial = spatial_overlap_score(left.spatial_anchor, right.spatial_anchor)
    temporal = time_overlap_score(left.time_range, right.time_range)
    if spatial <= 0.0 or temporal <= 0.0:
        return 0.0
    return round((spatial * 0.7) + (temporal * 0.3), 6)
