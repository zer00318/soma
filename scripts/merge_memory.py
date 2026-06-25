#!/usr/bin/env python3
"""Merge a base kf_memory with a DENSE-caption kf_memory, per frame.

The dense re-caption unlocked 4 vision questions but LOST 5 (its keyframes/OCR differed from
the base) and added confabulation. This keeps the BASE record (its OCR + caption = the 5 it
answered) and folds the dense caption in as appended DETAIL on the closest-in-time frame — so
the brain keeps everything the base had AND gains the dense object detail, in ONE record per
frame (not a doubled corpus, which would only widen the confabulation surface).

  python scripts/merge_memory.py <base_kf.json> <dense_kf.json> <out_kf.json> [--window 0.6]
"""
from __future__ import annotations
import json, os, sys


def merge(base_path, dense_path, out_path, window=0.6):
    base = json.load(open(base_path))
    dense = json.load(open(dense_path)) if os.path.exists(dense_path) else []
    if not isinstance(base, list):
        base = base.get("frames") or base.get("records") or []
    dense = [d for d in dense if isinstance(d, dict) and d.get("t") is not None]
    out, used = [], 0
    for r in base:
        if not isinstance(r, dict):
            continue
        nr = dict(r)
        t = r.get("t")
        if t is not None and dense:
            best = min(dense, key=lambda d: abs(float(d["t"]) - float(t)))
            if abs(float(best["t"]) - float(t)) <= window and best.get("caption"):
                base_cap = str(nr.get("caption") or "").strip()
                nr["caption"] = (base_cap + "\nDETAIL: " + str(best["caption"]).strip()).strip()
                used += 1
        out.append(nr)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    json.dump(out, open(out_path, "w"), indent=2, ensure_ascii=False)
    print(f"merged {len(out)} base frames; folded dense detail into {used} -> {out_path}")
    return out


def main(argv):
    window = 0.6
    if "--window" in argv:
        i = argv.index("--window"); window = float(argv[i + 1]); del argv[i:i + 2]
    if len(argv) < 3:
        print(__doc__); return 2
    merge(argv[0], argv[1], argv[2], window=window)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
