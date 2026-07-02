#!/usr/bin/env python3
"""Select the N sharpest, time-diverse keyframes from a dense capture dir.

Dense capture (hundreds of frames) is a POOL, not the work-list: perceiving every frame
through the heavy binder is infeasible (~3 min/frame). We bucket the frames across the
recording timeline and keep the single sharpest frame per bucket (Laplacian variance),
copying its jpg + .depth.json + .pose.json. Result: full temporal/viewpoint coverage at
a fraction of the perception cost.

    .venv/bin/python scripts/select_keyframes.py <src_dir> <out_dir> [--n 40]
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def main() -> int:
    import cv2

    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=40)
    args = ap.parse_args()

    src = Path(args.src)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    frames = sorted(src.glob("*.jpg"), key=lambda p: float(p.stem))
    if not frames:
        print("no frames")
        return 1

    # sharpness per frame
    scored = []
    for fp in frames:
        img = cv2.imread(str(fp))
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        scored.append((fp, cv2.Laplacian(gray, cv2.CV_64F).var()))
    if not scored:
        print("no readable frames")
        return 1

    # bucket across the timeline, keep the sharpest per bucket
    n = min(args.n, len(scored))
    bucket = max(1, len(scored) // n)
    kept = []
    for i in range(0, len(scored), bucket):
        window = scored[i:i + bucket]
        best = max(window, key=lambda x: x[1])
        kept.append(best)
    kept = kept[:n]

    for idx, (fp, sharp) in enumerate(kept):
        stem = f"{idx:06d}"
        shutil.copy2(fp, out / f"{stem}.jpg")
        for suffix in (".depth.json", ".pose.json"):
            sib = fp.with_suffix(suffix)
            if sib.exists():
                shutil.copy2(sib, out / f"{stem}{suffix}")
    sharps = [round(s, 0) for _, s in kept]
    print(f"selected {len(kept)} keyframes from {len(scored)} (bucket={bucket}) -> {out}")
    print(f"sharpness range: min={min(sharps)} max={max(sharps)} median={sorted(sharps)[len(sharps)//2]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
