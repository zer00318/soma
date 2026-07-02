#!/usr/bin/env python3
"""Coordinate-first perception — the architecture the founder specified: the coordinate exists
BEFORE any helper, and every helper INHERITS the coordinate.

Old (wrong) order:   helpers guess labels frame-by-frame  ->  binder guesses which are the same thing
This (right) order:  segment the scene into regions -> give each region a metric 3D COORDINATE
                     -> THEN helpers describe each region, each inheriting that region's coordinate
                     -> fuse per-coordinate  ->  N instances, each a rich multi-helper attribute bundle

Concretely, the 5-nutella example: SAM2 carves the shelf into 5 regions, geometry stamps each with an
(x,y,z)+size, and the colour/label/OCR/size helpers each annotate a specific region and inherit its
coordinate. Individuation is then a PROPERTY OF SPACE (5 regions -> 5 jars), not a label-matching guess.

STAGES (each maps to an on-device analog for the LIVE, frames-never-leave-phone product):
  [GEOMETRY]  DepthPro metric depth (-> CoreML mono-depth on device)
  [SEGMENT ]  SAM2 everything, class-agnostic (-> MobileSAM/EdgeSAM on device)   == the ANCHORS
  [ANCHOR  ]  lift each mask to (x,y,z)+size in metres                            == the COORDINATE
  [HELPERS ]  size / colour / label(CLIP) run per-anchor, each inherits the coordinate
              (-> Vision OCR, CoreML CLIP on device)

This script runs one frame at a time (streaming), mirroring the live path. Cross-frame fusion into
one persistent WORLD map (VGGT poses) is the next module.

    .venv/bin/python scripts/spatial_perceive.py --image <f.jpg> [--json out.json] [--device mps]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np

CLIP_MODEL = "openai/clip-vit-base-patch32"
DEPTH_MODEL = "apple/DepthPro-hf"

# Open vocabulary for the CLIP label helper. CLIP is open-set, so this is only a candidate list; the
# helper picks the best match per region. Extend with --vocab.
LABEL_VOCAB = [
    "suitcase", "backpack", "handbag", "book", "water bottle", "thermos flask", "steel cup",
    "coffee mug", "tennis ball", "laptop", "keyboard", "computer mouse", "monitor", "phone",
    "pillow", "blanket", "towel", "shoe", "jar", "can", "box", "plastic bag", "clothes",
    "chest of drawers", "cabinet", "chair", "door", "wall", "floor", "bed", "plant", "lamp",
    "pen", "glasses", "headphones", "remote control", "charger", "cable",
]
# Labels that are scene surfaces, not countable objects — a region so labelled is dropped.
_SURFACE_LABELS = {"wall", "floor", "bed", "door", "blanket", "surface", "ceiling", "unknown"}


def _is_surface(label: str) -> bool:
    return any(s in label for s in _SURFACE_LABELS)

_COLORS = {
    "black": (30, 30, 30), "white": (235, 235, 235), "grey": (128, 128, 128),
    "red": (200, 40, 40), "green": (40, 150, 60), "blue": (40, 80, 200),
    "yellow": (225, 210, 60), "orange": (230, 140, 40), "brown": (120, 80, 50),
    "silver": (190, 190, 195), "beige": (210, 190, 150),
}


@dataclass
class Anchor:
    """A region of space with a metric coordinate — created BEFORE any helper runs."""
    anchor_id: int
    coordinate_m: tuple[float, float, float]     # (x right, y down, z forward), metres
    size_m: tuple[float, float]                  # metric width, height at the region's depth
    depth_m: float
    box_xyxy: tuple[int, int, int, int]
    area_px: int
    # helper outputs — each is written AFTER the coordinate exists and inherits it
    helpers: dict = field(default_factory=dict)


def _device(pref: str) -> str:
    import torch
    if pref == "cpu":
        return "cpu"
    return "mps" if torch.backends.mps.is_available() else "cpu"


# ---------------------------------------------------------------- GEOMETRY (coordinates first)
def depth_map(image, device: str):
    from transformers import DepthProForDepthEstimation, DepthProImageProcessor
    import torch
    proc = DepthProImageProcessor.from_pretrained(DEPTH_MODEL)
    model = DepthProForDepthEstimation.from_pretrained(DEPTH_MODEL).to(device).eval()
    inputs = proc(images=image, return_tensors="pt").to(device)
    with torch.no_grad():
        out = model(**inputs)
    W, H = image.size
    post = proc.post_process_depth_estimation(out, target_sizes=[(H, W)])[0]
    depth = post["predicted_depth"].detach().float().cpu().numpy()
    focal = None
    for k in ("focallength_px", "focal_length", "focal_length_px"):
        if post.get(k) is not None:
            f = post[k]
            focal = float(f.item()) if hasattr(f, "item") else float(f)
            break
    return depth, focal or 0.85 * max(H, W)


def segment(image_path: str, device: str):
    """SAM2 everything -> class-agnostic masks. These regions ARE the anchors (no labels yet)."""
    from ultralytics import SAM
    sam = SAM("sam2_b.pt")
    res = sam(image_path, device=device, verbose=False)[0]
    if res.masks is None:
        return []
    return [m.astype(bool) for m in res.masks.data.cpu().numpy().astype("uint8")]


def build_anchors(masks, depth, focal, img_wh) -> list[Anchor]:
    """Lift each object-scale mask to a metric 3D coordinate. Background/surface masks are dropped
    here by geometry (too large, or spanning the frame) — before any semantics."""
    W, H = img_wh
    cx, cy = W / 2.0, H / 2.0
    frame_area = H * W
    anchors: list[Anchor] = []
    for mask in masks:
        area = int(mask.sum())
        if area < 500 or area > 0.33 * frame_area:   # noise / background surfaces
            continue
        ys, xs = np.where(mask)
        x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
        # spanning-the-frame masks are walls/floor, not objects
        if (x1 - x0) > 0.92 * W and (y1 - y0) > 0.92 * H:
            continue
        d = depth[ys, xs]
        d = d[np.isfinite(d) & (d > 0)]
        if d.size == 0:
            continue
        z = float(np.median(d))
        u, v = float(xs.mean()), float(ys.mean())
        X, Y = (u - cx) * z / focal, (v - cy) * z / focal
        w_m, h_m = (x1 - x0) * z / focal, (y1 - y0) * z / focal
        anchors.append(Anchor(
            anchor_id=len(anchors),
            coordinate_m=(round(X, 3), round(Y, 3), round(z, 3)),
            size_m=(round(w_m, 3), round(h_m, 3)),
            depth_m=round(z, 3), box_xyxy=(x0, y0, x1, y1), area_px=area,
        ))
    return anchors


# ---------------------------------------------------------------- HELPERS (inherit the coordinate)
def helper_size(anchor: Anchor) -> dict:
    w, h = anchor.size_m
    return {"width_m": w, "height_m": h, "coordinate_m": anchor.coordinate_m}


def helper_colour(anchor: Anchor, mask, rgb) -> dict:
    px = rgb[mask]
    if px.size == 0:
        return {"colour": "unknown", "coordinate_m": anchor.coordinate_m}
    mean = px.reshape(-1, 3).mean(0)
    name = min(_COLORS, key=lambda k: float(np.linalg.norm(mean - np.array(_COLORS[k]))))
    return {"colour": name, "rgb": [int(v) for v in mean], "coordinate_m": anchor.coordinate_m}


def helper_labels_clip(crops, device: str) -> list[str]:
    """CLIP zero-shot label per region crop (fast, but weak on small cluttered crops)."""
    import torch
    from transformers import CLIPModel, CLIPProcessor
    model = CLIPModel.from_pretrained(CLIP_MODEL).to(device).eval()
    proc = CLIPProcessor.from_pretrained(CLIP_MODEL)
    text = proc(text=[f"a photo of a {c}" for c in LABEL_VOCAB], return_tensors="pt", padding=True).to(device)
    with torch.no_grad():
        tfeat = model.get_text_features(**text)
        tfeat = tfeat / tfeat.norm(dim=-1, keepdim=True)
    labels = []
    for crop in crops:
        im = proc(images=crop, return_tensors="pt").to(device)
        with torch.no_grad():
            ifeat = model.get_image_features(**im)
            ifeat = ifeat / ifeat.norm(dim=-1, keepdim=True)
            sim = (ifeat @ tfeat.T).squeeze(0)
        labels.append(LABEL_VOCAB[int(sim.argmax())])
    return labels


def helper_labels_vlm(crops, model_name: str = "gemma3:12b-it-qat") -> list[str]:
    """VLM (local gemma) names each region crop — far stronger than CLIP on cluttered scenes. Each
    label still inherits its anchor's coordinate at the call site. On device this is FastVLM/Qwen-VL."""
    import base64, io, json, urllib.request
    labels = []
    for crop in crops:
        buf = io.BytesIO(); crop.save(buf, format="JPEG"); b64 = base64.b64encode(buf.getvalue()).decode()
        payload = json.dumps({
            "model": model_name,
            "prompt": "Name the single main object in this cropped photo in 1-3 words (a plain noun, "
                      "e.g. 'steel thermos', 'book', 'backpack'). If it is just wall/floor/surface, "
                      "answer 'surface'. Answer with only the noun.",
            "images": [b64], "stream": False,
            "options": {"temperature": 0.0, "num_predict": 12},
        }).encode()
        try:
            req = urllib.request.Request("http://localhost:11434/api/generate", data=payload,
                                         headers={"Content-Type": "application/json"})
            resp = json.loads(urllib.request.urlopen(req, timeout=60).read())
            labels.append(resp.get("response", "").strip().strip(".").lower()[:40] or "unknown")
        except Exception as e:
            labels.append("unknown")
    return labels


def perceive(image_path: str, device: str, labeler: str = "vlm") -> list[Anchor]:
    from PIL import Image
    img = Image.open(image_path).convert("RGB")
    rgb = np.asarray(img)
    W, H = img.size

    # STAGE 1+2: coordinates FIRST (geometry + segmentation), no labels yet
    depth, focal = depth_map(img, device)
    masks = segment(image_path, device)
    print(f"  geometry: depth [{np.nanmin(depth):.2f},{np.nanmax(depth):.2f}]m focal={focal:.0f}px | "
          f"SAM2 {len(masks)} masks", file=sys.stderr)
    anchors = build_anchors(masks, depth, focal, (W, H))
    # keep the mask per surviving anchor (re-derive by box for helpers)
    kept_masks = []
    for a in anchors:
        x0, y0, x1, y1 = a.box_xyxy
        m = np.zeros((H, W), bool); m[y0:y1 + 1, x0:x1 + 1] = True
        kept_masks.append(m)
    print(f"  anchors: {len(anchors)} object-scale regions with coordinates (before any helper)",
          file=sys.stderr)

    # STAGE 3: helpers, each INHERITS the anchor coordinate
    crops = [img.crop(a.box_xyxy) for a in anchors]
    if not anchors:
        labels = []
    elif labeler == "clip":
        labels = helper_labels_clip(crops, device)
    else:
        labels = helper_labels_vlm(crops)
    out = []
    for a, m, lab in zip(anchors, kept_masks, labels):
        a.helpers["size"] = helper_size(a)
        a.helpers["colour"] = helper_colour(a, m, rgb)
        a.helpers["label"] = {"label": lab, "coordinate_m": a.coordinate_m}
        if _is_surface(lab):            # a region the label helper calls a surface is not an object
            continue
        out.append(a)
    for i, a in enumerate(out):
        a.anchor_id = i
    out.sort(key=lambda a: a.depth_m)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--device", default="mps")
    ap.add_argument("--labeler", default="vlm", choices=["vlm", "clip"])
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    device = _device(args.device)
    t0 = time.time()
    anchors = perceive(args.image, device, args.labeler)
    dt = time.time() - t0

    print(f"\n=== {len(anchors)} object anchors from {Path(args.image).name} ({dt:.1f}s, {device}) ===")
    print(f"{'label':16} {'colour':7} {'depth':>6} {'coordinate (x,y,z) m':>22} {'size w×h m':>12}")
    from collections import Counter
    counts = Counter()
    for a in anchors:
        lab = a.helpers["label"]["label"]; col = a.helpers["colour"]["colour"]
        counts[lab] += 1
        c = a.coordinate_m
        print(f"{lab:16} {col:7} {a.depth_m:6.2f} ({c[0]:+.2f},{c[1]:+.2f},{c[2]:.2f})".ljust(54)
              + f"{a.size_m[0]:.2f}×{a.size_m[1]:.2f}")
    print("\n=== counts (individuation = distinct spatial regions) ===")
    for lab, n in counts.most_common():
        print(f"  {n:2d}  {lab}")

    if args.json:
        Path(args.json).write_text(json.dumps([asdict(a) for a in anchors], indent=2))
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
