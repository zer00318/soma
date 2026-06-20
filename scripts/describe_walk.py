#!/usr/bin/env python3
"""Build a searchable memory of a walk by UNDERSTANDING scenes, not labeling crops.

Picks distinct keyframes from the walk (skips near-duplicates, cheaply, no
GPU), then asks a vision model to describe each scene factually — objects,
the TEXT on things, and the layout. Writes one memory record per keyframe:
{t, frame, description}. Checkpointed so a reboot costs minutes, not hours.
This replaces the crop -> CLIP-label -> 700-fragments pipeline.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.request

PROMPT = (
    "You are building a searchable memory of someone's home so they can ask "
    "questions later. Describe THIS scene factually for recall. "
    "1) List the real objects you can see. "
    "2) READ any text, labels, brand names, numbers, or writing visible and quote it exactly. "
    "3) Note the layout: what is on or next to what, foreground vs background, left vs right. "
    "Be concrete. Do not invent anything you cannot actually see."
)


def time_of(path: str) -> float:
    m = re.search(r"_(\d+\.\d+)s", os.path.basename(path or ""))
    return float(m.group(1)) if m else 0.0


def frame_signature(path: str, size: int = 16):
    """Tiny grayscale fingerprint for cheap near-duplicate detection (no GPU)."""
    from PIL import Image
    im = Image.open(path).convert("L").resize((size, size))
    return list(im.getdata())


def too_similar(sig, kept_sigs, thresh: float) -> bool:
    for k in kept_sigs:
        diff = sum(abs(a - b) for a, b in zip(sig, k)) / len(sig)
        if diff < thresh:
            return True
    return False


def _uniform_cover(items, cap):
    """Cap a chronological sequence without chopping off its tail."""
    if not cap or len(items) <= cap:
        return items
    if cap == 1:
        return [items[len(items) // 2]]
    last = len(items) - 1
    indices = [round(i * last / (cap - 1)) for i in range(cap)]
    return [items[i] for i in indices]


def pick_keyframes(frames, thresh=14.0, cap=90):
    kept, sigs = [], []
    for f in frames:
        try:
            sig = frame_signature(f)
        except Exception:
            continue
        if too_similar(sig, sigs, thresh):
            continue
        sigs.append(sig)
        kept.append(f)
    return _uniform_cover(kept, cap)


def describe(frame, model, host, timeout=180.0):
    img = base64.b64encode(open(frame, "rb").read()).decode()
    req = urllib.request.Request(
        host.rstrip("/") + "/api/generate",
        data=json.dumps({"model": model, "prompt": PROMPT, "images": [img],
                         "stream": False, "options": {"temperature": 0}}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace")).get("response", "").strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames-dir", default="")
    ap.add_argument("--out", default="/tmp/walk_memory.json")
    ap.add_argument("--model", default="gemma3:12b-it-qat")
    ap.add_argument("--ollama-host", default="http://127.0.0.1:11434")
    ap.add_argument("--dedup-thresh", type=float, default=14.0)
    ap.add_argument("--cap", type=int, default=90)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        # dedup logic only (no model, no real frames)
        assert too_similar([0] * 256, [[0] * 256], 1.0)
        assert not too_similar([255] * 256, [[0] * 256], 1.0)
        assert _uniform_cover(list(range(10)), 4) == [0, 3, 6, 9]
        assert _uniform_cover(list(range(3)), 4) == [0, 1, 2]
        print("SELF-TEST PASS")
        return 0

    import glob
    frames = sorted(glob.glob(os.path.join(args.frames_dir, "*.jpg")), key=time_of)
    keys = pick_keyframes(frames, args.dedup_thresh, args.cap)
    print(f"{len(frames)} frames -> {len(keys)} distinct keyframes", file=sys.stderr, flush=True)

    ckpt = args.out + ".ckpt.ndjson"
    done = {}
    if os.path.exists(ckpt):
        for line in open(ckpt):
            try:
                r = json.loads(line); done[r["frame"]] = r
            except Exception:
                pass
        print(f"resume: {len(done)} keyframes already described", file=sys.stderr, flush=True)

    fh = open(ckpt, "a")
    memory = []
    for i, f in enumerate(keys, 1):
        if f in done:
            memory.append(done[f]); continue
        try:
            desc = describe(f, args.model, args.ollama_host)
        except Exception as e:
            print(f"  err {f}: {e}", file=sys.stderr, flush=True); continue
        rec = {"t": time_of(f), "frame": f, "description": desc}
        memory.append(rec)
        fh.write(json.dumps(rec) + "\n"); fh.flush()
        if i % 5 == 0 or i == len(keys):
            print(f"described {i}/{len(keys)} keyframes", file=sys.stderr, flush=True)
    fh.close()
    memory.sort(key=lambda r: r["t"])
    json.dump(memory, open(args.out, "w"), indent=2)
    print(f"WROTE {len(memory)} scene memories to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
