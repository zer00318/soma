#!/usr/bin/env python3
"""Offline DENSE perception over a saved video — the physical-pillar capture path.

The live phone pipeline drops backlog and perceives only ~0.44 fps (gemma is the
bottleneck), so a multi-minute session yields ~5 perceived frames. The fix the
founder ordered is foundation-up: SAVE the full video, then perceive it OFFLINE at
whatever density we want, free of the real-time drop. This script is that offline
perceiver — and the template that will consume the phone's uploaded .mov once the
on-device recorder is fixed.

MOAT DISCIPLINE: no raw frame is ever written to disk. Each sampled frame is decoded
in memory, JPEG-encoded in memory, base64'd straight to the local gemma vision model,
and discarded. Only the derived TEXT persists, into the same TraceMemoryStore the
brain reads. "No raw video frame is ever stored or egressed" holds by construction.

    .venv/bin/python scripts/video_perceive.py data/walks/IMG_4045.MOV \
        --interval 2.0 --store data/trace_store.sqlite3 --max 40
"""
from __future__ import annotations

import argparse
import base64
import sys
import time
from pathlib import Path

import cv2  # type: ignore

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from mac_vision_perceive import perceive_frame_b64  # noqa: E402  gemma vision (in-memory)
from trace_memory.store import TraceMemoryStore  # noqa: E402


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _sharpness(frame_bgr) -> float:
    """Laplacian variance — low = motion-blur/defocus. Same gate idea as the live
    blur gate, computed in memory (no temp file)."""
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def perceive_video(
    video: str,
    store_path: str,
    interval_s: float,
    sharp_min: float,
    max_frames: int,
    base_t_ms: int | None,
) -> int:
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        _log(f"cannot open {video}")
        return 1
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = total / fps if fps else 0.0
    stride = max(1, int(round(interval_s * fps)))
    name = Path(video).name
    base_t = base_t_ms if base_t_ms is not None else int(time.time() * 1000)
    _log(f"{name}: {total} frames @ {fps:.1f}fps ({duration:.0f}s); sampling every "
         f"{interval_s}s (stride {stride}), sharp_min={sharp_min}, max={max_frames}")

    store = TraceMemoryStore(store_path)
    idx = 0
    kept = 0
    dropped_blur = 0
    try:
        while kept < max_frames:
            ok = cap.grab()
            if not ok:
                break
            if idx % stride != 0:
                idx += 1
                continue
            ok, frame = cap.retrieve()
            idx += 1
            if not ok or frame is None:
                continue
            frame_t_s = (idx / fps) if fps else 0.0
            sharp = _sharpness(frame)
            if sharp < sharp_min:
                dropped_blur += 1
                continue
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
            if not ok:
                continue
            img_b64 = base64.b64encode(buf.tobytes()).decode()
            del frame, buf  # raw pixels gone from memory before the next decode
            t0 = time.time()
            try:
                desc = perceive_frame_b64(img_b64)
            except Exception as exc:  # noqa: BLE001  one bad frame must not kill the run
                _log(f"perceive error @ {frame_t_s:.1f}s: {exc}")
                continue
            del img_b64  # the only copy of the pixels is now gone; only text remains
            if not desc.strip():
                continue
            store.write_observation(
                text=f"PHYS [{name} @ {frame_t_s:.1f}s]\n{desc}",
                t_ms=base_t + int(frame_t_s * 1000),
                source="phys_video",
                place=f"video:{name}",
                provenance={"channel": "phys_video_gemma", "video": name,
                            "frame_time_s": round(frame_t_s, 2), "sharpness": round(sharp, 1)},
                metadata={"video": name, "frame_time_s": round(frame_t_s, 2)},
            )
            kept += 1
            preview = desc.replace("\n", " ")[:90]
            _log(f"kept #{kept} @ {frame_t_s:5.1f}s sharp={sharp:6.0f} "
                 f"({time.time()-t0:.1f}s) | {preview}")
    finally:
        cap.release()
        store.close()
    _log(f"done: {kept} perceived, {dropped_blur} dropped (blur), source=phys_video")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--store", default="data/trace_store.sqlite3")
    ap.add_argument("--interval", type=float, default=2.0, help="seconds between sampled frames")
    ap.add_argument("--sharp-min", type=float, default=80.0, help="min Laplacian variance to keep")
    ap.add_argument("--max", type=int, default=40, help="max frames to perceive (token guard)")
    ap.add_argument("--base-t-ms", type=int, default=None, help="anchor timestamp (ms); default now")
    args = ap.parse_args()
    return perceive_video(args.video, args.store, args.interval, args.sharp_min,
                          args.max, args.base_t_ms)


if __name__ == "__main__":
    raise SystemExit(main())
