#!/usr/bin/env python3
"""SOMA Live-Digital Substrate — Screen Frame Sampler.

Simulates glasses by periodically sampling the screen while a video plays,
producing a replayable, oracle-able frame sequence for the live-perception
pipeline (caption + OCR + specialist chaining).

ENTRYPOINT
    capture(session, duration_s, every_s=2.0, region=None) -> manifest_path (str)

OUTPUT LAYOUT
    data/captures/<session>/
        frames/frame_NNNNNN_T.Ts.jpg   (6-digit index, T.T seconds since start)
        manifest.json                   {session, fps, started, frames:[{i,t,path}]}

CLI
    python scripts/capture_screen_live.py \\
        --session my_session --duration 30 [--every 2.0] [--region x,y,w,h]

    python scripts/capture_screen_live.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# Project root: resolve relative to THIS file so the script works regardless
# of the current working directory.
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent


def _frames_dir(session: str) -> Path:
    return _REPO_ROOT / "data" / "captures" / session / "frames"


def _manifest_path(session: str) -> Path:
    return _REPO_ROOT / "data" / "captures" / session / "manifest.json"


# ---------------------------------------------------------------------------
# Core capture loop
# ---------------------------------------------------------------------------

def capture(
    session: str,
    duration_s: float,
    every_s: float = 2.0,
    region: Optional[Tuple[int, int, int, int]] = None,
) -> str:
    """Capture screen frames at a fixed cadence.

    Args:
        session:    Name for this capture session (used as directory name).
        duration_s: Total capture duration in seconds.
        every_s:    Seconds between frame captures (default 2.0).
        region:     Optional (x, y, width, height) in screen pixels.
                    None = full primary monitor.

    Returns:
        Absolute path to manifest.json as a string.
    """
    try:
        import mss
        from PIL import Image
    except ImportError as exc:
        sys.exit(f"[capture_screen_live] Missing dependency: {exc}. Run: pip install mss Pillow")

    frames_dir = _frames_dir(session)
    frames_dir.mkdir(parents=True, exist_ok=True)
    manifest_p = _manifest_path(session)

    started_iso = datetime.now(timezone.utc).isoformat()
    fps = 1.0 / every_s
    frames_info: list[dict] = []

    # Build the monitor dict once
    with mss.MSS() as sct:
        if region is not None:
            x, y, w, h = region
            monitor = {"left": x, "top": y, "width": w, "height": h}
        else:
            monitor = sct.monitors[1]  # primary monitor

        start_ts = time.monotonic()
        frame_index = 0
        next_capture = start_ts  # first frame immediately

        print(f"[capture] session={session!r} duration={duration_s}s every={every_s}s", flush=True)

        while True:
            now = time.monotonic()
            elapsed = now - start_ts

            if elapsed >= duration_s:
                break

            if now < next_capture:
                # Tight-sleep in small increments to stay responsive
                time.sleep(min(0.05, next_capture - now))
                continue

            # --- grab frame ---
            shot = sct.grab(monitor)
            frame_elapsed = time.monotonic() - start_ts  # record after grab

            # mss returns BGRA; PIL's BGRX raw decoder discards the alpha byte
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

            fname = f"frame_{frame_index:06d}_{frame_elapsed:.1f}s.jpg"
            fpath = frames_dir / fname
            img.save(fpath, "JPEG", quality=90)

            # Path stored in manifest relative to session root so the manifest
            # is portable (can move the session dir without breaking paths).
            rel_path = str(fpath.relative_to(manifest_p.parent))

            frames_info.append({"i": frame_index, "t": round(frame_elapsed, 2), "path": rel_path})

            # Write manifest after every frame (partial runs are usable)
            manifest_p.write_text(
                json.dumps(
                    {"session": session, "fps": fps, "started": started_iso, "frames": frames_info},
                    indent=2,
                )
            )

            print(f"  frame {frame_index:04d}  t={frame_elapsed:.2f}s  {fpath.name}", flush=True)

            frame_index += 1
            next_capture += every_s  # advance by fixed cadence (drift-free)

    print(f"[capture] done — {frame_index} frames written to {manifest_p}", flush=True)
    return str(manifest_p)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def self_test() -> None:
    """Capture 3 frames over ~6 s, assert files exist, print PASS/FAIL."""
    session = "self_test_capture"
    every_s = 2.0
    duration_s = 5.5  # slightly under 3*every_s to avoid 4th frame on slow machines

    # Clean up any previous self-test run
    import shutil
    session_dir = _REPO_ROOT / "data" / "captures" / session
    if session_dir.exists():
        shutil.rmtree(session_dir)

    manifest_p_str = capture(session, duration_s, every_s)
    manifest_p = Path(manifest_p_str)
    frames_dir = _frames_dir(session)

    errors: list[str] = []

    # 1. Manifest exists
    if not manifest_p.exists():
        errors.append(f"manifest missing: {manifest_p}")
    else:
        with manifest_p.open() as f:
            manifest = json.load(f)

        # 2. Frame count in manifest
        n_frames = len(manifest["frames"])
        if n_frames < 2:
            errors.append(f"manifest has only {n_frames} frames (expected 2-3)")

        # 3. Each listed frame file exists on disk
        for fi in manifest["frames"]:
            fp = manifest_p.parent / fi["path"]
            if not fp.exists():
                errors.append(f"frame file missing: {fp}")

        # 4. At least 2 JPEG files in frames dir
        jpegs = sorted(frames_dir.glob("*.jpg"))
        if len(jpegs) < 2:
            errors.append(f"only {len(jpegs)} JPEG(s) in frames dir (expected >= 2)")

        # 5. Required manifest keys
        for key in ("session", "fps", "started", "frames"):
            if key not in manifest:
                errors.append(f"manifest missing key: {key!r}")

    if errors:
        print("FAIL")
        for e in errors:
            print("  ERROR:", e)
        sys.exit(1)
    else:
        print(f"PASS — {n_frames} frames, manifest at {manifest_p}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_region(s: str) -> Tuple[int, int, int, int]:
    parts = [int(v.strip()) for v in s.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("region must be x,y,w,h (four integers)")
    return tuple(parts)  # type: ignore[return-value]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SOMA screen sampler — capture frames off a live screen.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--session", help="Session name (output directory key)")
    parser.add_argument("--duration", type=float, help="Duration in seconds")
    parser.add_argument("--every", type=float, default=2.0, help="Seconds between frames")
    parser.add_argument(
        "--region",
        type=_parse_region,
        default=None,
        help="Screen region as x,y,w,h (pixels)",
    )
    parser.add_argument("--self-test", action="store_true", help="Run self-test and exit")

    args = parser.parse_args()

    if args.self_test:
        self_test()
        return

    if not args.session or args.duration is None:
        parser.error("--session and --duration are required unless --self-test is set")

    capture(args.session, args.duration, args.every, args.region)


if __name__ == "__main__":
    main()
