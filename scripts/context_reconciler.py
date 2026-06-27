#!/usr/bin/env python3
"""Activity-aware reconciliation for conflicting object identity reads."""
from __future__ import annotations

import re
from collections import Counter
from typing import Callable


GENERIC_LABELS = {
    "object",
    "objects",
    "thing",
    "things",
    "item",
    "items",
    "stuff",
    "something",
    "unknown",
    "unknown object",
    "generic",
    "entity",
}


def _normalize(label: str) -> str:
    text = re.sub(r"[^0-9a-z]+", " ", str(label or "").lower())
    return re.sub(r"\s+", " ", text).strip()


def _is_generic(label: str) -> bool:
    if not label:
        return True
    if label in GENERIC_LABELS:
        return True
    tokens = label.split()
    return bool(tokens) and all(token in GENERIC_LABELS for token in tokens)


def _clamp_plausibility(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def reconcile_node(
    reads: list[str],
    activity: str,
    plausibility_fn: Callable[[str, str], float],
) -> dict:
    """Reconcile one object's conflicting identity reads using an activity prior."""
    counts: Counter[str] = Counter()
    for read in reads:
        label = _normalize(read)
        if _is_generic(label):
            continue
        counts[label] += 1

    surviving: list[tuple[str, int, float, float]] = []
    dropped: list[str] = []
    for label, count in counts.items():
        plausibility = _clamp_plausibility(plausibility_fn(label, activity))
        score = count * plausibility
        if plausibility < 0.2:
            dropped.append(label)
            continue
        surviving.append((label, count, plausibility, score))

    surviving.sort(key=lambda item: (-item[3], -item[1], -item[2], item[0]))
    dropped.sort()

    if not surviving:
        return {
            "chosen": None,
            "confidence": 0.0,
            "reliable": False,
            "candidates": [],
            "dropped": dropped,
        }

    chosen, _, _, chosen_score = surviving[0]
    total_score = sum(score for _, _, _, score in surviving)
    confidence = chosen_score / total_score if total_score else 0.0

    return {
        "chosen": chosen,
        "confidence": confidence,
        "reliable": confidence >= 0.6,
        "candidates": [(label, count, plausibility) for label, count, plausibility, _ in surviving],
        "dropped": dropped,
    }


def reconcile(
    nodes: list[dict],
    activity: str,
    plausibility_fn: Callable[[str, str], float],
) -> list[dict]:
    """Attach reconciled identity decisions to nodes."""
    reconciled_nodes: list[dict] = []
    for node in nodes:
        updated = dict(node)
        result = reconcile_node(updated.get("texts") or [], activity, plausibility_fn)
        updated["reconciled"] = result
        if result["chosen"] is not None:
            updated["identity"] = result["chosen"]
        reconciled_nodes.append(updated)
    return reconciled_nodes


def phrase_uncertainty(reconciled: dict, detail: str) -> str | None:
    """Phrase a detail with calibrated uncertainty."""
    if reconciled.get("reliable"):
        return detail

    chosen = reconciled.get("chosen")
    if chosen:
        return f"I'm not certain it was {chosen}, but if it was, {detail}"

    return None
