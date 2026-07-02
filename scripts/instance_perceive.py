#!/usr/bin/env python3
"""Instance-grounded perception (Mac-side, high-res).

The bar-mover: instead of asking one VLM to describe a whole low-res frame, we
1. SEGMENT every instance with SAM2 (class-agnostic -> max coverage, incl. the
   unnamed long tail),
2. CROP each instance so it FILLS a strong VLM's input (fine print becomes legible),
3. READ each crop in parallel for {label, text, colour, material, state, orientation},
4. emit instances with image-space boxes (the Cartesian substrate; world-anchoring via
   ARKit is layered on later).

Counting/relations are NOT done here — instances are described, not counted. The binder
assembles the graph and the LLM derives counts/relations downstream.

Privacy: frame + crops are processed in memory and never persisted by this module; only
the derived instance text/boxes are returned.

    .venv/bin/python scripts/instance_perceive.py <image> [--max-instances 12] [--json out.json]
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

OLLAMA = "http://127.0.0.1:11434"
# Per-crop reader. 12b is ~2-3x faster than 27b so the live perception worker can
# keep up with the frame stream (27b at ~12 crops/frame was ~3 min/frame -> only a
# couple frames perceived per capture). Override with TRACE_ATTR_MODEL if needed.
ATTR_MODEL = os.environ.get("TRACE_ATTR_MODEL", "gemma3:12b-it-qat")
_GROUNDING_CACHE = (
    Path.home()
    / ".cache"
    / "huggingface"
    / "hub"
    / "models--IDEA-Research--grounding-dino-tiny"
    / "snapshots"
)

# Open-vocab detector classes. Broad everyday inventory for the demo domains
# (products, electronics, personal items, furniture). Extend freely — Grounding-DINO
# is open-vocabulary, this is just the recall net of what to look for.
GROUNDING_CLASSES = [
    "jar", "bottle", "can", "box", "bag", "cup", "mug", "glass", "bowl", "plate",
    "spoon", "fork", "knife", "laptop", "phone", "tablet", "monitor", "keyboard",
    "charger", "cable", "headphones", "book", "notebook", "pen", "ring", "watch",
    "glasses", "wallet", "key", "shoe", "hat", "backpack", "chair", "lamp", "plant",
    "remote", "camera", "speaker", "clock", "snack packet", "tube", "container",
    "pillow", "blanket",
    # Added 2026-06-30: objects the founder's questions actually ask about but the detector
    # was never told to look for (crop-zoom captured 0 of these before).
    "microphone", "tape", "tape roll", "diary", "fan", "thermos", "flask", "water bottle",
    "suitcase", "mattress", "towel", "shirt", "cloth", "duvet", "power bank", "adapter",
]

_GD = {"proc": None, "model": None, "device": None}

INSTANCE_PROMPT = (
    "This is a tight crop of ONE object from a person's camera. "
    "Identify the PRODUCT or object itself, not stickers or promo slogans on it.\n"
    "Respond in compact lines:\n"
    "NAME: <what this product/object IS — its common product name or brand if you "
    "recognise it (e.g. 'Nutella', 'Pringles', 'MacBook'), even if a promotional "
    "sticker or contest text is more prominent. Generic noun if unknown.>\n"
    "TEXT: <the MAIN brand/product name printed on it, verbatim; ignore promo "
    "slogans, prize/contest text, and stickers; else NONE>\n"
    "COLOUR: <main colours>\n"
    "MATERIAL: <glass/plastic/metal/fabric/paper/wood/unknown>\n"
    "STATE: <open/closed/empty/full/on/off/unknown>\n"
    "ORIENT: <upright/on-its-side/tilted/unknown>\n"
    "Only what is visible in THIS crop. Do not guess attributes you cannot see."
)


def _gen(prompt: str, img: bytes, timeout: int = 180) -> str:
    b64 = base64.b64encode(img).decode()
    body = {"model": ATTR_MODEL, "prompt": prompt, "images": [b64],
            "stream": False, "options": {"temperature": 0}}
    req = urllib.request.Request(f"{OLLAMA}/api/generate",
                                 data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))["response"].strip()


def _jpeg(im: Image.Image, max_side: int = 768, q: int = 92) -> bytes:
    im = im.convert("RGB")
    im.thumbnail((max_side, max_side))
    b = io.BytesIO()
    im.save(b, format="JPEG", quality=q)
    return b.getvalue()


def _resolve_grounding_model(default_model: str) -> str:
    configured = os.environ.get("TRACE_GROUNDING_DINO_MODEL")
    if configured:
        return configured
    if _GROUNDING_CACHE.exists():
        snapshots = sorted(path for path in _GROUNDING_CACHE.iterdir() if path.is_dir())
        if snapshots:
            return str(snapshots[-1])
    return default_model


def _load_gd(model_id: str = "IDEA-Research/grounding-dino-tiny"):
    if _GD["model"] is None:
        import torch
        from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
        resolved_model = _resolve_grounding_model(model_id)
        local_only = Path(resolved_model).exists()
        requested_device = os.environ.get("TRACE_GROUNDING_DINO_DEVICE", "").strip().lower()
        if requested_device:
            dev = requested_device
        else:
            # The founder already validated that the MPS path asserts on this box.
            # Default to CPU for reliability; opt back into MPS explicitly.
            dev = "cpu"
            if not local_only and torch.backends.mps.is_available():
                dev = "cpu"
        if local_only:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        _GD["proc"] = AutoProcessor.from_pretrained(
            resolved_model,
            local_files_only=local_only,
        )
        try:
            _GD["model"] = AutoModelForZeroShotObjectDetection.from_pretrained(
                resolved_model,
                local_files_only=local_only,
            ).to(dev)
            _GD["device"] = dev
        except Exception:
            _GD["model"] = AutoModelForZeroShotObjectDetection.from_pretrained(
                resolved_model,
                local_files_only=local_only,
            ).to("cpu")
            _GD["device"] = "cpu"
    return _GD["proc"], _GD["model"], _GD["device"]


def segment_instances(image_path: str, max_instances: int = 12,
                      box_thr: float = 0.35, text_thr: float = 0.27) -> list[dict]:
    """Open-vocab DETECTOR (Grounding-DINO) -> clean object boxes with class labels.
    Falls back to SAM2-everything, then a grid, so the pipeline always runs."""
    im = Image.open(image_path).convert("RGB")
    W, H = im.size
    labeled: list[tuple[tuple[int, int, int, int], str, float]] = []
    try:
        import torch
        proc, model, dev = _load_gd()
        prompt = ". ".join(GROUNDING_CLASSES) + "."
        inputs = proc(images=im, text=prompt, return_tensors="pt").to(dev)
        with torch.no_grad():
            outputs = model(**inputs)
        res = proc.post_process_grounded_object_detection(
            outputs, inputs.input_ids, box_threshold=box_thr,
            text_threshold=text_thr, target_sizes=[im.size[::-1]])[0]
        for box, score, label in zip(res["boxes"].tolist(), res["scores"].tolist(),
                                     res["labels"]):
            x0, y0, x1, y1 = (int(v) for v in box)
            labeled.append(((x0, y0, x1, y1), str(label), float(score)))
    except Exception as e:
        print(f"[instance_perceive] Grounding-DINO unavailable ({e}); grid fallback",
              file=sys.stderr)
        gx, gy = 3, 3
        for j in range(gy):
            for i in range(gx):
                labeled.append(((i * W // gx, j * H // gy,
                                 (i + 1) * W // gx, (j + 1) * H // gy), "region", 0.0))

    # drop degenerate boxes, de-dup overlaps (keep highest score), cap
    clean = []
    for (x0, y0, x1, y1), lab, sc in labeled:
        bx = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        if abs(bx[2] - bx[0]) > 12 and abs(bx[3] - bx[1]) > 12:
            clean.append((bx, lab, sc))
    clean.sort(key=lambda t: t[2], reverse=True)
    kept: list[tuple] = []
    for bx, lab, sc in clean:
        if all(_iou(bx, k[0]) < 0.6 for k in kept):
            kept.append((bx, lab, sc))

    # Containment suppression: drop a box that is mostly inside a >=2x larger box.
    # The open-vocab detector finds an object AND its parts (a laptop's keyboard,
    # screen, trackpad), turning ONE physical object into many instances and
    # poisoning counts. The parts are contained in the whole, so keep the whole.
    survivors = []
    for i, (bx, lab, sc) in enumerate(kept):
        area = max(1, (bx[2] - bx[0]) * (bx[3] - bx[1]))
        swallowed = False
        for j, (kbx, klab, ksc) in enumerate(kept):
            if i == j:
                continue
            karea = (kbx[2] - kbx[0]) * (kbx[3] - kbx[1])
            if karea >= 2.0 * area and _containment(bx, kbx) >= 0.80:
                swallowed = True
                break
        if not swallowed:
            survivors.append((bx, lab, sc))
    kept = survivors[:max_instances]
    return [{"box": list(bx), "det_label": lab, "det_score": round(sc, 2),
             "img_wh": [W, H]} for bx, lab, sc in kept]


def _containment(a, b) -> float:
    """Fraction of box a's area that lies inside box b."""
    x0 = max(a[0], b[0]); y0 = max(a[1], b[1])
    x1 = min(a[2], b[2]); y1 = min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    return inter / area_a if area_a else 0.0


def _iou(a, b) -> float:
    x0 = max(a[0], b[0]); y0 = max(a[1], b[1])
    x1 = min(a[2], b[2]); y1 = min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua else 0.0


def _nms(boxes, thr: float = 0.7):
    kept = []
    for b in sorted(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True):
        if all(_iou(b, k) < thr for k in kept):
            kept.append(b)
    return kept


def read_instance(image_path: str, box: list[int]) -> dict:
    im = Image.open(image_path).convert("RGB")
    W, H = im.size
    x0, y0, x1, y1 = box
    x0, x1 = sorted((max(0, min(x0, W)), max(0, min(x1, W))))
    y0, y1 = sorted((max(0, min(y0, H)), max(0, min(y1, H))))
    pad_x = int((x1 - x0) * 0.08); pad_y = int((y1 - y0) * 0.08)
    left = max(0, x0 - pad_x); upper = max(0, y0 - pad_y)
    right = min(W, x1 + pad_x); lower = min(H, y1 + pad_y)
    if right - left < 8 or lower - upper < 8:
        return {"name": "", "text": "", "colour": "", "material": "", "state": "",
                "orient": "", "_raw": "degenerate-box"}
    crop = im.crop((left, upper, right, lower))
    raw = _gen(INSTANCE_PROMPT, _jpeg(crop))
    return _parse_attrs(raw)


def _parse_attrs(raw: str) -> dict:
    out = {"name": "", "text": "", "colour": "", "material": "", "state": "", "orient": ""}
    key_map = {"NAME": "name", "TEXT": "text", "COLOUR": "colour", "COLOR": "colour",
               "MATERIAL": "material", "STATE": "state", "ORIENT": "orient"}
    for line in raw.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            kk = key_map.get(k.strip().upper())
            if kk:
                out[kk] = v.strip()
    out["_raw"] = raw[:300]
    return out


def perceive(image_path: str, max_instances: int = 12, workers: int = 3) -> list[dict]:
    instances = segment_instances(image_path, max_instances)
    def work(inst):
        attrs = read_instance(image_path, inst["box"])
        return {**inst, **attrs}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(work, instances))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--max-instances", type=int, default=12)
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    insts = perceive(args.image, args.max_instances)
    print(f"\n=== {len(insts)} instances in {Path(args.image).name} ===\n")
    for i, x in enumerate(insts):
        txt = f' text="{x["text"]}"' if x.get("text") and x["text"].upper() != "NONE" else ""
        det = f"({x.get('det_label','?')} {x.get('det_score','')})"
        print(f"[{i:2}] {det:<22} {x.get('name','?'):<30} {x.get('colour',''):<14} "
              f"{x.get('state','')}{txt}  box={x['box']}")
    if args.json:
        Path(args.json).write_text(json.dumps(insts, ensure_ascii=False, indent=2))
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
