#!/usr/bin/env python3
"""Select walk frames from low ARKit camera motion, with a sharpness guard."""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np


FrameLoader = Callable[[float], Any]


def _float_or_none(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _rotation_from_transform(transform: list[Any]) -> np.ndarray | None:
    if len(transform) < 16:
        return None
    nums = [_float_or_none(v) for v in transform[:16]]
    if any(v is None for v in nums):
        return None
    t = [float(v) for v in nums if v is not None]
    # ARKit/simd columns are flattened column-major; position is 12..14.
    return np.array(
        [
            [t[0], t[4], t[8]],
            [t[1], t[5], t[9]],
            [t[2], t[6], t[10]],
        ],
        dtype=np.float64,
    )


def _position_from_transform(transform: list[Any]) -> np.ndarray | None:
    if len(transform) < 15:
        return None
    nums = [_float_or_none(v) for v in transform[12:15]]
    if any(v is None for v in nums):
        return None
    return np.array([float(v) for v in nums if v is not None], dtype=np.float64)


def parse_poses(path: str) -> list[dict[str, Any]]:
    """Parse normal-tracking ARKit poses from an ndjson file."""
    poses: list[dict[str, Any]] = []
    if not path or not os.path.exists(path):
        return poses

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(raw, dict):
                continue
            tracking = str(raw.get("tracking") or raw.get("tracking_state") or "").strip().lower()
            if tracking != "normal":
                continue
            t = _float_or_none(raw.get("t"))
            transform = raw.get("transform")
            if t is None or not isinstance(transform, list):
                continue
            rotation = _rotation_from_transform(transform)
            position = _position_from_transform(transform)
            if rotation is None or position is None:
                continue
            poses.append({"t": t, "R": rotation, "pos": position, "tracking": tracking})

    poses.sort(key=lambda p: p["t"])
    return poses


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    q = max(0.0, min(100.0, percentile)) / 100.0
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    low = math.floor(pos)
    high = math.ceil(pos)
    if low == high:
        return ordered[low]
    frac = pos - low
    return ordered[low] * (1.0 - frac) + ordered[high] * frac


def compute_pose_motions(poses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach angular/translational speed and blended motion to pose deltas."""
    records: list[dict[str, Any]] = []
    if len(poses) < 2:
        return records

    prev = poses[0]
    for pose in poses[1:]:
        dt = float(pose["t"]) - float(prev["t"])
        if dt <= 1e-6:
            prev = pose
            continue
        r_rel = np.asarray(prev["R"], dtype=np.float64).T @ np.asarray(pose["R"], dtype=np.float64)
        cos_angle = (float(np.trace(r_rel)) - 1.0) / 2.0
        cos_angle = max(-1.0, min(1.0, cos_angle))
        angle = math.acos(cos_angle)
        angular_speed = angle / dt
        translational_speed = float(np.linalg.norm(np.asarray(pose["pos"]) - np.asarray(prev["pos"]))) / dt
        motion = angular_speed + 0.5 * translational_speed
        record = dict(pose)
        record.update(
            {
                "angular_speed": angular_speed,
                "translational_speed": translational_speed,
                "motion": motion,
            }
        )
        records.append(record)
        prev = pose
    return records


def select_pose_timestamps(
    poses: list[dict[str, Any]],
    *,
    target_fps: float = 3.0,
    still_percentile: float = 40.0,
) -> tuple[list[dict[str, Any]], float | None]:
    """Select the lowest-motion pose in each target-fps bucket."""
    if target_fps <= 0:
        raise ValueError("target_fps must be positive")
    if not poses:
        print("No usable normal-tracking poses; selected 0 frames.", file=sys.stderr)
        return [], None

    motion_records = compute_pose_motions(poses)
    if not motion_records:
        print("Not enough usable pose deltas; selected 0 frames.", file=sys.stderr)
        return [], None

    motions = [float(p["motion"]) for p in motion_records]
    threshold = _percentile(motions, still_percentile)
    bucket_s = 1.0 / target_fps
    buckets: dict[int, dict[str, Any]] = {}
    for pose in motion_records:
        motion = float(pose["motion"])
        if motion > threshold:
            continue
        bucket = int(math.floor(float(pose["t"]) / bucket_s))
        current = buckets.get(bucket)
        if current is None or motion < float(current["motion"]):
            buckets[bucket] = pose

    selected = [buckets[k] for k in sorted(buckets)]
    return selected, threshold


def frame_sharpness(frame: Any) -> float:
    if frame is None:
        return 0.0
    if len(frame.shape) == 2:
        gray = frame
    else:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _video_frame_loader(video_path: str) -> tuple[FrameLoader, Callable[[], None]]:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise IOError(f"Cannot open video file: {video_path}")

    def load(t: float) -> Any:
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, float(t)) * 1000.0)
        ok, frame = cap.read()
        return frame if ok else None

    return load, cap.release


def write_selected_frames(
    selected: list[dict[str, Any]],
    out_dir: str,
    frame_loader: FrameLoader,
    *,
    min_sharpness: float = 12.0,
) -> list[dict[str, Any]]:
    os.makedirs(out_dir, exist_ok=True)
    manifest: list[dict[str, Any]] = []
    for pose in selected:
        t = float(pose["t"])
        frame = frame_loader(t)
        sharpness = frame_sharpness(frame)
        if frame is None or sharpness < min_sharpness:
            continue
        filename = f"frame_{len(manifest):06d}_{t:.1f}s.jpg"
        path = os.path.join(out_dir, filename)
        ok = cv2.imwrite(path, frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
        if not ok:
            raise IOError(f"Failed to write frame: {path}")
        manifest.append(
            {
                "file": filename,
                "t": round(t, 3),
                "sharpness": round(sharpness, 3),
                "motion": round(float(pose["motion"]), 6),
            }
        )

    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")
    return manifest


def select_sharp_frames(
    poses_path: str,
    video_path: str,
    out_dir: str,
    *,
    target_fps: float = 3.0,
    still_percentile: float = 40.0,
    min_sharpness: float = 12.0,
    frame_loader: FrameLoader | None = None,
) -> tuple[list[dict[str, Any]], int, float | None]:
    poses = parse_poses(poses_path)
    if not poses:
        print(f"No usable poses in {poses_path}; selected 0 frames.")
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
            f.write("[]\n")
        return [], 0, None

    selected, threshold = select_pose_timestamps(
        poses,
        target_fps=target_fps,
        still_percentile=still_percentile,
    )
    if frame_loader is not None:
        manifest = write_selected_frames(selected, out_dir, frame_loader, min_sharpness=min_sharpness)
    else:
        loader, release = _video_frame_loader(video_path)
        try:
            manifest = write_selected_frames(selected, out_dir, loader, min_sharpness=min_sharpness)
        finally:
            release()
    return manifest, len(selected), threshold


def _pose(t: float, angle: float, x: float = 0.0) -> dict[str, Any]:
    c = math.cos(angle)
    s = math.sin(angle)
    return {
        "t": t,
        "R": np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64),
        "pos": np.array([x, 0.0, 0.0], dtype=np.float64),
        "tracking": "normal",
    }


def self_test() -> int:
    poses: list[dict[str, Any]] = []
    for i in range(30):
        poses.append(_pose(i * 0.1, i * 0.2, x=i * 0.01))
    for i in range(30, 60):
        jitter = 0.001 * math.sin(i)
        poses.append(_pose(i * 0.1, 29 * 0.2 + jitter, x=0.29 + 0.0001 * math.cos(i)))

    selected, threshold = select_pose_timestamps(poses, target_fps=3.0, still_percentile=40.0)
    assert threshold is not None and threshold < 0.1, threshold
    assert selected, "expected selected timestamps"
    still = [p for p in selected if float(p["t"]) >= 3.0]
    assert len(still) / len(selected) >= 0.80, [p["t"] for p in selected]

    assert select_pose_timestamps([], target_fps=3.0, still_percentile=40.0)[0] == []

    sharp_frame = np.zeros((80, 80, 3), dtype=np.uint8)
    sharp_frame[::2, :, :] = 255
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest = write_selected_frames(selected, tmpdir, lambda _t: sharp_frame, min_sharpness=12.0)
        assert len(manifest) == len(selected)
        assert all(Path(tmpdir, item["file"]).exists() for item in manifest)
        assert all(item["sharpness"] >= 12.0 for item in manifest)

    print("SELF-TEST PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--poses", default="", help="Input poses.ndjson path")
    parser.add_argument("--video", default="", help="Input video path")
    parser.add_argument("--out-dir", default="/tmp/walk_frames", help="Output frame directory")
    parser.add_argument("--target-fps", type=float, default=3.0, help="Maximum selected frames per second")
    parser.add_argument("--still-percentile", type=float, default=40.0, help="Keep calmest X percent of pose motion")
    parser.add_argument("--min-sharpness", type=float, default=12.0, help="Final Laplacian sharpness guard")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if not args.poses:
        parser.error("--poses required")
    if not args.video:
        parser.error("--video required")

    manifest, considered, threshold = select_sharp_frames(
        args.poses,
        args.video,
        args.out_dir,
        target_fps=args.target_fps,
        still_percentile=args.still_percentile,
        min_sharpness=args.min_sharpness,
    )
    threshold_text = "none" if threshold is None else f"{threshold:.6f}"
    print(
        f"kept {len(manifest)}/{considered} selected pose frames "
        f"(motion_threshold={threshold_text}, still_percentile={args.still_percentile:g}) "
        f"to {args.out_dir}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
