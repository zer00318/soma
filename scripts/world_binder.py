#!/usr/bin/env python3
"""Deterministic binding of detections to distinct world-coordinate nodes."""
from __future__ import annotations

from collections import defaultdict
import math
import re
from typing import Any

_EMPTY_VALUES = {"", "none", "unknown", "null", "n/a"}
_GENERIC_TYPES = {"object", "thing", "item"}
_TEXT_FIELDS = ("text", "name", "brand")
_CORE_FIELDS = {"box", "img_wh", "type", "det_label", "label"} | set(_TEXT_FIELDS)
_TYPE_SYNONYMS = {
    "bottles": "bottle",
    "boxes": "box",
    "cups": "cup",
    "jars": "jar",
    "mugs": "cup",
}


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in _EMPTY_VALUES:
        return ""
    return text


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.lower())


def _singularize(word: str) -> str:
    if word in _TYPE_SYNONYMS:
        return _TYPE_SYNONYMS[word]
    if word.endswith("ies") and len(word) > 3:
        return word[:-3] + "y"
    if word.endswith(("ches", "shes", "sses", "xes", "zes")) and len(word) > 2:
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 1:
        return word[:-1]
    return word


def _normalize_type_value(value: object) -> str:
    raw = _clean_text(value).lower()
    raw = re.sub(r"^(a|an|the)\s+", "", raw)
    pieces = _tokens(raw)
    head = pieces[0] if pieces else "object"
    return _singularize(head) or "object"


def _normalize_type(inst: dict[str, Any]) -> str:
    raw_type = _clean_text(inst.get("type"))
    det_label = _clean_text(inst.get("det_label"))
    label = _clean_text(inst.get("label"))
    candidate = raw_type or det_label or label or "object"
    if raw_type.lower() in _GENERIC_TYPES and (det_label or label):
        candidate = det_label or label
    return _normalize_type_value(candidate)


def _normalize_query(value: object) -> str:
    tokens = [_singularize(token) for token in _tokens(_clean_text(value))]
    return " ".join(tokens)


def _float_or_none(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number


def _valid_box(box: object) -> tuple[float, float, float, float] | None:
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return None
    coords = [_float_or_none(value) for value in box]
    if any(value is None for value in coords):
        return None
    x0, y0, x1, y1 = coords
    return float(x0), float(y0), float(x1), float(y1)


def _valid_img_wh(img_wh: object) -> tuple[float, float] | None:
    if not isinstance(img_wh, (list, tuple)) or len(img_wh) != 2:
        return None
    width = _float_or_none(img_wh[0])
    height = _float_or_none(img_wh[1])
    if width is None or height is None or width <= 0.0 or height <= 0.0:
        return None
    return width, height


def _coerce_world_point(value: object) -> list[float] | None:
    if value is None or not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    coords = [_float_or_none(coord) for coord in value]
    if any(coord is None for coord in coords):
        return None
    return [float(coords[0]), float(coords[1]), float(coords[2])]


def _grid_parts(depth_grid: object) -> tuple[int, int, list[object]] | None:
    if not isinstance(depth_grid, dict):
        return None
    width = _int_or_none(depth_grid.get("w"))
    height = _int_or_none(depth_grid.get("h"))
    pts = depth_grid.get("pts")
    if width is None or height is None or width <= 0 or height <= 0:
        return None
    if not isinstance(pts, list) or len(pts) != width * height:
        return None
    return width, height, pts


def _primary_text(inst: dict[str, Any]) -> str:
    for field in _TEXT_FIELDS:
        text = _clean_text(inst.get(field))
        if text:
            return text
    return ""


def _iter_text_reads(inst: dict[str, Any]) -> list[str]:
    reads: list[str] = []
    seen: set[str] = set()
    for field in (*_TEXT_FIELDS, "label"):
        text = _clean_text(inst.get(field))
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        reads.append(text)
    return reads


def _distance3(left: list[float], right: list[float]) -> float:
    return math.sqrt(
        (left[0] - right[0]) ** 2
        + (left[1] - right[1]) ** 2
        + (left[2] - right[2]) ** 2
    )


def sample_world(
    box: object,
    img_wh: object,
    depth_grid: object,
) -> list[float] | None:
    """World (x,y,z) for a detection box center via the phone raycast grid."""
    coords = _valid_box(box)
    dims = _valid_img_wh(img_wh)
    grid = _grid_parts(depth_grid)
    if coords is None or dims is None or grid is None:
        return None

    x0, y0, x1, y1 = coords
    width, height = dims
    grid_w, grid_h, pts = grid
    center_x = (x0 + x1) / 2.0
    center_y = (y0 + y1) / 2.0
    normalized_x = min(max(center_x / width, 0.0), 1.0 - 1e-9)
    normalized_y = min(max(center_y / height, 0.0), 1.0 - 1e-9)
    target_col = min(grid_w - 1, max(0, int(normalized_x * grid_w)))
    target_row = min(grid_h - 1, max(0, int(normalized_y * grid_h)))

    for radius in range(3):
        best: tuple[float, int, int, list[float]] | None = None
        row_start = max(0, target_row - radius)
        row_stop = min(grid_h, target_row + radius + 1)
        col_start = max(0, target_col - radius)
        col_stop = min(grid_w, target_col + radius + 1)
        for row in range(row_start, row_stop):
            for col in range(col_start, col_stop):
                if max(abs(row - target_row), abs(col - target_col)) != radius:
                    continue
                point = _coerce_world_point(pts[row * grid_w + col])
                if point is None:
                    continue
                candidate = (
                    float((row - target_row) ** 2 + (col - target_col) ** 2),
                    row,
                    col,
                    point,
                )
                if best is None or candidate[:3] < best[:3]:
                    best = candidate
        if best is not None:
            return best[3]
    return None


def _new_node(type_name: str, located: bool) -> dict[str, Any]:
    return {
        "type": type_name,
        "located": located,
        "world_xyz": None,
        "texts": [],
        "frames": [],
        "count_frames": 0,
        "label": type_name,
        "attrs": {},
        "_frame_set": set(),
        "_text_keys": set(),
        "_text_votes": defaultdict(int),
        "_text_display": {},
        "_text_order": {},
        "_world_sum": [0.0, 0.0, 0.0],
        "_world_count": 0,
    }


def _merge_attrs(node: dict[str, Any], inst: dict[str, Any]) -> None:
    attrs = node["attrs"]
    for key, value in inst.items():
        if key in _CORE_FIELDS or key.startswith("_"):
            continue
        if isinstance(value, str):
            cleaned = _clean_text(value)
            if not cleaned:
                continue
            attrs.setdefault(key, cleaned)
            continue
        if isinstance(value, (int, float, bool)) and key not in attrs:
            attrs[key] = value


def _update_label(node: dict[str, Any]) -> None:
    text_votes = node["_text_votes"]
    if not text_votes:
        node["label"] = node["type"]
        return
    best_key = min(
        text_votes,
        key=lambda key: (-text_votes[key], node["_text_order"][key], key),
    )
    node["label"] = node["_text_display"][best_key]


def _add_member(
    node: dict[str, Any],
    inst: dict[str, Any],
    frame_idx: int,
    world_xyz: list[float] | None,
) -> None:
    if frame_idx not in node["_frame_set"]:
        node["_frame_set"].add(frame_idx)
        node["frames"].append(frame_idx)
        node["count_frames"] = len(node["frames"])

    for text in _iter_text_reads(inst):
        text_key = text.lower()
        if text_key not in node["_text_keys"]:
            node["_text_keys"].add(text_key)
            node["_text_order"][text_key] = len(node["_text_order"])
            node["_text_display"][text_key] = text
            node["texts"].append(text)
        node["_text_votes"][text_key] += 1

    if world_xyz is not None:
        node["_world_count"] += 1
        for index, value in enumerate(world_xyz):
            node["_world_sum"][index] += value
        world_count = float(node["_world_count"])
        node["world_xyz"] = [
            total / world_count for total in node["_world_sum"]
        ]

    _merge_attrs(node, inst)
    _update_label(node)


def _best_located_node(
    nodes: list[dict[str, Any]],
    type_name: str,
    world_xyz: list[float],
    eps_m: float,
) -> dict[str, Any] | None:
    best_match: dict[str, Any] | None = None
    best_distance = math.inf
    for node in nodes:
        if not node["located"] or node["type"] != type_name:
            continue
        centroid = node["world_xyz"]
        if centroid is None:
            continue
        distance = _distance3(world_xyz, centroid)
        if distance > eps_m or distance >= best_distance:
            continue
        best_match = node
        best_distance = distance
    return best_match


def _public_node(node: dict[str, Any]) -> dict[str, Any]:
    world_xyz = node["world_xyz"]
    return {
        "world_xyz": None if world_xyz is None else list(world_xyz),
        "type": node["type"],
        "texts": list(node["texts"]),
        "label": node["label"],
        "frames": list(node["frames"]),
        "count_frames": node["count_frames"],
        "located": node["located"],
        "attrs": dict(node["attrs"]),
    }


def _summary(nodes: list[dict[str, Any]], counts_by_type: dict[str, dict[str, int]]) -> str:
    located = sum(1 for node in nodes if node["located"])
    unlocated = len(nodes) - located
    if not counts_by_type:
        return "0 nodes (0 located, 0 unlocated)"
    type_summary = ", ".join(
        f"{type_name}:{counts['distinct']}/{counts['located']}"
        for type_name, counts in sorted(counts_by_type.items())
    )
    return (
        f"{len(nodes)} nodes ({located} located, {unlocated} unlocated); "
        f"per-type distinct/located: {type_summary}"
    )


def bind_world_instances(
    frame_instances: object,
    frame_depth_grids: object,
    eps_m: float = 0.12,
) -> dict[str, Any]:
    """Cluster detections across frames into distinct world-located nodes."""
    frames = frame_instances if isinstance(frame_instances, list) else []
    grids = frame_depth_grids if isinstance(frame_depth_grids, list) else []
    nodes: list[dict[str, Any]] = []
    fallback_nodes: dict[tuple[str, str], dict[str, Any]] = {}

    for frame_idx, instances in enumerate(frames):
        grid = grids[frame_idx] if frame_idx < len(grids) else None
        if not isinstance(instances, list):
            continue
        for inst in instances:
            if not isinstance(inst, dict):
                continue
            type_name = _normalize_type(inst)
            world_xyz = sample_world(inst.get("box"), inst.get("img_wh"), grid)
            if world_xyz is not None:
                node = _best_located_node(nodes, type_name, world_xyz, eps_m)
                if node is None:
                    node = _new_node(type_name, located=True)
                    nodes.append(node)
                _add_member(node, inst, frame_idx, world_xyz)
                continue

            fallback_key = (type_name, _primary_text(inst).lower())
            node = fallback_nodes.get(fallback_key)
            if node is None:
                node = _new_node(type_name, located=False)
                nodes.append(node)
                fallback_nodes[fallback_key] = node
            _add_member(node, inst, frame_idx, None)

    public_nodes = [_public_node(node) for node in nodes]
    counts_by_type: dict[str, dict[str, int]] = defaultdict(
        lambda: {"distinct": 0, "located": 0}
    )
    for node in public_nodes:
        counts = counts_by_type[node["type"]]
        counts["distinct"] += 1
        if node["located"]:
            counts["located"] += 1

    ordered_counts = {
        type_name: counts_by_type[type_name] for type_name in sorted(counts_by_type)
    }
    return {
        "nodes": public_nodes,
        "counts_by_type": ordered_counts,
        "summary": _summary(public_nodes, ordered_counts),
    }


def count_of(binder_result: object, query_noun: object) -> int:
    """Count distinct nodes whose type or texts match the query noun."""
    needle = _normalize_query(query_noun)
    if not needle or not isinstance(binder_result, dict):
        return 0
    nodes = binder_result.get("nodes")
    if not isinstance(nodes, list):
        return 0

    matches = 0
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_type = _normalize_type_value(node.get("type"))
        if needle in node_type:
            matches += 1
            continue
        texts = node.get("texts")
        if not isinstance(texts, list):
            continue
        if any(needle in _clean_text(text).lower() for text in texts):
            matches += 1
    return matches
