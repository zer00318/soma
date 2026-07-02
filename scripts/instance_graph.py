#!/usr/bin/env python3
"""Instance graph + LLM meta-reasoner (the binder + brain, demo / image-space version).

Takes the instances from instance_perceive (each: box, det_label, name, text, colour,
state, ...) and:
  1. builds a SCENE GRAPH — nodes = instances, edges = spatial relations DERIVED from box
     geometry (on-top-of / next-to / contains). Deterministic; no LLM guessing here.
  2. lets the LLM do META-COMMENTARY over the graph: count = number of nodes of a type;
     "which is on top" = read an edge; attributes = read node fields.

Counting and relations are DERIVED, never asserted by a helper. World-anchoring (ARKit)
replaces image-space boxes later; the graph logic is unchanged.

    .venv/bin/python scripts/instance_graph.py <instances.json> --ask "how many jars"
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from collections import Counter
from pathlib import Path

OLLAMA = "http://127.0.0.1:11434"
REASON_MODEL = "gemma3:27b-it-qat"   # same model as the perceiver -> no swap churn in 32GB

_TYPE_NORM = {
    "jars": "jar", "bottles": "bottle", "laptops": "laptop", "phones": "phone",
    "rings": "ring", "books": "book", "cups": "cup", "cans": "can", "shoes": "shoe",
}


def _norm_type(inst: dict) -> str:
    lab = (inst.get("det_label") or inst.get("name") or "object").strip().lower()
    lab = re.sub(r"^(a |an |the )", "", lab)
    head = lab.split()[0] if lab.split() else lab
    return _TYPE_NORM.get(head, head)


def _categorize(name: str, text: str, det_label: str) -> str:
    """Coarse category for an instance, PREFERRING the VLM-read identity (name/text)
    over the detector's class label, which is often wrong (a chip bag detected as
    'blanket', a phone as 'monitor'). Map known brands/keywords to a category; only
    fall back to the detector label when the identity gives no signal.

    Implemented by the local-LLM worker (task: instance_categorize), Chief-reviewed.
    Returns a category like 'snack', 'condiment', 'electronics', 'beverage',
    'food', 'clothing', else the cleaned detector label.
    """
    keyword_map = {
        "lays": "snack", "doritos": "snack", "pringles": "snack", "chips": "snack",
        "tortilla": "snack", "crisps": "snack",
        "iphone": "electronics", "macbook": "electronics", "samsung": "electronics",
        "galaxy": "electronics", "laptop": "electronics", "monitor": "electronics",
        "phone": "electronics", "ipad": "electronics",
        "heinz": "condiment", "ketchup": "condiment", "mustard": "condiment",
        "mayo": "condiment", "sauce": "condiment",
        "coke": "beverage", "pepsi": "beverage", "water": "beverage", "juice": "beverage",
        "soda": "beverage",
        "nutella": "food", "jam": "food", "bread": "food", "cheese": "food",
        "shoe": "clothing", "shirt": "clothing", "adidas": "clothing", "nike": "clothing",
        "pants": "clothing",
    }
    name_lower = name.lower()
    text_lower = text.lower()
    for keyword, category in keyword_map.items():
        if keyword in name_lower or keyword in text_lower:
            return category
    cleaned = (det_label or name or "object").strip().lower()
    return re.sub(r"^(a |an |the )", "", cleaned)


def _rel(a: dict, b: dict) -> str | None:
    """Spatial relation of A to B from image-space boxes (y grows DOWN).
    Returns 'on'(A on top of B) / 'next_to' / 'in'(A inside B) / None."""
    ax0, ay0, ax1, ay1 = a["box"]
    bx0, by0, bx1, by1 = b["box"]
    # containment: A mostly inside B
    inter_x = max(0, min(ax1, bx1) - max(ax0, bx0))
    inter_y = max(0, min(ay1, by1) - max(ay0, by0))
    inter = inter_x * inter_y
    area_a = max(1, (ax1 - ax0) * (ay1 - ay0))
    if inter / area_a > 0.75:
        return "in"
    # horizontal overlap fraction (of the narrower box)
    hov = inter_x / max(1, min(ax1 - ax0, bx1 - bx0))
    # vertical overlap fraction
    vov = inter_y / max(1, min(ay1 - ay0, by1 - by0))
    # A on top of B: A's bottom near B's top, strong horizontal overlap, A above B
    if hov > 0.4 and ay1 <= by1 and abs(ay1 - by0) < 0.25 * (by1 - by0 + 1):
        return "on"
    # next to: similar vertical band, horizontally adjacent, little vertical stacking
    gap = max(bx0 - ax1, ax0 - bx1)
    if vov > 0.3 and gap < 0.3 * (ax1 - ax0 + bx1 - bx0) and hov < 0.2:
        return "next_to"
    return None


def build_graph(instances: list[dict]) -> dict:
    nodes = []
    for i, inst in enumerate(instances):
        nodes.append({
            "id": i, "type": _norm_type(inst),
            "category": _categorize(inst.get("name", ""), inst.get("text", ""),
                                    inst.get("det_label", "")),
            "name": inst.get("name", "") or inst.get("det_label", ""),
            "text": inst.get("text", ""), "colour": inst.get("colour", ""),
            "material": inst.get("material", ""), "state": inst.get("state", ""),
            "orient": inst.get("orient", ""), "box": inst.get("box"),
        })
    edges = []
    for a in nodes:
        for b in nodes:
            if a["id"] == b["id"]:
                continue
            r = _rel({"box": a["box"]}, {"box": b["box"]})
            if r:
                edges.append({"from": a["id"], "to": b["id"], "rel": r})
    counts = Counter(n["type"] for n in nodes)
    return {"nodes": nodes, "edges": edges, "counts": dict(counts)}


def count_by_category(graph: dict) -> dict:
    """Group node counts by CATEGORY (not raw det type), so 'how many snacks?' answers
    correctly across 'Lays' and 'Doritos' (both category 'snack'). Return {category: count},
    e.g. {'snack': 2, 'electronics': 1}. Skip nodes whose category is empty/'object'.
    Implemented by the local-LLM worker (task: graph_count_by_category), Chief-reviewed."""
    counts = Counter()
    for node in graph["nodes"]:
        category = node.get("category")
        if category and category != "object":
            counts[category] += 1
    return dict(counts)


def render_graph(graph: dict) -> str:
    lines = ["INSTANCES (each is one physical object, with derived attributes):"]
    for n in graph["nodes"]:
        bits = [f'#{n["id"]} {n["type"]}']
        if n["name"] and n["name"].lower() not in (n["type"], "none"):
            bits.append(f'"{n["name"]}"')
        for k in ("colour", "material", "state", "orient"):
            if n.get(k) and n[k].lower() not in ("unknown", "none", ""):
                bits.append(f'{k}={n[k]}')
        if n.get("text") and n["text"].upper() != "NONE":
            bits.append(f'text="{n["text"]}"')
        lines.append("  " + " ".join(bits))
    if graph["edges"]:
        lines.append("\nSPATIAL RELATIONS (derived from geometry):")
        rel_word = {"on": "is on top of", "next_to": "is next to", "in": "is inside"}
        for e in graph["edges"]:
            lines.append(f'  #{e["from"]} {rel_word.get(e["rel"], e["rel"])} #{e["to"]}')
    lines.append("\nCOUNTS BY TYPE (derived): " +
                 ", ".join(f"{v} {k}" for k, v in graph["counts"].items()))
    return "\n".join(lines)


def answer(graph: dict, question: str) -> str:
    brief = render_graph(graph)
    prompt = (
        "You are answering from a structured scene graph built by perception helpers. "
        "Every instance is a real object that was seen; counts and relations are already "
        "derived for you. Answer the question from this data ONLY. If the data does not "
        "contain it, say 'I don't have that in what I saw.' Be direct and concise.\n\n"
        f"{brief}\n\nQUESTION: {question}\nANSWER:"
    )
    body = {"model": REASON_MODEL, "prompt": prompt, "stream": False,
            "options": {"temperature": 0}}
    req = urllib.request.Request(f"{OLLAMA}/api/generate",
                                 data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=120))["response"].strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("instances")
    ap.add_argument("--ask", nargs="*", default=[])
    args = ap.parse_args()

    instances = json.loads(Path(args.instances).read_text())
    graph = build_graph(instances)
    print(render_graph(graph))
    for q in args.ask:
        print(f"\nQ: {q}\n  A: {answer(graph, q)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
