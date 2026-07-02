#!/usr/bin/env python3
"""Multi-object permanence — collapse cross-frame RE-observations of the same physical
object into distinct instances, WITHOUT coordinates or pose (both are unreliable/absent in
real captures) and WITHOUT pixels (product deletes frames; helpers run on-device and emit
text). The only reliable signal in the live stream is the helper text itself: the object's
label + its described attributes (colour / material / kind) + temporal order.

The founder's ask, in plain terms: "is the object in frame 4 the same as the one in frame 25,
or is it a new one?" Answer it on the text:
  - same label + compatible attributes (same colour/material family), seen across frames
    -> ONE physical object re-observed (merge).
  - same label but incompatible attributes (clear-glass vs blue-plastic) -> DIFFERENT objects.

A local LLM (gemma on the Mac) makes the merge/split call; a deterministic attribute-signature
clusterer is the fallback when no LLM is reachable, so counting never silently depends on a
network hop. Counting is then just: how many distinct instances of the asked subject.

CLI:
    .venv/bin/python scripts/permanence.py --store data/trace_store.sqlite3 \
        --subject "water bottle" --source phone_camera
    .venv/bin/python scripts/permanence.py --self-test
"""
from __future__ import annotations

import json
import re
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# Colour / material vocab used as the deterministic discriminator (fallback path only). Two
# same-label reads with disjoint, non-empty colour+material signatures are DIFFERENT objects.
_COLOURS = {
    "red", "orange", "yellow", "green", "blue", "cyan", "teal", "purple", "magenta", "pink",
    "brown", "black", "white", "grey", "gray", "silver", "gold", "clear", "transparent",
    "cream", "beige", "tan", "violet",
}
_MATERIALS = {
    "plastic", "glass", "metal", "steel", "ceramic", "wood", "wooden", "paper", "cardboard",
    "fabric", "cloth", "leather", "rubber", "stainless",
}
# Colour synonyms that should NOT be treated as conflicting (VLM lexical drift for one object).
_COLOUR_FAMILIES = [
    {"teal", "cyan", "green", "blue"},      # blue-green drift
    {"grey", "gray", "silver"},
    {"clear", "transparent", "white"},
    {"violet", "purple", "magenta"},
    {"cream", "beige", "tan", "white"},
]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^0-9a-z]+", " ", str(text or "").lower())).strip()


@dataclass
class Read:
    """One per-frame observation of an object, parsed from the helper text line."""
    node_id: str
    t_ms: int
    label: str          # head noun, e.g. "water bottle"
    desc: str           # descriptor phrase, e.g. "blue plastic bottle | counter"
    raw: str
    colours: set[str] = field(default_factory=set)
    materials: set[str] = field(default_factory=set)

    def signature(self) -> tuple[frozenset[str], frozenset[str]]:
        return frozenset(self.colours), frozenset(self.materials)


def _parse_object_line(line: str) -> tuple[str, str] | None:
    """Parse the on-device helper formats into (label, descriptor).
    Handles:  'OBJECT | water bottle | blue plastic bottle | counter | likely'
              '#6 jar "Water bottle" colour=Silver material=Metal state=Closed'
    Returns None for non-object lines."""
    s = line.strip()
    low = s.lower()
    if low.startswith("object |") or low.startswith("object|"):
        parts = [p.strip() for p in s.split("|")[1:] if p.strip()]
        parts = [p for p in parts if p.lower() not in {"likely", "unsure", "certain"}]
        if not parts:
            return None
        label = parts[0]
        desc = " | ".join(parts[1:]) if len(parts) > 1 else ""
        return label, desc
    m = re.search(r'"([^"]+)"', s)
    if ("colour=" in low or "color=" in low or "material=" in low) and m:
        label = m.group(1)
        attrs = " ".join(re.findall(r"(?:colour|color|material|state|orient)=(\S+)", s, re.I))
        return label, attrs
    return None


def _extract_attrs(text: str) -> tuple[set[str], set[str]]:
    toks = set(_norm(text).split())
    return toks & _COLOURS, toks & _MATERIALS


def _colours_conflict(a: set[str], b: set[str]) -> bool:
    """Two colour sets conflict only if both are non-empty AND no shared colour and they don't
    fall in the same colour family (VLM lexical drift for the same object is not a conflict)."""
    if not a or not b or (a & b):
        return False
    for fam in _COLOUR_FAMILIES:
        if (a & fam) and (b & fam):
            return False
    return True


_SUBJECT_FILLER = {"the", "a", "an", "in", "on", "of", "there", "were", "was", "are", "is",
                   "total", "currently", "current", "my", "some", "any", "how", "many", "all"}


# Irregular plurals the suffix rule can't reach — without these, "how many mice" matches no
# label and the caller silently falls back to another noun in the question.
_IRREGULAR_PLURALS = {
    "mice": "mouse", "geese": "goose", "people": "person", "men": "man", "women": "woman",
    "children": "child", "feet": "foot", "teeth": "tooth", "knives": "knife",
    "shelves": "shelf", "leaves": "leaf", "loaves": "loaf", "wolves": "wolf", "dice": "die",
    "buses": "bus",
}


def _sing(t: str) -> str:
    if t in _IRREGULAR_PLURALS:
        return _IRREGULAR_PLURALS[t]
    if len(t) > 4 and t.endswith(("sses", "xes", "zes", "ches", "shes")):
        return t[:-2]
    return t[:-1] if len(t) > 3 and t.endswith("s") and not t.endswith("ss") else t


def _label_matches_subject(label: str, subject_tokens: set[str]) -> bool:
    """Match if any SIGNIFICANT subject noun (len>2, not filler) appears in the label —
    tolerant of messy question phrasing ("nutella jars were there in total") and plurals."""
    lab = {_sing(t) for t in _norm(label).split()}
    subj = {_sing(t) for t in subject_tokens if len(t) > 2 and t not in _SUBJECT_FILLER}
    return bool(subj & lab)


def gather_reads(store: Any, subject: str, sources: tuple[str, ...] | None) -> list[Read]:
    """Collect every observation whose parsed object label matches the subject."""
    subject_tokens = set(_norm(subject).split())
    reads: list[Read] = []
    for node in store.nodes(node_types=("observation", "entity"), sources=sources):
        for line in str(node.text or "").splitlines():
            parsed = _parse_object_line(line)
            if not parsed:
                continue
            label, desc = parsed
            if not _label_matches_subject(label, subject_tokens):
                continue
            cols, mats = _extract_attrs(f"{label} {desc}")
            reads.append(Read(node_id=node.id, t_ms=int(node.t_ms), label=_norm(label),
                              desc=desc.strip(), raw=line.strip(), colours=cols, materials=mats))
            break  # one read per node (avoid double-counting a multi-line dump)
    reads.sort(key=lambda r: (r.t_ms, r.node_id))
    return reads


# ---- deterministic fallback: attribute-signature clustering -------------------------------

def _cluster_deterministic(reads: list[Read]) -> list[list[Read]]:
    """Greedy single-link clustering: a read joins an existing instance unless its colour
    signature CONFLICTS with that instance's. Empty-attribute reads fold into the nearest
    (first) instance rather than inflating the count."""
    instances: list[list[Read]] = []
    inst_cols: list[set[str]] = []
    for r in reads:
        placed = False
        for i, cols in enumerate(inst_cols):
            if not _colours_conflict(r.colours, cols):
                instances[i].append(r)
                inst_cols[i] = cols | r.colours
                placed = True
                break
        if not placed:
            instances.append([r])
            inst_cols.append(set(r.colours))
    return instances


# ---- local-LLM arbiter -------------------------------------------------------------------

def _llm_instances(reads: list[Read], subject: str, model: str, host: str,
                   timeout: float) -> list[dict[str, Any]] | None:
    """Ask gemma to merge re-observations and split genuinely distinct objects. Returns a list
    of {canonical, read_indexes:[...]} or None on any failure (caller falls back)."""
    lines = [f"{i}: {r.raw}" for i, r in enumerate(reads)]
    prompt = (
        "You resolve OBJECT PERMANENCE from a wearable camera's per-frame detections.\n"
        f"All lines below are detections of '{subject}' seen across many frames as the wearer "
        "moved. The SAME physical object is detected many times (that is normal — merge those). "
        "Two detections are DIFFERENT physical objects only if their described attributes are "
        "incompatible (e.g. a clear glass bottle vs a blue plastic bottle vs a silver metal "
        "bottle are three different objects). Minor wording differences (teal vs cyan vs green) "
        "are the SAME object. Group the detections into distinct physical objects.\n\n"
        "DETECTIONS:\n" + "\n".join(lines) + "\n\n"
        "Return STRICT JSON only: {\"instances\": [{\"canonical\": short label with key "
        "attributes, \"reads\": [line numbers]}]}. Every line number appears in exactly one "
        "instance. The number of instances is your count."
    )
    body = {"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0}}
    try:
        req = urllib.request.Request(f"{host.rstrip('/')}/api/generate",
                                     data=json.dumps(body).encode(),
                                     headers={"content-type": "application/json"})
        raw = json.load(urllib.request.urlopen(req, timeout=timeout)).get("response", "")
        obj = json.loads(re.search(r"\{.*\}", raw, re.DOTALL).group(0))
        insts = obj.get("instances")
        if not isinstance(insts, list) or not insts:
            return None
        # validate coverage
        seen = set()
        for it in insts:
            for idx in it.get("reads", []):
                if isinstance(idx, int) and 0 <= idx < len(reads):
                    seen.add(idx)
        if len(seen) < max(1, len(reads) // 2):
            return None  # too many dropped -> untrustworthy, fall back
        return insts
    except Exception:
        return None


_NUM_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
              "nine": 9, "ten": 10, "several": 2, "multiple": 2, "couple": 2, "pair": 2, "few": 2}


def explicit_count_floor(store: Any, subject: str,
                         sources: tuple[str, ...] | None) -> tuple[int, str]:
    """Cross-frame clustering CANNOT separate identical-looking multiples (3 grey pillows read
    the same collapse to 1). The rescue is the VLM's OWN per-frame count: a single frame that
    says "3 jars" or "on top of another pillow" is direct evidence of >=N objects present at
    once. Return the largest such count found in any single observation + its evidence line.
    Approximate words (several/multiple) yield a soft floor of 2, never a confident exact."""
    # Consider EVERY significant subject noun (not just the longest): "nutella jars" must key
    # the floor on "jar" (the countable container: inventory says "5 jar"), not on "nutella".
    heads = [_sing(t) for t in _norm(subject).split()
             if len(t) > 2 and t not in _SUBJECT_FILLER]
    if not heads:
        return 0, ""
    best, evidence = 0, ""
    for head_sing in heads:
        # Exclude '#N <noun>' — that is an INSTANCE INDEX in a '#0 phone / #1 jar' enumeration,
        # not a count. Require the digit not be preceded by '#' or another word char.
        pat_num = re.compile(rf"(?<![#\w])(\d+)\s+\w*{re.escape(head_sing)}\w*\b", re.I)
        pat_word = re.compile(rf"\b({'|'.join(_NUM_WORDS)})\s+\w*{re.escape(head_sing)}\w*\b", re.I)
        for node in store.nodes(node_types=("observation", "entity"), sources=sources):
            text = str(node.text or "")
            low = _norm(text)
            if head_sing not in low:
                continue
            for m in pat_num.finditer(text):
                if m.group(1).startswith("0"):
                    continue  # leading zero -> timestamp/index/OCR garble, not a count
                n = int(m.group(1))
                # Cap at 20: a single frame asserting >20 of one household object is almost
                # always OCR gibberish ("...sume 52 nutella...") or a stray index, not a count.
                if 1 < n <= 20 and n > best:
                    best, evidence = n, m.group(0)
            if best == 0:
                for m in pat_word.finditer(text):
                    n = _NUM_WORDS[m.group(1).lower()]
                    if n > best:
                        best, evidence = n, m.group(0)
            if "on top of another" in low and head_sing in low and best < 2:
                best, evidence = 2, "on top of another " + head_sing
    return best, evidence


@dataclass
class CountResult:
    subject: str
    count: int
    method: str
    instances: list[dict[str, Any]]
    n_reads: int
    floor: int = 0
    floor_evidence: str = ""


def count_instances(store: Any, subject: str, *, sources: tuple[str, ...] | None = None,
                    model: str = "gemma3:12b-it-qat", host: str = "http://127.0.0.1:11434",
                    use_llm: bool = True, timeout: float = 120.0) -> CountResult:
    floor, floor_ev = explicit_count_floor(store, subject, sources)
    reads = gather_reads(store, subject, sources)
    if not reads and floor == 0:
        return CountResult(subject, 0, "no-reads", [], 0)

    method = "deterministic"
    instances: list[dict[str, Any]] = []
    if reads:
        llm = _llm_instances(reads, subject, model, host, timeout) if use_llm else None
        if llm is not None:
            method = "llm-arbiter"
            instances = [{"canonical": it.get("canonical", ""),
                          "n_frames": len(it.get("reads", [])),
                          "citation_ids": [reads[i].node_id for i in it.get("reads", [])
                                           if isinstance(i, int) and 0 <= i < len(reads)]}
                         for it in llm]
        else:
            clusters = _cluster_deterministic(reads)
            instances = [{"canonical": Counter(r.desc or r.label
                                               for r in cl).most_common(1)[0][0],
                          "n_frames": len(cl), "citation_ids": [r.node_id for r in cl]}
                         for cl in clusters]

    # The count is the MAX of distinct instances found across frames and the largest count the
    # VLM asserted within a single frame (the identical-multiples rescue).
    count = max(len(instances), floor)
    if floor > len(instances):
        method += "+frame-count-floor"
    return CountResult(subject, count, method, instances, len(reads),
                       floor=floor, floor_evidence=floor_ev)
