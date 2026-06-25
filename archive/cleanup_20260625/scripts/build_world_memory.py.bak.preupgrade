#!/usr/bin/env python3
"""Build ONE continuous, deduplicated memory of a space from a walk — not a pile
of per-photo descriptions.

The failure this fixes: asked "how many nutella jars", the per-frame system said
"6 across three scenes" — it recounted the SAME jars every time they reappeared.
A memory must know there are N DISTINCT jars, once, however many frames show them.

How: walk the keyframes in time order, carrying a running INVENTORY of distinct
objects. For each new chunk of frames, a model decides which observations are the
SAME items already in the inventory (continuing) vs genuinely NEW distinct items,
and refines counts/attributes. The output is a single world memory (text/JSON).
Questions are answered from THIS — never from the photos (the product keeps none).

Input: kf_memory.json (per-frame caption+OCR, time-ordered). Checkpointed.
"""
from __future__ import annotations
import argparse, json, os, re, sys, urllib.request

UPDATE_SYS = (
    "You maintain a running INVENTORY of the distinct physical objects in one room, "
    "built by watching a walk-through in order. You are given the inventory so far and "
    "new observations from the next few moments (each a description + any text read).\n"
    "CRITICAL: the walk keeps RE-SEEING the same objects. Do NOT add a new entry or "
    "increase a count for something already in the inventory — only merge/refine it. "
    "Add an entry ONLY for a genuinely new distinct object not seen before. If a single "
    "moment clearly shows several of the same item (e.g. three identical jars side by "
    "side), set that item's count to the MOST seen together in one moment — never the sum "
    "across moments.\n"
    'Return ONLY a JSON object of the form {"objects": [ ... ]} where each element is '
    '{"name": str, "count": int, "attributes": str, "where": str}. '
    "Include EVERY distinct object known so far, not just the new ones. "
    "Keep names plain and singular (e.g. 'nutella jar'). Be conservative; merge aggressively."
)


def chat(messages, model, host, timeout=180):
    req = urllib.request.Request(
        host.rstrip("/") + "/api/chat",
        data=json.dumps({"model": model, "messages": messages, "stream": False,
                         "format": "json", "options": {"temperature": 0}}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))["message"]["content"]


def parse_inventory(s):
    try:
        v = json.loads(s)
    except Exception:
        m = re.search(r"\[.*\]", s, re.S)
        if not m:
            return None
        try:
            v = json.loads(m.group(0))
        except Exception:
            return None
    if isinstance(v, dict):
        for k in ("inventory", "objects", "items"):
            if isinstance(v.get(k), list):
                return v[k]
        # a single object {name,count,...} -> one-element inventory
        if "name" in v:
            return [v]
        return None
    return v if isinstance(v, list) else None


def condense(rec, maxlen=240):
    cap = (rec.get("caption") or "")[:maxlen]
    ocr = rec.get("ocr") or []
    txt = (" | text read: " + "; ".join(ocr)) if ocr else ""
    return "(t=%.0fs) %s%s" % (rec.get("t", 0), cap, txt)


def build(frames, model, host, chunk=5, log=sys.stderr):
    inventory = []
    for i in range(0, len(frames), chunk):
        batch = frames[i:i + chunk]
        obs = "\n".join(condense(r) for r in batch)
        msgs = [
            {"role": "system", "content": UPDATE_SYS},
            {"role": "user", "content": "INVENTORY SO FAR:\n%s\n\nNEW OBSERVATIONS:\n%s\n\n"
             "Return the full updated inventory as a JSON array."
             % (json.dumps(inventory, ensure_ascii=False), obs)},
        ]
        try:
            out = chat(msgs, model, host)
            new = parse_inventory(out)
            if new is not None:
                inventory = new
        except Exception as e:
            print("  chunk %d err: %s" % (i, e), file=log, flush=True)
        print("after t<=%.0fs: %d distinct objects" % (batch[-1].get("t", 0), len(inventory)),
              file=log, flush=True)
    return inventory


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--memory", default="data/walks/home_capture_20260613/memory/kf_memory.json")
    ap.add_argument("--out", default="data/walks/home_capture_20260613/memory/world_memory.json")
    ap.add_argument("--model", default="gemma3:12b-it-qat")
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--chunk", type=int, default=5)
    ap.add_argument("--from-t", type=float, default=0.0)
    ap.add_argument("--to-t", type=float, default=1e9)
    args = ap.parse_args()

    mem = json.load(open(args.memory))
    mem = [r for r in mem if args.from_t <= r.get("t", 0) <= args.to_t]
    mem.sort(key=lambda r: r.get("t", 0))
    print("building world memory from %d frames" % len(mem), file=sys.stderr, flush=True)
    inv = build(mem, args.model, args.host, args.chunk)
    inv = sorted(inv, key=lambda o: -(o.get("count") or 1))
    json.dump({"objects": inv, "n_frames": len(mem)}, open(args.out, "w"), indent=2, ensure_ascii=False)
    print("\nWROTE %d distinct objects to %s" % (len(inv), args.out))
    for o in inv[:40]:
        print("  %2sx %-22s %s" % (o.get("count"), o.get("name"), (o.get("attributes") or "")[:50]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
