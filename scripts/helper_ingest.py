#!/usr/bin/env python3
"""Helper-driven capture ingest — the founder-correct path.

Capture is done by FAST LOCAL specialist helpers, never the frontier model. Per frame:
  1. blur/quality gate (frame_quality) decides blurry-vs-sharp BEFORE perception
  2. instance_perceive (Grounding-DINO detect -> per-crop local reader) extracts each
     object's label/text/colour/material/state in parallel
  3. the structured per-object readout is written as one immutable world-grounded
     observation (coordinate_frame + spatial_anchor from pose + time_range)
The frontier model is reserved for query-time reasoning only (see evaluation/annotate_live).

This keeps capture local, cheap, deterministic-on-a-fixed-input, and re-runnable for free.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from trace_memory.store import (  # noqa: E402
    SleepConsolidator,
    TraceMemoryStore,
    observation_overlap_score,
    observation_time_range,
    scene_frustum_anchor,
    session_coordinate_frame,
)


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_FQ = _load_module("frame_quality", ROOT / "scripts" / "frame_quality.py")
_IP = _load_module("instance_perceive", ROOT / "scripts" / "instance_perceive.py")

# reuse light_ingest's pose/time helpers to keep sidecars identical
_LI = _load_module("light_ingest", ROOT / "scripts" / "light_ingest.py")


def _compose_text(instances: list[dict]) -> str:
    """Structured, verbatim-leaning observation the reasoner can read. One line per object;
    only fields the helper actually filled. Object COUNT is preserved by listing each
    instance, so a downstream counting/consensus pass can individuate."""
    lines = ["## Objects observed (local helpers)"]
    for inst in instances:
        name = (inst.get("name") or inst.get("det_label") or "object").strip()
        bits = []
        for key, label in (("colour", "colour"), ("material", "material"),
                            ("state", "state"), ("orient", "orientation")):
            val = (inst.get(key) or "").strip()
            if val and val.upper() != "NONE":
                bits.append(f"{label}: {val}")
        text = (inst.get("text") or "").strip()
        if text and text.upper() != "NONE":
            bits.append(f'text: "{text}"')
        det = (inst.get("det_label") or "").strip()
        det_note = f" (detected as {det})" if det and det.lower() not in name.lower() else ""
        suffix = (" — " + "; ".join(bits)) if bits else ""
        lines.append(f"- {name}{det_note}{suffix}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("frames_dir")
    ap.add_argument("--store", required=True)
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--sleep-bind", action="store_true")
    ap.add_argument("--max-instances", type=int, default=12)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--blur-threshold", type=float, default=60.0)
    ap.add_argument("--dark-threshold", type=float, default=12.0)
    ap.add_argument("--max-frames", type=int, default=0, help="0 = all; else subsample evenly")
    args = ap.parse_args()

    store_path = Path(args.store)
    if args.fresh:
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(store_path) + suffix)
            if candidate.exists():
                candidate.unlink()

    frames_dir = Path(args.frames_dir)
    frames = sorted(frames_dir.glob("*.jpg"), key=lambda path: float(path.stem))
    if args.max_frames and len(frames) > args.max_frames:
        step = len(frames) / args.max_frames
        frames = [frames[int(i * step)] for i in range(args.max_frames)]

    coordinate_frame = session_coordinate_frame(frames_dir.name)
    store = TraceMemoryStore(str(store_path))
    written = skipped_blur = 0
    recent_nodes: deque[Any] = deque(maxlen=3)
    try:
        for index, frame_path in enumerate(frames):
            t0 = time.time()
            q = _FQ.quality(str(frame_path), blur_threshold=args.blur_threshold,
                            dark_threshold=args.dark_threshold)
            if q.get("blurry") or q.get("dark"):
                skipped_blur += 1
                print(f"  [skip blur] {frame_path.name} sharp={q.get('sharpness'):.0f} "
                      f"bright={q.get('brightness'):.0f}", flush=True)
                continue
            try:
                instances = _IP.perceive(str(frame_path), max_instances=args.max_instances,
                                         workers=args.workers)
            except Exception as exc:  # noqa: BLE001
                print(f"  frame {index} FAILED {exc}", flush=True)
                continue
            if not instances:
                continue
            text = _compose_text(instances)

            pose = _LI._pose_degrees(_LI._load(frame_path.with_suffix(".pose.json")))
            t_ms = _LI._frame_time_ms(frame_path, index)
            node = store.write_canonical_observation(
                text=text,
                t_ms=t_ms,
                source="phone_camera",
                helper_type="instance_vlm",
                coordinate_frame=coordinate_frame,
                time_range=observation_time_range(t_ms),
                spatial_anchor=scene_frustum_anchor(
                    pose=pose,
                    metadata={"frame_ids": [frame_path.name], "ingest_backend": "local_helpers"},
                ),
                provenance={
                    "frame": frame_path.name,
                    "helper_ingest": True,
                    "backend": "local_helpers",
                    "helpers": ["frame_quality", "instance_perceive"],
                    "frames_dir": str(frames_dir),
                },
                source_support={"frame_ids": [frame_path.name], "frame_paths": [str(frame_path)]},
                place=_LI._place_bucket(pose),
                pose=pose,
                metadata={"frame_index": index, "helper_prompt": "instance_perceive",
                          "sharpness": q.get("sharpness"), "instances": instances},
                immutable_raw=True,
            )

            if recent_nodes:
                previous = recent_nodes[-1]
                store.link(previous.id, node.id, "succession",
                           metadata={"builder": "helper_ingest"})
                for candidate in recent_nodes:
                    overlap = observation_overlap_score(candidate, node)
                    if overlap < 0.35:
                        continue
                    store.link(candidate.id, node.id, "candidate_same_context",
                               weight=overlap,
                               metadata={"builder": "helper_ingest", "space_time_score": overlap})

            recent_nodes.append(node)
            written += 1
            preview = text[:80].replace("\n", " ")
            print(f"  [{written}] {time.time()-t0:.1f}s n={len(instances)} :: {preview}", flush=True)

        if args.sleep_bind:
            summary = SleepConsolidator(store).consolidate()
            print(f"SLEEP_BIND: grouped={summary.grouped_observation_count} "
                  f"composed={summary.composed_memory_count} links={summary.link_count}", flush=True)
        print(f"DONE: {written} observations, {skipped_blur} blurry frames dropped", flush=True)
    finally:
        store.close() if hasattr(store, "close") else None
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
