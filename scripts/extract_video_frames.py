#!/usr/bin/env python
"""Extract frames from a .mov via cv2 (no ffmpeg dependency)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("out_dir")
    ap.add_argument("--fps", type=float, default=4.0, help="frames per second to extract")
    args = ap.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"could not open {args.video}", file=sys.stderr)
        return 1
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    step = max(1, round(src_fps / args.fps))
    print(f"source fps={src_fps:.1f} total_frames={total} step={step} -> ~{total // step} extracted")

    idx = written = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % step == 0:
            cv2.imwrite(str(out / f"{written:06d}.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
            written += 1
        idx += 1
    cap.release()
    print(f"wrote {written} frames to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
