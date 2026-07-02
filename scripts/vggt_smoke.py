#!/usr/bin/env python3
"""Smoke test: does VGGT-1B run on this M2 (MPS) and produce sane multi-frame world points?

This is the make-or-break for the persistence increment. VGGT is a 1B transformer written for CUDA
bf16; we need it to load and run on MPS (fp32/fp16) and return world_points in ONE shared frame.

    .venv/bin/python scripts/vggt_smoke.py frameA.jpg frameB.jpg frameC.jpg
"""
import sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "vendor" / "vggt"))

import numpy as np
import torch
from vggt.models.vggt import VGGT
from vggt.utils.load_fn import load_and_preprocess_images


def main():
    paths = sys.argv[1:]
    if len(paths) < 2:
        print("need >=2 image paths"); return 1
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"device={dev}  frames={len(paths)}")

    t0 = time.time()
    model = VGGT.from_pretrained("facebook/VGGT-1B").to(dev).eval()
    print(f"loaded VGGT-1B in {time.time()-t0:.1f}s")

    images = load_and_preprocess_images(paths).to(dev)
    print(f"images tensor: {tuple(images.shape)}")

    t1 = time.time()
    with torch.no_grad():
        # MPS has no bf16 autocast; run fp32 for correctness first
        pred = model(images)
    print(f"inference: {time.time()-t1:.1f}s")

    for k in ("depth", "world_points", "world_points_conf", "pose_enc"):
        v = pred.get(k)
        if v is None:
            print(f"  {k}: MISSING"); continue
        v = v.detach().float().cpu().numpy()
        print(f"  {k}: shape={v.shape}")
    wp = pred["world_points"].detach().float().cpu().numpy()  # [B,S,H,W,3]
    finite = np.isfinite(wp)
    print(f"  world_points finite frac: {finite.mean():.3f}  "
          f"range x[{np.nanmin(wp[...,0]):.2f},{np.nanmax(wp[...,0]):.2f}] "
          f"z[{np.nanmin(wp[...,2]):.2f},{np.nanmax(wp[...,2]):.2f}]")
    # Sanity: do the per-frame world maps overlap (shared frame) rather than diverge?
    S = wp.shape[1]
    centroids = [np.nanmedian(wp[0, s].reshape(-1, 3), axis=0) for s in range(S)]
    print("  per-frame scene centroids (should be close if in ONE world frame):")
    for s, c in enumerate(centroids):
        print(f"    frame{s}: ({c[0]:+.2f},{c[1]:+.2f},{c[2]:+.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
