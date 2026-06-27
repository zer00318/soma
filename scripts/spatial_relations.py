"""Deterministic spatial relations between world-anchored nodes.

ARKit world convention used here:
- `+x` = right
- `+y` = up
- `+z` = toward the camera / back toward the observer

That means a larger `z` value is treated as "in front of" a smaller `z` value
because the point is closer to the camera.
"""
from __future__ import annotations

import math
from typing import Iterable

# ARKit world axes: +x = right, +y = up, +z = toward the camera / observer.
# Higher z is therefore described as "in front of" lower z.
_NEXT_TO_X_TOL_M = 0.15
_NEXT_TO_Y_TOL_M = 0.10
_NEXT_TO_Z_TOL_M = 0.08
_ON_TOP_X_TOL_M = 0.05
_ON_TOP_Z_TOL_M = 0.05
_ON_TOP_MIN_DY_M = 0.05
_ON_TOP_MAX_DY_M = 0.18
_EPS = 1e-9

_INVERSE_REL = {
    "left of": "right of",
    "right of": "left of",
    "above": "below",
    "below": "above",
    "in front of": "behind",
    "behind": "in front of",
    "next to": "next to",
}

_DESCRIBE_PRIORITY = {
    "on top of": 0,
    "left of": 1,
    "above": 2,
    "in front of": 3,
    "next to": 4,
    "right of": 5,
    "below": 6,
    "behind": 7,
}

_DESCRIBE_TEXT = {
    "left of": "to the left of",
    "right of": "to the right of",
    "above": "above",
    "below": "below",
    "in front of": "in front of",
    "behind": "behind",
    "next to": "next to",
    "on top of": "on top of",
}


def _node_name(node: dict, index: int) -> str:
    label = node.get("label") or node.get("type")
    text = str(label).strip() if label is not None else ""
    return text or f"node {index}"


def _world_xyz(node: dict) -> tuple[float, float, float] | None:
    xyz = node.get("world_xyz")
    if xyz is None:
        return None
    if not isinstance(xyz, (list, tuple)) or len(xyz) != 3:
        return None
    try:
        return (float(xyz[0]), float(xyz[1]), float(xyz[2]))
    except (TypeError, ValueError):
        return None


def _valid_nodes(nodes: Iterable[dict]) -> list[dict]:
    valid = []
    for index, node in enumerate(nodes):
        xyz = _world_xyz(node)
        if xyz is None:
            continue
        valid.append({"label": _node_name(node, index), "world_xyz": xyz})
    return valid


def _dominant_axis(dx: float, dy: float, dz: float) -> str | None:
    scores = [("x", abs(dx)), ("y", abs(dy)), ("z", abs(dz))]
    axis, score = max(scores, key=lambda item: item[1])
    return axis if score > _EPS else None


def _axis_relation_from_a_to_b(dx: float, dy: float, dz: float, axis: str | None) -> str | None:
    if axis == "x":
        return "left of" if dx > 0 else "right of"
    if axis == "y":
        return "below" if dy > 0 else "above"
    if axis == "z":
        return "behind" if dz > 0 else "in front of"
    return None


def _is_b_on_top_of_a(dx: float, dy: float, dz: float) -> bool:
    return (
        _ON_TOP_MIN_DY_M <= dy <= _ON_TOP_MAX_DY_M
        and abs(dx) <= _ON_TOP_X_TOL_M
        and abs(dz) <= _ON_TOP_Z_TOL_M
    )


def _is_next_to(dx: float, dy: float, dz: float, axis: str | None) -> bool:
    return (
        axis == "x"
        and _EPS < abs(dx) <= _NEXT_TO_X_TOL_M
        and abs(dy) <= _NEXT_TO_Y_TOL_M
        and abs(dz) <= _NEXT_TO_Z_TOL_M
    )


def _distance(a_xyz: tuple[float, float, float], b_xyz: tuple[float, float, float]) -> float:
    return round(math.dist(a_xyz, b_xyz), 4)


def _pair_analysis(a: dict, b: dict) -> dict:
    ax, ay, az = a["world_xyz"]
    bx, by, bz = b["world_xyz"]
    dx, dy, dz = bx - ax, by - ay, bz - az
    axis = _dominant_axis(dx, dy, dz)
    primary_ab = _axis_relation_from_a_to_b(dx, dy, dz, axis)
    primary_ba = _INVERSE_REL[primary_ab] if primary_ab else None
    top_from = None
    top_to = None
    if _is_b_on_top_of_a(dx, dy, dz):
        top_from = b["label"]
        top_to = a["label"]
    elif _is_b_on_top_of_a(-dx, -dy, -dz):
        top_from = a["label"]
        top_to = b["label"]
    return {
        "distance": _distance(a["world_xyz"], b["world_xyz"]),
        "primary_ab": primary_ab,
        "primary_ba": primary_ba,
        "next_to": _is_next_to(dx, dy, dz, axis) and top_from is None,
        "top_from": top_from,
        "top_to": top_to,
    }


def _append_symmetric(records: list[dict], a_label: str, b_label: str, rel_ab: str, dist_m: float) -> None:
    records.append({"from": a_label, "to": b_label, "rel": rel_ab, "dist_m": dist_m})
    records.append(
        {"from": b_label, "to": a_label, "rel": _INVERSE_REL[rel_ab], "dist_m": dist_m}
    )


def relations(nodes: list[dict]) -> list[dict]:
    """Derive pairwise spatial relations between located world nodes.

    `nodes` is a list of dicts with `world_xyz=[x, y, z]` in meters plus
    `label` and/or `type`. Nodes with `world_xyz=None` are skipped.

    Assumed ARKit world axes:
    - `+x` = right
    - `+y` = up
    - `+z` = toward the camera / back toward the observer

    For each unordered pair, the helper emits the strongest derived relation from
    the dominant world-axis delta plus at most one contextual relation:
    `next to` or `on top of`. Returned rows are directional and use centroid
    distance in meters as `dist_m`.
    """
    valid = _valid_nodes(nodes)
    derived = []
    for index, a in enumerate(valid):
        for b in valid[index + 1 :]:
            analysis = _pair_analysis(a, b)
            dist_m = analysis["distance"]
            if analysis["primary_ab"]:
                _append_symmetric(derived, a["label"], b["label"], analysis["primary_ab"], dist_m)
            if analysis["next_to"]:
                _append_symmetric(derived, a["label"], b["label"], "next to", dist_m)
            if analysis["top_from"] is not None:
                derived.append(
                    {
                        "from": analysis["top_from"],
                        "to": analysis["top_to"],
                        "rel": "on top of",
                        "dist_m": dist_m,
                    }
                )
    return derived


def _describe_direction(a_label: str, b_label: str, analysis: dict) -> tuple[str, str, list[str]] | None:
    if analysis["top_from"] is not None:
        phrases = ["on top of"]
        if analysis["next_to"]:
            phrases.append("next to")
        return analysis["top_from"], analysis["top_to"], phrases

    if analysis["primary_ab"] is None and not analysis["next_to"]:
        return None

    options = []
    if analysis["primary_ab"] is not None:
        options.append((a_label, b_label, analysis["primary_ab"]))
        options.append((b_label, a_label, analysis["primary_ba"]))

    if not options:
        first, second = sorted((a_label, b_label))
        return first, second, ["next to"]

    subject, target, rel = min(
        options, key=lambda item: (_DESCRIBE_PRIORITY[item[2]], item[0], item[1])
    )
    phrases = [rel]
    if analysis["next_to"]:
        phrases.append("next to")
    return subject, target, phrases


def _join_phrases(phrases: list[str]) -> str:
    rendered = [_DESCRIBE_TEXT[phrase] for phrase in phrases]
    if len(rendered) == 1:
        return rendered[0]
    return " and ".join(rendered)


def describe(nodes: list[dict]) -> list[str]:
    """Return readable spatial summaries, one line per valid node pair.

    Example:
    `Nutella is to the left of and next to Pesto (0.08 m).`
    """
    valid = _valid_nodes(nodes)
    lines = []
    for index, a in enumerate(valid):
        for b in valid[index + 1 :]:
            analysis = _pair_analysis(a, b)
            direction = _describe_direction(a["label"], b["label"], analysis)
            if direction is None:
                continue
            subject, target, phrases = direction
            lines.append(
                f"{subject} is {_join_phrases(phrases)} {target} ({analysis['distance']:.2f} m)."
            )
    return lines
