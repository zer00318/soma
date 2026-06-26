#!/usr/bin/env python3
"""Deterministic cross-frame consolidation for per-frame instance detections."""
from __future__ import annotations

from collections import Counter, defaultdict
import re

_EMPTY_VALUES = {"", "none", "unknown", "null", "n/a"}
_TYPE_SYNONYMS = {
    "cups": "cup",
    "mugs": "cup",
}
_MERGED_FIELDS = ("name", "brand", "text", "colour", "material", "state", "orient")


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
    if word.endswith(("ches", "shes", "xes", "zes", "sses")) and len(word) > 2:
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 1:
        return word[:-1]
    return word


def _normalize_type(inst: dict) -> str:
    type_value = _clean_text(inst.get("type"))
    det_value = _clean_text(inst.get("det_label"))
    label_value = _clean_text(inst.get("label"))
    raw = type_value or det_value or label_value or "object"
    if type_value.lower() in {"object", "thing", "item"} and (det_value or label_value):
        raw = det_value or label_value
    raw = re.sub(r"^(a|an|the)\s+", "", raw.lower())
    toks = _tokens(raw)
    head = toks[0] if toks else "object"
    return _TYPE_SYNONYMS.get(head, _singularize(head)) or "object"


def _identity_tokens(inst: dict) -> set[str]:
    type_token = _normalize_type(inst)
    raw = (
        _clean_text(inst.get("text"))
        or _clean_text(inst.get("brand"))
        or _clean_text(inst.get("name"))
    )
    if not raw:
        return set()
    return {
        token
        for token in _tokens(raw)
        if token not in {type_token, "brand", "label", "object"}
    }


def _colour_material_signature(inst: dict) -> tuple[str, str]:
    return (
        _clean_text(inst.get("colour")).lower(),
        _clean_text(inst.get("material")).lower(),
    )


def _signature_nonempty(signature: tuple[str, str]) -> bool:
    return bool(signature[0] or signature[1])


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _yaw_delta(left: float, right: float) -> float:
    return abs((left - right + 180.0) % 360.0 - 180.0)


def _valid_box(box: object) -> list[float] | None:
    if not isinstance(box, list) or len(box) != 4:
        return None
    coords: list[float] = []
    for value in box:
        if not isinstance(value, (int, float)):
            return None
        coords.append(float(value))
    return coords


def _detections_match(
    existing: dict,
    incoming: dict,
    existing_frame: int,
    incoming_frame: int,
    existing_yaw: float | None,
    incoming_yaw: float | None,
) -> bool:
    if existing_frame == incoming_frame:
        return False
    if _normalize_type(existing) != _normalize_type(incoming):
        return False

    existing_tokens = _identity_tokens(existing)
    incoming_tokens = _identity_tokens(incoming)
    if existing_tokens and incoming_tokens:
        if _jaccard(existing_tokens, incoming_tokens) < 0.6:
            return False
    elif not existing_tokens and not incoming_tokens:
        if _colour_material_signature(existing) != _colour_material_signature(incoming):
            return False
    else:
        return False

    if (
        existing_yaw is not None
        and incoming_yaw is not None
        and _yaw_delta(existing_yaw, incoming_yaw) > 25.0
    ):
        return False
    return True


def _cluster_matches(cluster: dict, inst: dict, frame_idx: int, yaw: float | None) -> bool:
    if frame_idx in cluster["frame_set"]:
        return False
    for member in cluster["members"]:
        if _detections_match(
            member["inst"],
            inst,
            member["frame_idx"],
            frame_idx,
            member["yaw"],
            yaw,
        ):
            return True
    return False


def _pick_value(instances: list[dict], field: str) -> str:
    by_norm: dict[str, dict[str, object]] = {}
    for index, inst in enumerate(instances):
        raw = _clean_text(inst.get(field))
        if not raw:
            continue
        norm = raw.lower()
        entry = by_norm.setdefault(norm, {"count": 0, "raw": raw, "index": index})
        entry["count"] = int(entry["count"]) + 1
        if len(raw) > len(str(entry["raw"])):
            entry["raw"] = raw
    if not by_norm:
        return ""
    best = max(
        by_norm.values(),
        key=lambda entry: (
            int(entry["count"]),
            len(str(entry["raw"])),
            -int(entry["index"]),
        ),
    )
    return str(best["raw"])


def _merge_box(instances: list[dict]) -> list[float] | None:
    boxes = [_valid_box(inst.get("box")) for inst in instances]
    valid = [box for box in boxes if box is not None]
    if not valid:
        return None
    return [sum(coords) / len(valid) for coords in zip(*valid)]


def _build_label(inst_type: str, merged: dict) -> str:
    detail = merged.get("text") or merged.get("brand") or merged.get("name") or ""
    detail_text = _clean_text(detail)
    return f"{inst_type} {detail_text}".strip() if detail_text else inst_type


def _type_frame_counts(frame_instances: list[list[dict]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for frame in frame_instances:
        per_frame = Counter(_normalize_type(inst) for inst in frame if isinstance(inst, dict))
        for inst_type, count in per_frame.items():
            counts[inst_type] = max(counts[inst_type], count)
    return counts


def _counts_by_type(frame_instances: list[list[dict]], clusters: list[dict]) -> dict[str, dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for cluster in clusters:
        grouped[cluster["type"]].append(cluster)

    max_per_frame = _type_frame_counts(frame_instances)
    result: dict[str, dict] = {}
    for inst_type, typed_clusters in grouped.items():
        texted = [cluster for cluster in typed_clusters if cluster["has_text"]]
        if texted:
            low = len(texted)
            high = len(typed_clusters)
            result[inst_type] = {
                "distinct": high,
                "hedge": str(high) if low == high else f"{low}-{high}",
            }
            continue

        signatures = [cluster["signature"] for cluster in typed_clusters]
        unique_nonempty = (
            all(_signature_nonempty(signature) for signature in signatures)
            and len(set(signatures)) == len(signatures)
        )
        if unique_nonempty:
            distinct = len(typed_clusters)
            result[inst_type] = {"distinct": distinct, "hedge": str(distinct)}
            continue

        max_count = max_per_frame.get(inst_type, len(typed_clusters))
        result[inst_type] = {"distinct": max_count, "hedge": f"1-{max_count}"}

    return dict(sorted(result.items()))


def _summary(instances: list[dict], counts_by_type: dict[str, dict]) -> str:
    if not instances:
        return "No instances were consolidated from the provided frames."
    parts = [f'{inst_type} {info["hedge"]}' for inst_type, info in counts_by_type.items()]
    return (
        f"Consolidated {len(instances)} canonical instances across "
        f"{len(counts_by_type)} type(s): " + ", ".join(parts) + "."
    )


def consolidate(
    frame_instances: list[list[dict]],
    frame_yaws: list[float | None] | None = None,
) -> dict:
    """Consolidate per-frame instance detections into canonical cross-frame instances."""
    yaws = frame_yaws or []
    clusters: list[dict] = []

    for frame_idx, detections in enumerate(frame_instances):
        yaw = yaws[frame_idx] if frame_idx < len(yaws) else None
        for inst in detections:
            if not isinstance(inst, dict):
                continue
            matched_cluster = None
            for cluster in clusters:
                if _cluster_matches(cluster, inst, frame_idx, yaw):
                    matched_cluster = cluster
                    break
            if matched_cluster is None:
                matched_cluster = {
                    "type": _normalize_type(inst),
                    "members": [],
                    "frame_set": set(),
                }
                clusters.append(matched_cluster)
            matched_cluster["members"].append(
                {"inst": dict(inst), "frame_idx": frame_idx, "yaw": yaw}
            )
            matched_cluster["frame_set"].add(frame_idx)

    canonical_instances: list[dict] = []
    cluster_summaries: list[dict] = []
    for cluster in clusters:
        members = cluster["members"]
        member_insts = [member["inst"] for member in members]
        merged = {field: _pick_value(member_insts, field) for field in _MERGED_FIELDS}
        merged["type"] = cluster["type"]
        merged["box"] = _merge_box(member_insts)
        merged["frames"] = sorted(cluster["frame_set"])
        merged["count_frames"] = len(merged["frames"])
        merged["label"] = _build_label(cluster["type"], merged)
        canonical_instances.append(merged)
        cluster_summaries.append(
            {
                "type": cluster["type"],
                "has_text": any(_identity_tokens(inst) for inst in member_insts),
                "signature": _colour_material_signature(member_insts[0]),
            }
        )

    counts_by_type = _counts_by_type(frame_instances, cluster_summaries)
    return {
        "instances": canonical_instances,
        "counts_by_type": counts_by_type,
        "summary": _summary(canonical_instances, counts_by_type),
    }
