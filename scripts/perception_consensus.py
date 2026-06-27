#!/usr/bin/env python3
"""Cross-frame consensus helpers for post-consolidation instance honesty."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy


def _coerce_nonnegative_int(value: object) -> int:
    try:
        count = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    return max(count, 0)


def _instance_type(instance: dict) -> str:
    raw_type = str(instance.get("type") or "").strip()
    return raw_type or "object"


def _tier(count_frames: int) -> str:
    return "confirmed" if count_frames >= 2 else "provisional"


def _confidence(count_frames: int) -> float:
    return round(min(1.0, count_frames / 3.0), 2)


def _confirmed_counts(instances: list[dict], counts_by_type: dict) -> dict[str, int]:
    all_types = {
        str(inst_type).strip()
        for inst_type in counts_by_type
        if str(inst_type).strip()
    }
    all_types.update(_instance_type(instance) for instance in instances)

    counts: Counter[str] = Counter()
    for instance in instances:
        if instance.get("tier") == "confirmed":
            counts[_instance_type(instance)] += 1

    return {inst_type: counts.get(inst_type, 0) for inst_type in sorted(all_types)}


def _summary_confirmed(confirmed_counts: dict[str, int], total_frames: int) -> str:
    frame_count = _coerce_nonnegative_int(total_frames)
    visible_counts = {
        inst_type: count for inst_type, count in confirmed_counts.items() if count > 0
    }
    if not visible_counts:
        return f"Nothing confirmed across {frame_count} frame(s)."

    parts = [f"{inst_type} {count}" for inst_type, count in visible_counts.items()]
    return f"Confirmed across {frame_count} frame(s): " + ", ".join(parts) + "."


def tier_instances(consolidated: dict, total_frames: int) -> dict:
    """Tag instances with a cross-frame consensus tier without mutating input."""
    result = deepcopy(consolidated)

    instances = result.get("instances")
    if not isinstance(instances, list):
        instances = []
        result["instances"] = instances

    for instance in instances:
        if not isinstance(instance, dict):
            continue
        count_frames = _coerce_nonnegative_int(instance.get("count_frames"))
        instance["tier"] = _tier(count_frames)
        instance["confidence"] = _confidence(count_frames)

    counts_by_type = result.get("counts_by_type")
    if not isinstance(counts_by_type, dict):
        counts_by_type = {}
        result["counts_by_type"] = counts_by_type

    dict_instances = [instance for instance in instances if isinstance(instance, dict)]
    confirmed_counts = _confirmed_counts(dict_instances, counts_by_type)
    result["confirmed_counts_by_type"] = confirmed_counts
    result["summary_confirmed"] = _summary_confirmed(confirmed_counts, total_frames)
    return result


def confident_instances(consolidated: dict) -> list[dict]:
    """Return only instances that cleared the >=2-frame confirmation threshold."""
    instances = consolidated.get("instances")
    if not isinstance(instances, list):
        return []
    return [
        deepcopy(instance)
        for instance in instances
        if isinstance(instance, dict) and instance.get("tier") == "confirmed"
    ]

