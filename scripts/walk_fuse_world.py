#!/usr/bin/env python3
"""Fuse offline walk inventory objects into an approximate world map.

Inputs come from the Mac-side walk pipeline:
  walk_extract_frames.py -> walk_segment_frames.py -> walk_label_crops.py ->
  walk_build_inventory.py

When ARKit poses are available, crop centers are backprojected through the
nearest camera pose and clustered by label. Without poses, the output remains
ingestable as positionless inventory.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _load_json(path: str | None, default: Any) -> Any:
    if not path or str(path).upper() == "NONE":
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _clamp01(value: Any, default: float = 0.0) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = default
    if not math.isfinite(score):
        return default
    return max(0.0, min(1.0, score))


def _float_or_none(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _norm_label(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _norm_trust(value: Any) -> str:
    trust = str(value or "trusted").strip().lower()
    return "rejected" if trust == "rejected" else "trusted"


def _name_source(value: Any) -> str:
    return str(value or "").strip() or "unknown"


def _crop_path(record: dict[str, Any]) -> str:
    for key in ("crop_path", "crop", "path", "file"):
        value = record.get(key)
        if value:
            return str(value)
    return ""


def _frame_key_from_crop(path: str) -> str:
    base = os.path.basename(path)
    match = re.match(r"(.+?)_obj\d+\.[A-Za-z0-9]+$", base)
    if match:
        return match.group(1)
    return os.path.splitext(base)[0]


def _frame_key(path: str) -> str:
    base = os.path.basename(path)
    return os.path.splitext(base)[0]


def _timestamp_from_name(path: str) -> float | None:
    match = re.search(r"_([0-9]+(?:\.[0-9]+)?)s(?:\.|$)", os.path.basename(path))
    return _float_or_none(match.group(1)) if match else None


def _manifest_lookup(manifest: list[Any], frames_manifest_path: str | None = None) -> dict[str, float]:
    lookup: dict[str, float] = {}
    base_dir = Path(frames_manifest_path).resolve().parent if frames_manifest_path else None
    for entry in manifest:
        if not isinstance(entry, dict):
            continue
        file_value = str(entry.get("file") or entry.get("frame") or entry.get("path") or "")
        if not file_value:
            continue
        t = _float_or_none(entry.get("t"))
        if t is None:
            t = _float_or_none(entry.get("timestamp"))
        if t is None:
            t = _timestamp_from_name(file_value)
        if t is None:
            continue
        keys = {
            file_value,
            os.path.basename(file_value),
            _frame_key(file_value),
        }
        if base_dir is not None and not os.path.isabs(file_value):
            abs_path = str(base_dir / file_value)
            keys.add(abs_path)
            keys.add(os.path.basename(abs_path))
            keys.add(_frame_key(abs_path))
        for key in keys:
            lookup[key] = t
    return lookup


def _record_time(record: dict[str, Any], manifest_times: dict[str, float]) -> float | None:
    for key in ("t", "timestamp", "frame_t", "frame_time"):
        t = _float_or_none(record.get(key))
        if t is not None:
            return t

    frame = str(record.get("frame") or record.get("source_frame") or record.get("frame_path") or "")
    crop = _crop_path(record)
    candidates = []
    if frame:
        candidates.extend([frame, os.path.basename(frame), _frame_key(frame)])
    if crop:
        candidates.extend([crop, os.path.basename(crop), _frame_key_from_crop(crop)])
    for candidate in candidates:
        if candidate in manifest_times:
            return manifest_times[candidate]
    for candidate in candidates:
        t = _timestamp_from_name(candidate)
        if t is not None:
            return t
    return None


def _record_box_center(record: dict[str, Any]) -> tuple[float, float] | None:
    box = record.get("box") or record.get("bbox") or record.get("xyxy")
    if isinstance(box, dict):
        vals = [box.get(k) for k in ("x1", "y1", "x2", "y2")]
    elif isinstance(box, list) and len(box) >= 4:
        vals = box[:4]
    else:
        return None
    nums = [_float_or_none(v) for v in vals]
    if any(v is None for v in nums):
        return None
    x1, y1, x2, y2 = [float(v) for v in nums if v is not None]
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def _labels_from_file(labels_json: Any) -> list[dict[str, Any]]:
    labels: list[dict[str, Any]] = []
    if isinstance(labels_json, list):
        source = labels_json
    elif isinstance(labels_json, dict):
        source = labels_json.get("labels") or labels_json.get("crops") or []
    else:
        source = []
    for record in source:
        if not isinstance(record, dict):
            continue
        label = record.get("label") or record.get("word") or record.get("name")
        label_norm = _norm_label(label)
        if not label_norm:
            continue
        item = dict(record)
        item["label"] = label_norm
        item["score"] = _clamp01(record.get("score", record.get("confidence", 0.0)))
        item["crop_path"] = _crop_path(record)
        item["trust"] = _norm_trust(record.get("trust"))
        item["name_source"] = _name_source(record.get("name_source"))
        if record.get("clip_word"):
            item["clip_word"] = _norm_label(record.get("clip_word"))
        if record.get("gemma_label"):
            item["gemma_label"] = _norm_label(record.get("gemma_label"))
        labels.append(item)
    return labels


def _inventory_objects(inventory_json: Any, labels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    if isinstance(inventory_json, dict):
        entries = inventory_json.get("objects") if isinstance(inventory_json.get("objects"), list) else None
        if entries is not None:
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                label = _norm_label(entry.get("label") or entry.get("word"))
                if not label:
                    continue
                examples = entry.get("frame_evidence") or entry.get("examples") or []
                if not isinstance(examples, list):
                    examples = []
                objects.append({
                    "label": label,
                    "count": int(entry.get("count") or len(examples) or 1),
                    "confidence": _clamp01(entry.get("confidence", entry.get("score_mean", entry.get("score_max", 0.0)))),
                    "frame_evidence": [str(p) for p in examples],
                    "trust": _norm_trust(entry.get("trust")),
                    "name_source": _name_source(entry.get("name_source")),
                    "trusted_count": int(entry.get("trusted_count") or 0),
                    "rejected_count": int(entry.get("rejected_count") or 0),
                })
            return objects
        for label, entry in inventory_json.items():
            if not isinstance(entry, dict):
                continue
            label_norm = _norm_label(label)
            if not label_norm:
                continue
            examples = entry.get("examples") or entry.get("frame_evidence") or []
            if not isinstance(examples, list):
                examples = []
            trust = _norm_trust(entry.get("trust"))
            trusted_count = int(entry.get("trusted_count") or 0)
            rejected_count = int(entry.get("rejected_count") or 0)
            raw_count = int(entry.get("count") or len(examples) or 1)
            count = trusted_count if trust == "trusted" and trusted_count else rejected_count if trust == "rejected" and rejected_count else raw_count
            objects.append({
                "label": label_norm,
                "count": count,
                "confidence": _clamp01(entry.get("score_mean", entry.get("score_max", 0.0))),
                "frame_evidence": [str(p) for p in examples],
                "trust": trust,
                "name_source": _name_source(entry.get("name_source")),
                "trusted_count": trusted_count,
                "rejected_count": rejected_count,
            })
    if objects:
        return objects

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for label in labels:
        grouped[str(label["label"])].append(label)
    for label, rows in grouped.items():
        objects.append({
            "label": label,
            "count": len(rows),
            "confidence": sum(_clamp01(r.get("score")) for r in rows) / max(1, len(rows)),
            "frame_evidence": [str(r.get("crop_path") or "") for r in rows if r.get("crop_path")],
            "trust": "trusted" if any(r.get("trust") == "trusted" for r in rows) else "rejected",
            "name_source": _name_source(rows[0].get("name_source") if rows else ""),
            "trusted_count": sum(1 for r in rows if r.get("trust") == "trusted"),
            "rejected_count": sum(1 for r in rows if r.get("trust") == "rejected"),
        })
    return objects


def _load_poses(path: str | None) -> list[dict[str, Any]]:
    if not path or str(path).upper() == "NONE":
        return []
    poses: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                pose = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(pose, dict):
                continue
            t = _float_or_none(pose.get("t"))
            transform = pose.get("transform")
            intrinsics = pose.get("intrinsics")
            if t is None or not isinstance(transform, list) or len(transform) < 16:
                continue
            if not isinstance(intrinsics, list) or len(intrinsics) < 9:
                intrinsics = []
            poses.append({"t": t, "transform": transform[:16], "intrinsics": intrinsics[:9]})
    return sorted(poses, key=lambda p: p["t"])


def _nearest_pose(poses: list[dict[str, Any]], t: float) -> dict[str, Any] | None:
    if not poses:
        return None
    lo = 0
    hi = len(poses) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if poses[mid]["t"] < t:
            lo = mid + 1
        else:
            hi = mid
    candidates = [poses[lo]]
    if lo > 0:
        candidates.append(poses[lo - 1])
    return min(candidates, key=lambda p: abs(float(p["t"]) - t))


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    low = math.floor(pos)
    high = math.ceil(pos)
    if low == high:
        return ordered[low]
    frac = pos - low
    return ordered[low] * (1.0 - frac) + ordered[high] * frac


def _intrinsics_params(values: list[Any]) -> tuple[float, float, float, float] | None:
    if len(values) < 9:
        return None
    nums = [_float_or_none(v) for v in values[:9]]
    if any(v is None for v in nums):
        return None
    m = [float(v) for v in nums if v is not None]
    fx = m[0]
    fy = m[4]
    # CaptureMode.swift stores simd columns: [fx,0,0, 0,fy,0, cx,cy,1].
    cx, cy = m[6], m[7]
    if abs(cx) < 1e-6 and abs(cy) < 1e-6 and (abs(m[2]) > 1e-6 or abs(m[5]) > 1e-6):
        cx, cy = m[2], m[5]
    if fx <= 0 or fy <= 0:
        return None
    return fx, fy, cx, cy


def _normalize(vec: tuple[float, float, float]) -> tuple[float, float, float]:
    mag = math.sqrt(vec[0] * vec[0] + vec[1] * vec[1] + vec[2] * vec[2])
    if mag <= 1e-9:
        return (0.0, 0.0, -1.0)
    return (vec[0] / mag, vec[1] / mag, vec[2] / mag)


def _ray_from_pose(
    pose: dict[str, Any],
    center: tuple[float, float],
) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    params = _intrinsics_params(pose.get("intrinsics") or [])
    if params is None:
        return None
    fx, fy, cx, cy = params
    u, v = center
    ray_cam = _normalize(((u - cx) / fx, -(v - cy) / fy, -1.0))
    t = [float(x) for x in pose["transform"][:16]]
    origin = (t[12], t[13], t[14])
    ray_world = _normalize((
        t[0] * ray_cam[0] + t[4] * ray_cam[1] + t[8] * ray_cam[2],
        t[1] * ray_cam[0] + t[5] * ray_cam[1] + t[9] * ray_cam[2],
        t[2] * ray_cam[0] + t[6] * ray_cam[1] + t[10] * ray_cam[2],
    ))
    return origin, ray_world


def _point_from_ray(
    origin: tuple[float, float, float],
    ray: tuple[float, float, float],
    floor_y: float,
    fallback_depth: float = 2.0,
) -> tuple[float, float, float, str]:
    depth = fallback_depth
    mode = "fallback"
    if abs(ray[1]) > 1e-6:
        candidate = (floor_y - origin[1]) / ray[1]
        if 0.15 <= candidate <= 20.0:
            depth = candidate
            mode = "plane"
    return (
        origin[0] + ray[0] * depth,
        origin[1] + ray[1] * depth,
        origin[2] + ray[2] * depth,
        mode,
    )


def _round_position(value: float | None) -> float | None:
    return None if value is None else round(float(value), 3)


def _cluster_positioned(points: list[dict[str, Any]], radius: float = 1.0) -> list[dict[str, Any]]:
    by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for point in points:
        by_label[point["label"]].append(point)

    objects: list[dict[str, Any]] = []
    for label in sorted(by_label):
        clusters: list[dict[str, Any]] = []
        for point in by_label[label]:
            best = None
            best_dist = float("inf")
            for cluster in clusters:
                dist = math.dist((point["x"], point["y"], point["z"]), (cluster["x"], cluster["y"], cluster["z"]))
                if dist <= radius and dist < best_dist:
                    best = cluster
                    best_dist = dist
            if best is None:
                clusters.append({
                    "label": label,
                    "x": point["x"],
                    "y": point["y"],
                    "z": point["z"],
                    "score_sum": point["confidence"],
                    "count": 1,
                    "frame_evidence": list(point["frame_evidence"]),
                    "depth_modes": [point["depth_mode"]],
                    "name_sources": [point.get("name_source") or "unknown"],
                })
            else:
                count = int(best["count"])
                new_count = count + 1
                best["x"] = (best["x"] * count + point["x"]) / new_count
                best["y"] = (best["y"] * count + point["y"]) / new_count
                best["z"] = (best["z"] * count + point["z"]) / new_count
                best["score_sum"] += point["confidence"]
                best["count"] = new_count
                best["frame_evidence"].extend(point["frame_evidence"])
                best["depth_modes"].append(point["depth_mode"])
                best["name_sources"].append(point.get("name_source") or "unknown")
        for cluster in clusters:
            count = int(cluster["count"])
            modes = set(cluster["depth_modes"])
            source_counts: dict[str, int] = defaultdict(int)
            for source in cluster.get("name_sources") or []:
                source_counts[str(source)] += 1
            name_source = max(source_counts.items(), key=lambda kv: kv[1])[0] if source_counts else "unknown"
            objects.append({
                "label": label,
                "x": _round_position(cluster["x"]),
                "y": _round_position(cluster["y"]),
                "z": _round_position(cluster["z"]),
                "confidence": round(float(cluster["score_sum"]) / max(1, count), 3),
                "count": count,
                "frame_evidence": sorted(set(cluster["frame_evidence"])),
                "depth_mode": "plane" if modes == {"plane"} else "fallback",
                "trust": "trusted",
                "name_source": name_source,
                "trusted_count": count,
                "rejected_count": 0,
            })
    return objects


def fuse_world(
    inventory_json: Any,
    labels_json: Any,
    frames_manifest_json: Any,
    poses: list[dict[str, Any]],
    frames_manifest_path: str | None = None,
) -> dict[str, Any]:
    labels = _labels_from_file(labels_json)
    inventory_objects = _inventory_objects(inventory_json, labels)
    generated_at = datetime.now(timezone.utc).isoformat()

    if not poses:
        objects = []
        for item in sorted(inventory_objects, key=lambda o: (-int(o["count"]), o["label"])):
            objects.append({
                "label": item["label"],
                "x": None,
                "y": None,
                "z": None,
                "confidence": round(_clamp01(item.get("confidence")), 3),
                "count": int(item.get("count") or 1),
                "frame_evidence": item.get("frame_evidence") or [],
                "depth_mode": "none",
                "trust": _norm_trust(item.get("trust")),
                "name_source": _name_source(item.get("name_source")),
                "trusted_count": int(item.get("trusted_count") or 0),
                "rejected_count": int(item.get("rejected_count") or 0),
            })
        return {
            "schema": "walk_world.v1",
            "generated_at": generated_at,
            "pose_mode": "none",
            "objects": objects,
        }

    manifest = frames_manifest_json if isinstance(frames_manifest_json, list) else []
    manifest_times = _manifest_lookup(manifest, frames_manifest_path)
    heights = [float(p["transform"][13]) for p in poses if len(p.get("transform") or []) >= 14]
    floor_y = _percentile(heights, 0.05) - 1.4 if heights else -1.4

    points: list[dict[str, Any]] = []
    unpositioned_by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in labels:
        if record.get("trust") != "trusted":
            unpositioned_by_label[record["label"]].append(record)
            continue
        t = _record_time(record, manifest_times)
        center = _record_box_center(record)
        pose = _nearest_pose(poses, t) if t is not None else None
        ray = _ray_from_pose(pose, center) if pose is not None and center is not None else None
        if ray is None:
            unpositioned_by_label[record["label"]].append(record)
            continue
        origin, direction = ray
        x, y, z, depth_mode = _point_from_ray(origin, direction, floor_y)
        points.append({
            "label": record["label"],
            "x": x,
            "y": y,
            "z": z,
            "confidence": _clamp01(record.get("score")),
            "frame_evidence": [record["crop_path"]] if record.get("crop_path") else [],
            "depth_mode": depth_mode,
            "name_source": record.get("name_source") or "unknown",
        })

    objects = _cluster_positioned(points)
    positioned_labels = {obj["label"] for obj in objects}
    inventory_by_label = {obj["label"]: obj for obj in inventory_objects}
    for label, item in inventory_by_label.items():
        if label in positioned_labels:
            continue
        rows = unpositioned_by_label.get(label, [])
        evidence = item.get("frame_evidence") or [str(r.get("crop_path") or "") for r in rows if r.get("crop_path")]
        objects.append({
            "label": label,
            "x": None,
            "y": None,
            "z": None,
            "confidence": round(_clamp01(item.get("confidence")), 3),
            "count": int(item.get("count") or len(rows) or 1),
            "frame_evidence": evidence,
            "depth_mode": "none",
            "trust": _norm_trust(item.get("trust")),
            "name_source": _name_source(item.get("name_source")),
            "trusted_count": int(item.get("trusted_count") or 0),
            "rejected_count": int(item.get("rejected_count") or 0),
        })

    objects.sort(key=lambda o: (o["label"], 999999 if o["x"] is None else 0, -(o.get("count") or 0)))
    return {
        "schema": "walk_world.v1",
        "generated_at": generated_at,
        "pose_mode": "poses",
        "floor_y": round(floor_y, 3),
        "pose_count": len(poses),
        "objects": objects,
    }


def _write_world(world: dict[str, Any], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(world, f, indent=2, sort_keys=True)
        f.write("\n")


def self_test() -> int:
    manifest = [
        {"file": "frame_000000_0.0s.jpg", "t": 0.0},
        {"file": "frame_000030_1.0s.jpg", "t": 1.0},
    ]
    intrinsics = [500.0, 0.0, 0.0, 0.0, 500.0, 0.0, 320.0, 240.0, 1.0]

    def pose(t: float, x: float) -> dict[str, Any]:
        return {
            "t": t,
            "intrinsics": intrinsics,
            "transform": [
                1.0, 0.0, 0.0, 0.0,
                0.0, 1.0, 0.0, 0.0,
                0.0, 0.0, 1.0, 0.0,
                x, 1.5, 0.0, 1.0,
            ],
        }

    labels = [
        {"word": "mug", "score": 0.8, "crop_path": "/tmp/frame_000000_0.0s_obj0.jpg", "frame": "frame_000000_0.0s.jpg", "box": [300, 410, 340, 450]},
        {"word": "mug", "score": 0.7, "crop_path": "/tmp/frame_000030_1.0s_obj0.jpg", "frame": "frame_000030_1.0s.jpg", "box": [302, 412, 342, 452], "trust": "trusted", "name_source": "clip_agreed"},
        {"word": "laptop", "score": 0.9, "crop_path": "/tmp/frame_000030_1.0s_obj1.jpg", "frame": "frame_000030_1.0s.jpg", "box": [420, 410, 470, 450]},
        {"word": "bedpan", "score": 0.9, "crop_path": "/tmp/frame_000030_1.0s_obj2.jpg", "frame": "frame_000030_1.0s.jpg", "box": [420, 410, 470, 450], "trust": "rejected", "name_source": "clip_only"},
    ]
    inventory = {
        "mug": {"count": 2, "trusted_count": 2, "score_mean": 0.75, "examples": ["/tmp/frame_000000_0.0s_obj0.jpg"], "trust": "trusted"},
        "laptop": {"count": 1, "trusted_count": 1, "score_mean": 0.9, "examples": ["/tmp/frame_000030_1.0s_obj1.jpg"], "trust": "trusted"},
        "bedpan": {"count": 1, "rejected_count": 1, "score_mean": 0.9, "examples": ["/tmp/frame_000030_1.0s_obj2.jpg"], "trust": "rejected", "name_source": "clip_only"},
    }
    world = fuse_world(inventory, labels, manifest, [pose(0.0, 0.0), pose(1.0, 0.2)])
    mugs = [obj for obj in world["objects"] if obj["label"] == "mug"]
    assert len(mugs) == 1, mugs
    assert mugs[0]["count"] == 2, mugs
    assert mugs[0]["depth_mode"] == "plane", mugs
    assert mugs[0]["x"] is not None and mugs[0]["z"] is not None, mugs
    bedpans = [obj for obj in world["objects"] if obj["label"] == "bedpan"]
    assert len(bedpans) == 1 and bedpans[0]["trust"] == "rejected", bedpans
    assert bedpans[0]["x"] is None and bedpans[0]["depth_mode"] == "none", bedpans

    no_pose_world = fuse_world(inventory, labels, manifest, [])
    assert no_pose_world["pose_mode"] == "none"
    assert all(obj["x"] is None and obj["depth_mode"] == "none" for obj in no_pose_world["objects"])
    assert {obj["label"] for obj in no_pose_world["objects"]} == {"mug", "laptop", "bedpan"}
    print("SELF-TEST PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", default="/tmp/walk_inventory.json")
    parser.add_argument("--labels", default="/tmp/walk_labels.json")
    parser.add_argument("--frames-manifest", default="/tmp/walk_frames/manifest.json")
    parser.add_argument("--poses", default="NONE")
    parser.add_argument("--out", default="/tmp/walk_world.json")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    inventory = _load_json(args.inventory, {})
    labels = _load_json(args.labels, [])
    frames_manifest = _load_json(args.frames_manifest, [])
    poses = _load_poses(args.poses)
    world = fuse_world(inventory, labels, frames_manifest, poses, args.frames_manifest)
    _write_world(world, args.out)
    positioned = sum(1 for obj in world["objects"] if obj.get("x") is not None)
    print(f"wrote {len(world['objects'])} objects ({positioned} positioned) to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
