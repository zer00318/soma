#!/usr/bin/env python3
"""Activity-aware reconciliation for conflicting object identity reads."""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, Callable


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


def reconcile_identity(
    reads: list[str],
    *,
    activity: str | None = None,
    plausibility_fn: Callable[[str, str], float] | None = None,
    frame_support: list[Any] | None = None,
) -> dict:
    """Pick ONE primary identity for an entity from its conflicting per-frame reads.

    Pure frequency consensus by default; if ``plausibility_fn`` is given it weights
    each candidate by ``count * plausibility`` (e.g. drop "rocks" while cooking).
    Network/LLM is OPTIONAL — when ``plausibility_fn`` is ``None`` this is a deterministic,
    offline frequency vote, so ingestion never hard-depends on ollama.

    Returns ``{"primary": str|None, "confidence": float, "variants": list[str]}`` where
    ``variants`` are the OTHER non-generic reads (most-frequent first), preserving the
    original surface form for display.
    """
    # Preserve a representative original surface form per normalized label (first seen).
    display: dict[str, str] = {}
    order: list[str] = []
    counts: Counter[str] = Counter()
    for read in reads:
        norm = _normalize(read)
        if not norm or _is_generic(norm):
            continue
        if norm not in display:
            display[norm] = str(read).strip()
            order.append(norm)
        counts[norm] += 1

    if not counts:
        return {"primary": None, "confidence": 0.0, "variants": []}

    use_plausibility = activity is not None and plausibility_fn is not None
    scored: list[tuple[str, float, int]] = []
    for norm, count in counts.items():
        if use_plausibility:
            plausibility = _clamp_plausibility(plausibility_fn(norm, activity))  # type: ignore[arg-type]
            if plausibility < 0.2:
                continue
            score = count * plausibility
        else:
            score = float(count)
        scored.append((norm, score, count))

    if not scored:
        # Everything was dropped by plausibility -> fall back to pure frequency.
        scored = [(norm, float(count), count) for norm, count in counts.items()]

    # Highest score, then highest raw count, then first-seen order as a stable tiebreak.
    scored.sort(key=lambda item: (-item[1], -item[2], order.index(item[0])))

    primary_norm = scored[0][0]
    total_score = sum(score for _, score, _ in scored)
    confidence = scored[0][1] / total_score if total_score else 0.0
    variants = [display[norm] for norm, _, _ in scored[1:]]

    return {
        "primary": display[primary_norm],
        "confidence": round(confidence, 2),
        "variants": variants,
    }


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
