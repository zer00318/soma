#!/usr/bin/env python3
"""Cross-frame identity consensus helpers for reliable object reads."""
from __future__ import annotations

import re
from collections import Counter


GENERIC = {"object", "thing", "item", "jar", "bottle", "bag", "container", "box", "can", "cup", "spread",
           "snack", "stuff", "food"}

_CONTAINER_TOKENS = {"jar", "bottle", "bag", "container", "box", "can", "cup"}


def normalize(label: str) -> str:
    """lowercase, strip punctuation, collapse whitespace."""
    text = re.sub(r"[^0-9a-z]+", " ", str(label or "").lower())
    return re.sub(r"\s+", " ", text).strip()


def _strip_generic_edges(tokens: list[str]) -> list[str]:
    start = 0
    end = len(tokens)
    while start < end and tokens[start] in GENERIC:
        start += 1
    while end > start and tokens[end - 1] in GENERIC:
        end -= 1
    return tokens[start:end]


def _sorted_counts(counts: Counter[str]) -> list[tuple[str, int]]:
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def _generic_read(label: str) -> bool:
    tokens = label.split()
    return bool(tokens) and all(token in GENERIC for token in tokens)


def _canonicalize(label: str, exact_labels: set[str]) -> tuple[str, bool]:
    if not label:
        return "", True

    tokens = label.split()
    if all(token in GENERIC for token in tokens):
        return label, True

    core_tokens = _strip_generic_edges(tokens)
    if not core_tokens:
        return label, True

    core = " ".join(core_tokens)
    if core != label and core in exact_labels:
        return core, False

    if core != label and tokens[-1] in (GENERIC - _CONTAINER_TOKENS):
        return label, True

    return label, False


def resolve(reads: list[str]) -> dict:
    """Given the labels an object was read as across frames, return the consensus identity.

    - Count normalized, NON-generic reads. The top label is the consensus.
    - agreement = top_count / total_nongeneric_reads (0..1); 0 if no non-generic reads.
    - confidence tier: "high" if agreement>=0.6 and top_count>=2; "medium" if top_count>=2 or
      agreement>=0.5; else "low".
    - If only generic reads -> label = most common generic, tier "low".
    Return {"label": str, "tier": "high|medium|low", "agreement": float, "alternatives": [(label,count)...]}.
    """
    normalized = [normalize(read) for read in reads]
    exact_labels = {label for label in normalized if label and not _generic_read(label)}

    nongeneric_counts: Counter[str] = Counter()
    generic_counts: Counter[str] = Counter()
    for label in normalized:
        canonical, is_generic = _canonicalize(label, exact_labels)
        if not canonical:
            continue
        if is_generic:
            generic_counts[canonical] += 1
            continue
        nongeneric_counts[canonical] += 1

    if nongeneric_counts:
        ranked = _sorted_counts(nongeneric_counts)
        label, top_count = ranked[0]
        total_nongeneric = sum(nongeneric_counts.values())
        agreement = top_count / total_nongeneric if total_nongeneric else 0.0
        if agreement >= 0.6 and top_count >= 2:
            tier = "high"
        elif top_count >= 2 or agreement >= 0.5:
            tier = "medium"
        else:
            tier = "low"
        alternatives = ranked[1:]
        return {
            "label": label,
            "tier": tier,
            "agreement": agreement,
            "alternatives": alternatives,
        }

    ranked_generic = _sorted_counts(generic_counts)
    label = ranked_generic[0][0] if ranked_generic else ""
    return {
        "label": label,
        "tier": "low",
        "agreement": 0.0,
        "alternatives": ranked_generic[1:],
    }


def is_reliable(consensus: dict) -> bool:
    """True if tier in ('high','medium') — safe to assert; low -> the brain should hedge/refuse."""
    return str(consensus.get("tier") or "").lower() in {"high", "medium"}
