#!/usr/bin/env python3
"""Extract frames from a video at a fixed time interval using OpenCV (no ffmpeg).
Names match the pipeline convention: frame_<origidx:06d>_<t:.1f>s.jpg, so
build_keyframe_memory.time_of() reads the timestamp straight from the filename.

Usage: python3 scripts/extract_frames.py <video> <out_frames_dir> [--every 0.5]
"""
import argparse, os, sys
import cv2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("out_dir")
    ap.add_argument("--every", type=float, default=0.5, help="seconds between sampled frames")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print("ERROR: could not open", args.video); return 1
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    dur = total / fps if fps else 0
    step = max(1, int(round(fps * args.every)))
    print("video=%s fps=%.2f frames=%d dur=%.1fs -> sampling every %d frames (%.2fs)"
          % (args.video, fps, total, dur, step, args.every), flush=True)

    idx, saved = 0, 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        if idx % step == 0:
            ok, frame = cap.retrieve()
            if ok and frame is not None:
                t = idx / fps
                name = "frame_%06d_%.1fs.jpg" % (idx, t)
                cv2.imwrite(os.path.join(args.out_dir, name), frame,
                            [cv2.IMWRITE_JPEG_QUALITY, 92])
                saved += 1
        idx += 1
    cap.release()
    print("saved %d frames to %s" % (saved, args.out_dir), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
