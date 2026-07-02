#!/usr/bin/env python
"""Appearance-based instance individuation (ARKit-free, tracking-free).

The founder's architecture, done via VISUAL RE-ID instead of coordinates: embed each detected
crop of a label, cluster by appearance. Two views of the SAME physical jar embed close (merge);
two DIFFERENT jars embed apart (separate). Distinct clusters = the count. Robust to the camera
motion that broke coordinates (drift) and tracking (fragmentation).

    .venv/bin/python scripts/individuate_appearance.py <store.sqlite3> <capture_dir> <label> [--thr 0.12]
"""
from __future__ import annotations
import argparse, json, sys, glob
import numpy as np
from PIL import Image


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("store"); ap.add_argument("capture"); ap.add_argument("label")
    ap.add_argument("--thr", type=float, default=0.12, help="cosine-distance merge threshold")
    args = ap.parse_args()

    import sqlite3, torch, clip
    device = "cpu"
    model, preprocess = clip.load("ViT-B/32", device=device)

    c = sqlite3.connect(args.store)
    rows = list(c.execute(
        "SELECT provenance_json FROM memory_nodes WHERE node_type='observation' "
        "AND provenance_json LIKE '%crop_zoom%' AND lower(text) LIKE ?",
        ('%' + args.label.lower() + '%',)))
    embs, meta = [], []
    for (pj,) in rows:
        p = json.loads(pj); box = p.get("box"); frame = p.get("frame")
        if not box or not frame:
            continue
        fp = f"{args.capture}/{frame}"
        if not glob.glob(fp):
            continue
        im = Image.open(fp).convert("RGB")
        x0, y0, x1, y1 = [int(v) for v in box]
        crop = im.crop((x0, y0, x1, y1))
        with torch.no_grad():
            e = model.encode_image(preprocess(crop).unsqueeze(0).to(device))[0].cpu().numpy()
        embs.append(e / (np.linalg.norm(e) + 1e-8)); meta.append(frame)

    print(f"{len(embs)} '{args.label}' crops embedded")
    if not embs:
        return 0
    # greedy agglomerative: a crop joins an existing instance if cosine-distance < thr to its mean
    instances: list[dict] = []
    for e, fr in zip(embs, meta):
        best, bestd = None, 1e9
        for inst in instances:
            d = 1 - float(np.dot(e, inst["mean"]))
            if d < bestd:
                bestd, best = d, inst
        if best is not None and bestd < args.thr:
            best["embs"].append(e); best["frames"].append(fr)
            best["mean"] = np.mean(best["embs"], axis=0); best["mean"] /= np.linalg.norm(best["mean"]) + 1e-8
        else:
            instances.append({"embs": [e], "frames": [fr], "mean": e})
    print(f"\nDISTINCT PHYSICAL INSTANCES (appearance clusters, thr={args.thr}): {len(instances)}")
    for i, inst in enumerate(instances, 1):
        print(f"  instance {i}: seen in {len(inst['embs'])} crops (frames {sorted(set(inst['frames']))[:6]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
