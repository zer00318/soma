#!/usr/bin/env python3
"""Audit whether a capture can be replayed without trusting derived captions.

The recorder is the source of truth. VLM/OCR/entity artifacts are indexes over that
source and may be rebuilt after capture. This module deliberately does not grade
semantic quality; it grades whether the original evidence survived and whether
gaps are reported rather than silently hidden.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path


FRAME_TIME_RE = re.compile(r"_(\d+(?:\.\d+)?)s(?:\.[^.]+)?$")


def sha256_file(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def frame_times(frames_dir: str | os.PathLike[str]) -> list[float]:
    times = []
    for path in Path(frames_dir).glob("*"):
        match = FRAME_TIME_RE.search(path.name)
        if match:
            times.append(float(match.group(1)))
    return sorted(set(times))


def timeline_stats(times: list[float]) -> dict:
    if not times:
        return {"count": 0, "start_seconds": None, "end_seconds": None,
                "max_gap_seconds": None}
    gaps = [b - a for a, b in zip(times, times[1:])]
    return {
        "count": len(times),
        "start_seconds": times[0],
        "end_seconds": times[-1],
        "max_gap_seconds": max(gaps, default=0.0),
    }


def audit_native_meta(meta: dict, require_audio: bool = True) -> dict:
    """Return hard capture-contract failures for a finalized native evidence pack."""
    failures: list[str] = []
    duration = float(meta.get("video_duration_seconds") or 0)
    wall_duration = float(meta.get("duration_seconds") or 0)
    frame_count = int(meta.get("frame_count") or 0)
    dropped = int(meta.get("dropped_video_frames") or 0)
    max_gap = meta.get("max_frame_gap_seconds")

    if not meta.get("final"):
        failures.append("capture_not_finalized")
    if not meta.get("video_file") or frame_count <= 0 or duration <= 0:
        failures.append("video_evidence_missing")
    if dropped:
        failures.append("video_frames_dropped")
    if max_gap is None:
        failures.append("frame_gap_not_measured")
    elif float(max_gap) > 0.25:
        failures.append("video_timeline_gap")
    if wall_duration and duration and wall_duration - duration > 0.75:
        failures.append("video_tail_missing")

    if require_audio:
        audio_duration = float(meta.get("audio_duration_seconds") or 0)
        audio_offset = abs(float(meta.get("audio_start_offset_seconds") or 0))
        if not meta.get("audio_recorded") or not meta.get("audio_file"):
            failures.append("audio_evidence_missing")
        elif duration and audio_duration + 0.75 < duration:
            failures.append("audio_tail_missing")
        if audio_offset > 0.75:
            failures.append("audio_start_late")

    pose_count = int(meta.get("pose_count") or 0)
    pose_end = float(meta.get("pose_end_seconds") or 0)
    if pose_count <= 0:
        failures.append("pose_evidence_missing")
    elif duration and pose_end + 0.5 < duration:
        failures.append("pose_tail_missing")

    return {
        "pass": not failures,
        "failures": failures,
        "capture_seconds": wall_duration,
        "video_seconds": duration,
        "capture_overrun_seconds": max(0.0, duration - wall_duration),
        "rule": "capture work must finish inside the experience duration; reasoning is post-capture",
    }


def build_offline_audit(source: str, frames_dir: str, segment_end: float) -> dict:
    """Describe an evaluation evidence pack without pretending it proves live speed."""
    source_path = Path(source).resolve()
    times = frame_times(frames_dir)
    stats = timeline_stats(times)
    tail_gap = None if stats["end_seconds"] is None else max(0.0, segment_end - stats["end_seconds"])
    return {
        "schema_version": 1,
        "mode": "offline_replay",
        "real_time_proven": False,
        "source": {
            "path": str(source_path),
            "bytes": source_path.stat().st_size,
            "sha256": sha256_file(source_path),
            "retained": True,
        },
        "capture_window": {"start_seconds": 0.0, "end_seconds": segment_end},
        "derived_frame_index": {**stats, "tail_gap_seconds": tail_gap},
        "contract": {
            "raw_source_is_authoritative": True,
            "derived_text_is_rebuildable": True,
            "slow_models_allowed_during_capture": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--native-meta")
    group.add_argument("--source")
    parser.add_argument("--frames-dir")
    parser.add_argument("--segment-end", type=float)
    parser.add_argument("--allow-no-audio", action="store_true")
    parser.add_argument("--out")
    args = parser.parse_args()

    if args.native_meta:
        with open(args.native_meta) as handle:
            result = audit_native_meta(json.load(handle), require_audio=not args.allow_no_audio)
    else:
        if not args.frames_dir or args.segment_end is None:
            parser.error("--source requires --frames-dir and --segment-end")
        result = build_offline_audit(args.source, args.frames_dir, args.segment_end)

    encoded = json.dumps(result, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(encoded + "\n")
    print(encoded)
    return 0 if result.get("pass", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
