#!/usr/bin/env python3
"""Jitter-absorption: merge world-binder nodes that are the SAME physical object
split across nodes by estimated-depth jitter (no-LiDAR coordinate wobble).

Merge two same-type nodes when they are close in 3D AND clearly the same object
(share a distinctive brand token, or both are generic), but NEVER merge nodes
with disjoint brands ('nutella' vs 'barilla') even if close.
"""
from __future__ import annotations

import math
import re

# Words that do NOT distinguish two objects (don't justify a merge on their own).
GENERIC = {
    "jar", "jars", "bottle", "bottles", "can", "cans", "container", "containers",
    "spread", "hazelnut", "chocolate", "cup", "box", "pack", "packet", "tube",
    "glass", "of", "the", "a", "an", "with", "lid", "label", "food", "object",
    "snack", "bag",
}


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", str(text).lower())


def brand_tokens(node: dict) -> set[str]:
    """Distinctive lowercase tokens from a node's texts/label (len>=3, not GENERIC)."""
    out: set[str] = set()
    texts = list(node.get("texts") or [])
    if node.get("label"):
        texts.append(node["label"])
    for t in texts:
        for tok in _tokens(t):
            if len(tok) >= 3 and tok not in GENERIC:
                out.add(tok)
    return out


def _norm_type(node: dict) -> str:
    return str(node.get("type") or "").strip().lower()


def _dist(a, b) -> float | None:
    if not a or not b:
        return None
    return math.sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(a, b)))


def _should_merge(n1: dict, n2: dict, radius_m: float) -> bool:
    if _norm_type(n1) != _norm_type(n2):
        return False
    d = _dist(n1.get("world_xyz"), n2.get("world_xyz"))
    if d is None or d > radius_m:
        return False
    b1, b2 = brand_tokens(n1), brand_tokens(n2)
    if b1 and b2:
        return bool(b1 & b2)          # share a brand -> same object; disjoint -> different
    return True                       # at least one generic, same type, close -> same object


def _merge_pair(n1: dict, n2: dict) -> dict:
    frames = sorted(set(n1.get("frames") or []) | set(n2.get("frames") or []))
    texts: list[str] = []
    seen = set()
    for t in list(n1.get("texts") or []) + list(n2.get("texts") or []):
        if str(t).lower() not in seen:
            texts.append(t)
            seen.add(str(t).lower())
    xyzs = [n.get("world_xyz") for n in (n1, n2) if n.get("world_xyz")]
    if xyzs:
        world = [sum(c) / len(xyzs) for c in zip(*xyzs)]
    else:
        world = n1.get("world_xyz") or n2.get("world_xyz")
    merged = dict(n1)
    merged["frames"] = frames
    merged["count_frames"] = len(frames)
    merged["texts"] = texts
    merged["world_xyz"] = world
    merged["located"] = bool(n1.get("located") or n2.get("located"))
    merged["label"] = n1.get("label") or n2.get("label")
    return merged


def _counts(nodes: list[dict]) -> dict:
    out: dict[str, dict] = {}
    for n in nodes:
        t = _norm_type(n) or "object"
        bucket = out.setdefault(t, {"distinct": 0, "located": 0})
        bucket["distinct"] += 1
        if n.get("located"):
            bucket["located"] += 1
    return dict(sorted(out.items()))


def merge_jittered(binder_result: dict, radius_m: float = 0.15) -> dict:
    """Merge same-object nodes split by depth jitter. Returns a new binder_result."""
    nodes = [dict(n) for n in (binder_result.get("nodes") or [])]
    # Iterate to a fixpoint: each pass merges the first mergeable pair found.
    changed = True
    while changed and len(nodes) > 1:
        changed = False
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                if _should_merge(nodes[i], nodes[j], radius_m):
                    nodes[i] = _merge_pair(nodes[i], nodes[j])
                    del nodes[j]
                    changed = True
                    break
            if changed:
                break
    counts = _counts(nodes)
    parts = [f"{t} {info['distinct']}" for t, info in counts.items()]
    summary = (f"After jitter merge: {len(nodes)} distinct objects — "
               + ", ".join(parts) + ".") if nodes else "No objects."
    return {"nodes": nodes, "counts_by_type": counts, "summary": summary}
