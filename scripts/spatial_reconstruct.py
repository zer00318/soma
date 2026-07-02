#!/usr/bin/env python3
"""Coordinate-first object reconstruction — the substrate the counting product was missing.

The failed approach individuated objects by ``track_id`` (temporal identity), which fragments the
instant an object leaves frame: one keyboard -> 12 tracks -> "12 keyboards". This script replaces
that guess with GEOMETRY. For a single RGB frame it produces, per object, a metric 3D position and
size in the camera frame — no ARKit, no VIO, no LiDAR:

    [DETECT ]  YOLO-World (open vocabulary)  -> labeled object boxes
    [DEPTH  ]  Apple DepthPro (in transformers) -> per-pixel METRIC depth + focal length (px)
    [LIFT   ]  back-project each box's robust-median depth -> object (x,y,z) in metres + size

The output is the anchor the helpers and binder were always missing: an object is a *volume at a
location*, not a label that happened to appear. Multi-view fusion into ONE world frame (VGGT) is the
next increment — this one proves the substrate on a single frame first.

    .venv/bin/python scripts/spatial_reconstruct.py --image <path.jpg> [--json out.json]
    .venv/bin/python scripts/spatial_reconstruct.py --image <path.jpg> --vocab "suitcase,backpack,bottle,bed,tennis ball,door,chest of drawers"
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np

# A default open-vocabulary lexicon for a lived-in room/desk. YOLO-World is open-vocab, so this is
# just a prior — extend it per scene with --vocab. Kept concrete (physical nouns) on purpose.
DEFAULT_VOCAB = [
    "suitcase", "backpack", "handbag", "bag", "bottle", "water bottle", "cup", "mug",
    "bed", "pillow", "blanket", "tennis ball", "ball", "door", "chest of drawers", "dresser",
    "cabinet", "laptop", "keyboard", "mouse", "monitor", "book", "chair", "person", "phone",
    "shoe", "clothes", "towel", "box", "plastic bag", "can", "remote",
]

DEPTH_MODEL = "apple/DepthPro-hf"


@dataclass
class Detected:
    label: str
    confidence: float
    box_xyxy: tuple[float, float, float, float]
    depth_m: float          # robust median metric depth of the object
    position_m: tuple[float, float, float]  # (x right, y down, z forward) in camera frame, metres
    size_m: tuple[float, float]             # (width, height) in metres at the object's depth


def _device() -> str:
    import torch
    return "mps" if torch.backends.mps.is_available() else "cpu"


def load_depth(device: str):
    """DepthPro = zero-shot METRIC depth + focal length from one image, no intrinsics needed."""
    from transformers import DepthProForDepthEstimation, DepthProImageProcessor
    proc = DepthProImageProcessor.from_pretrained(DEPTH_MODEL)
    model = DepthProForDepthEstimation.from_pretrained(DEPTH_MODEL).to(device).eval()
    return proc, model


def run_depth(proc, model, image, device: str) -> tuple[np.ndarray, float]:
    """Return (metric_depth[H,W] in metres, focal_length_px). Defensive about key names."""
    import torch
    inputs = proc(images=image, return_tensors="pt").to(device)
    with torch.no_grad():
        out = model(**inputs)
    W, H = image.size
    post = proc.post_process_depth_estimation(out, target_sizes=[(H, W)])[0]
    depth = post.get("predicted_depth")
    depth = depth.detach().float().cpu().numpy()
    # focal length key varies across transformers versions
    focal = None
    for k in ("focallength_px", "focal_length", "focal_length_px"):
        if k in post and post[k] is not None:
            f = post[k]
            focal = float(f.item()) if hasattr(f, "item") else float(f)
            break
    if focal is None:  # fall back to a ~60deg-HFOV prior so the pipeline still runs
        focal = 0.85 * max(H, W)
    return depth, focal


def detect(image_path: str, vocab: list[str], conf: float):
    from ultralytics import YOLOWorld
    model = YOLOWorld("yolov8s-world.pt")
    model.set_classes(vocab)
    res = model.predict(image_path, conf=conf, iou=0.5, verbose=False)[0]
    dets = []
    for b in res.boxes:
        cls = int(b.cls.item())
        dets.append((vocab[cls] if cls < len(vocab) else str(cls),
                     float(b.conf.item()),
                     tuple(float(v) for v in b.xyxy[0].tolist())))
    return dets


def lift(box, depth: np.ndarray, focal: float) -> tuple[float, list[float], list[float]]:
    """Back-project a detection box to a metric 3D position + size.

    Depth is sampled from the CENTRAL 50% of the box (rejects background/wall bleeding in at the
    edges) with a median (rejects specular/edge outliers). Pinhole: X=(u-cx)Z/f, size=box_px*Z/f."""
    H, W = depth.shape
    x0, y0, x1, y1 = box
    cx, cy = W / 2.0, H / 2.0
    # central crop for a clean depth sample
    mx, my = (x1 - x0) * 0.25, (y1 - y0) * 0.25
    ix0, iy0 = int(max(0, x0 + mx)), int(max(0, y0 + my))
    ix1, iy1 = int(min(W, x1 - mx)), int(min(H, y1 - my))
    patch = depth[iy0:iy1, ix0:ix1]
    patch = patch[np.isfinite(patch) & (patch > 0)]
    if patch.size == 0:
        return 0.0, [0, 0, 0], [0, 0]
    z = float(np.median(patch))
    u, v = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    X = (u - cx) * z / focal
    Y = (v - cy) * z / focal
    width_m = (x1 - x0) * z / focal
    height_m = (y1 - y0) * z / focal
    return z, [round(X, 3), round(Y, 3), round(z, 3)], [round(width_m, 3), round(height_m, 3)]


# Open-vocab labels that name the same physical thing collapse to one identity, so a dresser tagged
# both "cabinet" and "chest of drawers" is not counted twice.
_SYNONYMS = {
    "cabinet": "dresser", "chest of drawers": "dresser", "dresser": "dresser",
    "handbag": "bag", "backpack": "bag", "bag": "bag",
    "water bottle": "bottle", "bottle": "bottle", "can": "bottle",
    "cup": "cup", "mug": "cup", "ball": "ball", "tennis ball": "ball",
}


def _canon(label: str) -> str:
    return _SYNONYMS.get(label, label)


def _iou(a, b) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0, ix1, iy1 = max(ax0, bx0), max(ay0, by0), min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = (ax1 - ax0) * (ay1 - ay0)
    area_b = (bx1 - bx0) * (by1 - by0)
    return inter / (area_a + area_b - inter)


def fuse(objs: list[Detected], min_conf: float) -> list[Detected]:
    """Collapse redundant detections of the SAME physical object using the coordinate anchor.

    Two detections are the same instance when their 2D boxes overlap heavily OR their 3D centroids
    sit within one object-radius (~0.2 m) — the merge criterion the old track_id path never had. We
    keep the highest-confidence detection per cluster. This is what turns "6 handbags" into 1 bag."""
    kept = [o for o in objs if o.confidence >= min_conf]
    kept.sort(key=lambda o: -o.confidence)
    clusters: list[Detected] = []
    for o in kept:
        merged = False
        for i, c in enumerate(clusters):
            same_region_2d = _iou(o.box_xyxy, c.box_xyxy) > 0.45
            close_3d = (abs(o.position_m[0] - c.position_m[0]) < 0.2
                        and abs(o.position_m[2] - c.position_m[2]) < 0.25)
            if same_region_2d or (close_3d and _canon(o.label) == _canon(c.label)):
                merged = True  # c already has >= confidence (sorted); drop o
                break
        if not merged:
            clusters.append(o)
    return clusters


def reconstruct(image_path: str, vocab: list[str], conf: float, min_conf: float = 0.15) -> list[Detected]:
    from PIL import Image
    device = _device()
    image = Image.open(image_path).convert("RGB")
    proc, model = load_depth(device)
    depth, focal = run_depth(proc, model, image, device)
    print(f"  depth: {depth.shape} range [{np.nanmin(depth):.2f}, {np.nanmax(depth):.2f}] m  "
          f"focal={focal:.1f}px  device={device}", file=sys.stderr)
    dets = detect(image_path, vocab, conf)
    out = []
    for label, c, box in dets:
        z, pos, size = lift(box, depth, focal)
        if z <= 0:
            continue
        out.append(Detected(label, round(c, 3), tuple(round(v, 1) for v in box), round(z, 3), tuple(pos), tuple(size)))
    fused = fuse(out, min_conf)
    fused.sort(key=lambda d: d.depth_m)
    print(f"  detections: {len(out)} raw -> {len(fused)} after 3D-region fusion (min_conf={min_conf})",
          file=sys.stderr)
    return fused


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--vocab", default=None, help="comma-separated open-vocab classes")
    ap.add_argument("--conf", type=float, default=0.03, help="raw detector confidence floor")
    ap.add_argument("--min-conf", type=float, default=0.15, help="keep-after-fusion confidence floor")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    vocab = [v.strip() for v in args.vocab.split(",")] if args.vocab else DEFAULT_VOCAB
    t0 = time.time()
    objs = reconstruct(args.image, vocab, args.conf, args.min_conf)
    dt = time.time() - t0

    print(f"\n=== {len(objs)} objects reconstructed from {Path(args.image).name}  ({dt:.1f}s) ===")
    print(f"{'label':16} {'conf':>5} {'depth_m':>8}  {'position (x,y,z) m':>22}  {'size w×h m':>14}")
    from collections import Counter
    counts = Counter()
    for o in objs:
        o.label = _canon(o.label)  # show the physical identity, not the open-vocab synonym
        counts[o.label] += 1
        px = f"({o.position_m[0]:+.2f},{o.position_m[1]:+.2f},{o.position_m[2]:.2f})"
        sz = f"{o.size_m[0]:.2f}×{o.size_m[1]:.2f}"
        print(f"{o.label:16} {o.confidence:5.2f} {o.depth_m:8.2f}  {px:>22}  {sz:>14}")
    print("\n=== counts ===")
    for label, n in counts.most_common():
        print(f"  {n:2d}  {label}")

    if args.json:
        Path(args.json).write_text(json.dumps([asdict(o) for o in objs], indent=2))
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
