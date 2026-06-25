#!/usr/bin/env python3
"""Spatial Localizer — binding keystone for the TRACE perception engine.

For each frame emits narrow, context-free facts WITH location:
  (a) OCR text tokens + their normalized bboxes   (via ocrmac / Apple Vision)
  (b) Dominant colour regions + their normalized bboxes  (PIL + numpy grid blob)

Output: data/walks/<session>/memory/localized_facts.json
Schema:
  [{"t": 2.0, "frame": "...", "facts": [
      {"kind": "text",   "value": "RONTGEN", "bbox": [x, y, w, h]},
      {"kind": "colour", "value": "blue",    "bbox": [x, y, w, h]}
  ]}]

Entrypoint: localize(frames: list[str]) -> str   (returns output path)
Self-test:  python spatial_localizer.py --self-test
CLI:        python spatial_localizer.py --frames-dir DIR --out OUTPUT.json

LABOR NOTE: skeleton drafted by qwen2.5-coder:14b, corrected + verified by Claude.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys

import numpy as np
from PIL import Image


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def time_of(path: str) -> float:
    m = re.search(r"_(\d+\.\d+)s", os.path.basename(path))
    return float(m.group(1)) if m else 0.0


def ocr_facts(img_path: str) -> list[dict]:
    """Run Apple Vision OCR; return list of text facts with normalized bboxes."""
    try:
        from ocrmac import ocrmac as _ocrmac
        res = _ocrmac.OCR(img_path, recognition_level="accurate").recognize()
        facts = []
        for item in res:
            text, conf, bbox = item[0], item[1], item[2]
            if conf >= 0.3 and text.strip():
                # bbox from ocrmac is already [x, y, w, h] normalized 0-1
                facts.append({"kind": "text", "value": text.strip(), "bbox": list(bbox)})
        return facts
    except Exception as e:
        print(f"  ocr_facts error {img_path}: {e}", file=sys.stderr)
        return []


def _name_colour(h: float, s: float, v: float) -> str:
    """Name a colour from HSV where h/s/v are in PIL uint8 range (0-255).

    HSV in PIL: H=0-255 wraps full circle (0=red, 43=yellow, 85=green,
    128=cyan, 170=blue, 213=magenta, 255=red again).
    S=0 means grey/white/black (check V).
    """
    # Achromatic check
    if s < 40:           # low saturation
        if v < 60:
            return "black"
        elif v < 170:
            return "grey"
        else:
            return "white"
    # Chromatic — map H 0-255 to named colour
    if h < 11 or h >= 245:
        return "red"
    elif h < 22:
        return "orange"
    elif h < 43:
        return "yellow"
    elif h < 85:
        return "green"
    elif h < 106:
        return "cyan"
    elif h < 149:
        return "blue"
    elif h < 180:
        return "purple"
    elif h < 213:
        return "pink"
    elif h < 245:
        return "red"   # magenta-red wrap
    return "grey"


def colour_facts(img_path: str, grid_n: int = 8) -> list[dict]:
    """Detect dominant colour regions; return list of colour facts with normalized bboxes."""
    try:
        img = Image.open(img_path).convert("RGB")
        w, h = img.size
        scale = min(1.0, 320 / w)
        nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
        img_small = img.resize((nw, nh), Image.LANCZOS)
        hsv = np.array(img_small.convert("HSV"))  # shape (nh, nw, 3) uint8

        cell_h = nh // grid_n
        cell_w = nw // grid_n
        if cell_h < 1 or cell_w < 1:
            return []

        # Build colour grid[row, col]
        grid: list[list[str]] = []
        for row in range(grid_n):
            grid.append([])
            for col in range(grid_n):
                patch = hsv[row * cell_h:(row + 1) * cell_h,
                            col * cell_w:(col + 1) * cell_w]
                med = np.median(patch.reshape(-1, 3), axis=0)
                grid[row].append(_name_colour(float(med[0]), float(med[1]), float(med[2])))

        # Connected-component merge of same-colour adjacent cells
        visited = [[False] * grid_n for _ in range(grid_n)]
        blobs: list[dict] = []

        for start_row in range(grid_n):
            for start_col in range(grid_n):
                if visited[start_row][start_col]:
                    continue
                colour = grid[start_row][start_col]
                stack = [(start_row, start_col)]
                cells = []
                while stack:
                    r, c = stack.pop()
                    if r < 0 or r >= grid_n or c < 0 or c >= grid_n:
                        continue
                    if visited[r][c]:
                        continue
                    if grid[r][c] != colour:
                        continue
                    visited[r][c] = True
                    cells.append((r, c))
                    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        stack.append((r + dr, c + dc))

                if not cells:
                    continue

                min_row = min(r for r, _ in cells)
                max_row = max(r for r, _ in cells)
                min_col = min(c for _, c in cells)
                max_col = max(c for _, c in cells)

                # Convert grid coords to normalized image coords [x, y, w, h]
                # x = col direction, y = row direction
                bx = (min_col * cell_w) / nw
                by = (min_row * cell_h) / nh
                bw = ((max_col + 1) * cell_w) / nw - bx
                bh = ((max_row + 1) * cell_h) / nh - by

                blobs.append({
                    "kind": "colour",
                    "value": colour,
                    "bbox": [round(bx, 4), round(by, 4), round(bw, 4), round(bh, 4)],
                })

        return blobs

    except Exception as e:
        print(f"  colour_facts error {img_path}: {e}", file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# core entrypoint
# ---------------------------------------------------------------------------

def localize(frames: list[str], out: str | None = None) -> str:
    """Process each frame; write localized_facts.json; return output path."""
    if not frames:
        raise ValueError("frames list is empty")

    if out is None:
        # Derive session path: frames live in .../memory/ or .../work/run_frames/
        # Try to detect .../work/run_frames/ pattern -> go 3 levels up
        first = os.path.abspath(frames[0])
        frames_dir = os.path.dirname(first)
        if os.path.basename(frames_dir) == "run_frames":
            session_dir = os.path.dirname(os.path.dirname(frames_dir))  # skip 'work/'
        else:
            session_dir = os.path.dirname(frames_dir)
        out = os.path.join(session_dir, "memory", "localized_facts.json")

    os.makedirs(os.path.dirname(out), exist_ok=True)

    results = []
    for i, frame in enumerate(frames, 1):
        t = time_of(frame)
        print(f"[{i}/{len(frames)}] t={t:.1f}s  {os.path.basename(frame)}", file=sys.stderr, flush=True)
        text_facts = ocr_facts(frame)
        col_facts = colour_facts(frame)
        results.append({
            "t": t,
            "frame": frame,
            "facts": text_facts + col_facts,
        })
        print(f"  -> {len(text_facts)} text, {len(col_facts)} colour facts", file=sys.stderr, flush=True)

    with open(out, "w") as fh:
        json.dump(results, fh, indent=2)

    print(f"Wrote {len(results)} entries -> {out}", file=sys.stderr, flush=True)
    return out


# ---------------------------------------------------------------------------
# CLI + self-test
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Spatial localizer: OCR + colour facts per frame")
    ap.add_argument("--frames-dir", default="",
                    help="Directory containing frame JPGs")
    ap.add_argument("--out", default="",
                    help="Output JSON path (default: derived from frames-dir)")
    ap.add_argument("--self-test", action="store_true",
                    help="Run on 5 walk frames; assert text+colour facts exist")
    args = ap.parse_args()

    if args.self_test:
        import glob
        walk_dir = "data/walks/walk_outside_20260614/work/run_frames"
        if not os.path.isdir(walk_dir):
            print(f"FAIL: walk dir not found: {walk_dir}")
            return 1
        frames = sorted(glob.glob(os.path.join(walk_dir, "*.jpg")))
        # Use every 10th frame to get spread; take 5
        frames = frames[::10][:5]
        if not frames:
            print("FAIL: no frames found")
            return 1

        print(f"Self-test: localizing {len(frames)} frames from {walk_dir}", file=sys.stderr)
        out_path = localize(frames)
        with open(out_path) as fh:
            data = json.load(fh)

        has_text   = any(any(f["kind"] == "text"   for f in e["facts"]) for e in data)
        has_colour = any(any(f["kind"] == "colour" for f in e["facts"]) for e in data)

        print(f"\nEntries: {len(data)}")
        for e in data:
            tcnt = sum(1 for f in e["facts"] if f["kind"] == "text")
            ccnt = sum(1 for f in e["facts"] if f["kind"] == "colour")
            print(f"  t={e['t']}s  text={tcnt}  colour={ccnt}")

        if has_colour:
            print("PASS (colour facts present)" + (" + text facts" if has_text else " [no text in these frames — OK]"))
            return 0
        else:
            print("FAIL: no colour facts found")
            return 1

    # Normal CLI mode
    if not args.frames_dir:
        ap.print_help()
        return 1

    import glob
    frames = sorted(glob.glob(os.path.join(args.frames_dir, "*.jpg")))
    if not frames:
        print(f"No JPG frames found in {args.frames_dir}", file=sys.stderr)
        return 1

    out = args.out if args.out else None
    localize(frames, out=out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
