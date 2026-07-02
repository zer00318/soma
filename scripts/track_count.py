#!/usr/bin/env python
"""ARKit-free instance counting via VIDEO OBJECT TRACKING.

Instead of world coordinates (which needed 6-DOF ARKit that never tracked), we track each object
through the video by appearance. A persistent track ID = one physical object. Count distinct
tracks per label -> the count. This needs no pose, no depth, no ARKit — just the .mov.

Open-vocab (YOLO-World) so we can track "nutella jar", not only COCO "bottle".

    .venv/bin/python scripts/track_count.py <video.mov> [--stride 5] [--conf 0.25]
"""
from __future__ import annotations
import argparse, collections, sys

CLASSES = ["nutella jar", "pesto jar", "glasses", "eyeglasses", "electric fan", "laptop",
           "water bottle", "cup", "book", "power adapter", "jar"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--stride", type=int, default=6, help="sample every Nth frame")
    ap.add_argument("--conf", type=float, default=0.25)
    args = ap.parse_args()

    from ultralytics import YOLOWorld
    model = YOLOWorld("yolov8s-world.pt")   # auto-downloads once
    model.set_classes(CLASSES)

    # track IDs seen per class + how many frames each (class,id) persisted (consensus strength)
    seen: dict[str, set] = collections.defaultdict(set)
    persistence: dict[tuple, int] = collections.Counter()
    frames = 0
    for r in model.track(source=args.video, stream=True, persist=True, conf=args.conf,
                         vid_stride=args.stride, tracker="bytetrack.yaml", verbose=False):
        frames += 1
        if r.boxes is None or r.boxes.id is None:
            continue
        ids = r.boxes.id.int().tolist()
        clss = r.boxes.cls.int().tolist()
        for tid, ci in zip(ids, clss):
            label = CLASSES[ci]
            seen[label].add(tid)
            persistence[(label, tid)] += 1

    print(f"\nprocessed {frames} sampled frames (stride={args.stride})\n" + "="*60)
    print("DISTINCT TRACKS per label  (= physical object count, no ARKit):")
    for label in sorted(seen, key=lambda l: -len(seen[l])):
        # consensus filter: a real object persists across several frames; a one-off blip does not
        solid = [tid for tid in seen[label] if persistence[(label, tid)] >= 3]
        if not seen[label]:
            continue
        print(f"  {label:16} raw_tracks={len(seen[label]):2}  solid(>=3 frames)={len(solid)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
