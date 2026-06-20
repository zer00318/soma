#!/usr/bin/env python3
"""CAPTURE-TIME micro-detail pass (2026-06-14 founder mandate).

The whole-frame caption/OCR (build_keyframe_memory.py) gets the MACRO but blurs
the MICRO: small/edge text on a plaque, a laptop screen, a far-off sign. So for a
BOUNDED set of the highest-value frames, split each frame into a grid of regions
and run Apple Vision OCR (ocrmac) on EACH region crop separately. A region crop is
effectively a zoom — Vision reads small text it skipped in the full frame.

This is CAPTURE-TIME text. The query path reads micro_details.json, never the frame.

Bounded by design: ~12 frames x grid regions x ~0.5s OCR. No per-region VLM.

Draft seeded by local qwen2.5-coder:14b, then integrated + debugged.

Output: JSON list of {t, frame, region, bbox, micro_ocr:[...]} (empty regions dropped).

Run:
  .venv/bin/python scripts/build_micro_details.py \
      --frames data/walks/walk_outside_20260614/work/run_frames \
      --kf     data/walks/walk_outside_20260614/memory/kf_memory.json \
      --out    data/walks/walk_outside_20260614/memory/micro_details.json
"""
from __future__ import annotations
import argparse, json, os, re, sys, tempfile, time

# Keywords in caption/OCR that mark a frame as text-bearing (worth a micro pass).
HIGH_VALUE = re.compile(
    r"poster|sign|screen|board|text|plaque|label|laptop|display|monitor|"
    r"placard|notice|banner|writing|words|letters|name",
    re.IGNORECASE,
)


def time_of(path: str) -> float:
    """Extract the float seconds from a frame filename like frame_000360_12.0s.jpg."""
    m = re.search(r"_(\d+(?:\.\d+)?)s", os.path.basename(path or ""))
    return float(m.group(1)) if m else 0.0


def resolve_frame(frames_dir: str, frame: str) -> str | None:
    """kf_memory may store an absolute path or a basename; find the real file."""
    if frame and os.path.exists(frame):
        return frame
    cand = os.path.join(frames_dir, os.path.basename(frame or ""))
    return cand if os.path.exists(cand) else None


def select_frames(kf, max_frames: int):
    """Pick the highest-value text-bearing frames, deduped in time.

    Rank by length of existing whole-frame OCR (more text already = more to mine
    at finer resolution). Then walk in descending value, skipping any frame within
    1.5s of one already chosen (consecutive frames are near-duplicate scenes).
    """
    cands = []
    for e in kf:
        cap = e.get("caption", "") or ""
        ocr_text = " ".join(e.get("ocr", []) or [])
        if HIGH_VALUE.search(cap) or HIGH_VALUE.search(ocr_text):
            t = e.get("t")
            if t is None:
                t = time_of(e.get("frame", ""))
            cands.append({"t": float(t), "frame": e.get("frame", ""),
                          "ocrlen": len(ocr_text)})
    # most existing text first; stable tie-break by time
    cands.sort(key=lambda c: (-c["ocrlen"], c["t"]))

    chosen = []
    for c in cands:
        if any(abs(c["t"] - k["t"]) <= 1.5 for k in chosen):
            continue
        chosen.append(c)
        if len(chosen) >= max_frames:
            break
    # process in chronological order
    chosen.sort(key=lambda c: c["t"])
    return chosen


def grid_regions(w: int, h: int, rows: int, cols: int):
    """Yield (region_name, (left, top, right, bottom)) for an even rows x cols grid."""
    for r in range(rows):
        for c in range(cols):
            left = (w * c) // cols
            right = (w * (c + 1)) // cols
            top = (h * r) // rows
            bottom = (h * (r + 1)) // rows
            yield f"r{r + 1}c{c + 1}", (left, top, right, bottom)


def ocr(img_path: str, min_conf: float):
    """Apple Vision OCR via ocrmac — same call shape as build_keyframe_memory.py."""
    from ocrmac import ocrmac
    res = ocrmac.OCR(img_path, recognition_level="accurate").recognize()
    return [t.strip() for (t, conf, _box) in res if conf >= min_conf and t.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description="Capture-time micro-detail region OCR")
    ap.add_argument("--frames", required=True, help="dir of *.jpg frames")
    ap.add_argument("--kf", required=True, help="path to kf_memory.json")
    ap.add_argument("--out", required=True, help="output micro_details.json")
    ap.add_argument("--max-frames", type=int, default=12)
    ap.add_argument("--grid", default="3x3", help="rows x cols, e.g. 3x3 or 2x3")
    ap.add_argument("--min-conf", type=float, default=0.3)
    ap.add_argument("--max-dim", type=int, default=1600,
                    help="resize the full frame so its longest side <= this before cropping")
    args = ap.parse_args()

    try:
        rows, cols = (int(x) for x in args.grid.lower().split("x"))
    except Exception:
        print(f"bad --grid {args.grid!r}; expected ROWSxCOLS", file=sys.stderr)
        return 2

    from PIL import Image

    kf = json.load(open(args.kf))
    chosen = select_frames(kf, args.max_frames)
    print(f"{len(kf)} keyframes -> {len(chosen)} high-value frames "
          f"({rows}x{cols}={rows * cols} regions each)", file=sys.stderr, flush=True)

    records = []
    n_frames = n_regions = n_frag = 0
    tmpdir = tempfile.mkdtemp(prefix="micro_")

    for i, c in enumerate(chosen, 1):
        path = resolve_frame(args.frames, c["frame"])
        if not path:
            print(f"  [{i}/{len(chosen)}] MISSING {c['frame']}", file=sys.stderr, flush=True)
            continue
        try:
            im = Image.open(path).convert("RGB")
            w, h = im.size
            s = min(1.0, args.max_dim / max(w, h))
            if s < 1.0:
                im = im.resize((int(w * s), int(h * s)), Image.LANCZOS)
            w, h = im.size

            t0 = time.time()
            frame_regions = frame_frag = 0
            for name, bbox in grid_regions(w, h, rows, cols):
                crop = im.crop(bbox)
                tmp = os.path.join(tmpdir, f"{i}_{name}.jpg")
                crop.save(tmp, quality=92)
                try:
                    lines = ocr(tmp, args.min_conf)
                finally:
                    if os.path.exists(tmp):
                        os.remove(tmp)
                if lines:
                    frame_regions += 1
                    frame_frag += len(lines)
                    records.append({
                        "t": c["t"],
                        "frame": path,
                        "region": name,
                        "bbox": [int(x) for x in bbox],
                        "micro_ocr": lines,
                    })
            n_frames += 1
            n_regions += frame_regions
            n_frag += frame_frag
            dt = time.time() - t0
            print(f"  [{i}/{len(chosen)}] t={c['t']:.1f}s  {frame_regions}/{rows * cols} "
                  f"regions w/ text, {frame_frag} fragments  ({dt:.1f}s)",
                  file=sys.stderr, flush=True)
        except Exception as e:
            print(f"  [{i}/{len(chosen)}] err {path}: {e}", file=sys.stderr, flush=True)
            continue

    try:
        os.rmdir(tmpdir)
    except OSError:
        pass

    records.sort(key=lambda r: (r["t"], r["region"]))
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    json.dump(records, open(args.out, "w"), indent=2, ensure_ascii=False)
    print(f"\nWROTE {len(records)} region records "
          f"({n_frames} frames, {n_regions} non-empty regions, {n_frag} OCR fragments) "
          f"to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
