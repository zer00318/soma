#!/usr/bin/env python3
"""Quarantine detections that are clearly inside physical screens."""
from __future__ import annotations

import re
from typing import Any

SCREEN_TYPES = {"laptop", "monitor", "tablet", "phone", "tv", "screen", "display"}
_GENERIC_TYPES = {"object", "thing", "item"}


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.lower())


def _singularize(word: str) -> str:
    if word.endswith("ies") and len(word) > 3:
        return word[:-3] + "y"
    if word.endswith(("ches", "shes", "sses", "xes", "zes")) and len(word) > 2:
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 1:
        return word[:-1]
    return word


def _normalize_type(inst: dict[str, Any]) -> str:
    type_value = _clean_text(inst.get("type"))
    det_value = _clean_text(inst.get("det_label"))
    label_value = _clean_text(inst.get("label"))
    raw = type_value or det_value or label_value or "object"
    if type_value.lower() in _GENERIC_TYPES and (det_value or label_value):
        raw = det_value or label_value
    raw = re.sub(r"^(a|an|the)\s+", "", raw.lower())
    pieces = _tokens(raw)
    head = pieces[0] if pieces else "object"
    return _singularize(head) or "object"


def _float_or_none(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _valid_box(box: object) -> tuple[float, float, float, float] | None:
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return None
    coords = [_float_or_none(value) for value in box]
    if any(value is None for value in coords):
        return None
    x0, y0, x1, y1 = coords
    if x1 <= x0 or y1 <= y0:
        return None
    return float(x0), float(y0), float(x1), float(y1)


def _intersection_area(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    overlap_x = min(left[2], right[2]) - max(left[0], right[0])
    overlap_y = min(left[3], right[3]) - max(left[1], right[1])
    if overlap_x <= 0.0 or overlap_y <= 0.0:
        return 0.0
    return overlap_x * overlap_y


def _containment_ratio(
    inst_box: tuple[float, float, float, float] | None,
    screen_box: tuple[float, float, float, float] | None,
) -> float:
    if inst_box is None or screen_box is None:
        return 0.0
    inst_area = (inst_box[2] - inst_box[0]) * (inst_box[3] - inst_box[1])
    if inst_area <= 0.0:
        return 0.0
    return _intersection_area(inst_box, screen_box) / inst_area


def mark_on_screen(instances: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a new list with screen-contained detections marked as on-screen."""
    screens: list[tuple[str, tuple[float, float, float, float] | None]] = []
    for inst in instances:
        type_name = _normalize_type(inst)
        if type_name in SCREEN_TYPES:
            screens.append((type_name, _valid_box(inst.get("box"))))

    annotated: list[dict[str, Any]] = []
    for inst in instances:
        type_name = _normalize_type(inst)
        annotated_inst = dict(inst)
        annotated_inst["on_screen"] = False
        annotated_inst.pop("screen_type", None)

        if type_name in SCREEN_TYPES:
            annotated.append(annotated_inst)
            continue

        inst_box = _valid_box(inst.get("box"))
        best_ratio = 0.0
        best_screen_type = ""
        for screen_type, screen_box in screens:
            ratio = _containment_ratio(inst_box, screen_box)
            if ratio > best_ratio:
                best_ratio = ratio
                best_screen_type = screen_type

        if best_ratio >= 0.70:
            annotated_inst["on_screen"] = True
            annotated_inst["screen_type"] = best_screen_type

        annotated.append(annotated_inst)

    return annotated


def physical_only(instances: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter out detections that were marked as on-screen content."""
    return [inst for inst in instances if not inst.get("on_screen")]
