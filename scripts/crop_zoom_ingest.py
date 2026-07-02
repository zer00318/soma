#!/usr/bin/env python
"""Crop-zoom capture pass: ADD instance-level (detect -> crop -> read) observations to an
existing perceived store, so small objects / fine print become legible. Augments — it does
NOT replace the whole-frame/screen observations already in the store.

Local-only stack: GroundingDINO/SAM2 (detect) + gemma-vision (read crops). Frames are read
in memory and never persisted by this pass (privacy moat).

    .venv/bin/python scripts/crop_zoom_ingest.py --frames data/phone_captures/bedroom_kf40 \
        --store data/trace_store_cropzoom.sqlite3 --max-instances 8
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from trace_memory.store import TraceMemoryStore
from trace_memory.store.world import observation_time_range, scene_frustum_anchor, session_coordinate_frame

# Reuse the exact frame->anchor conventions of the scene_only ingest so the binder/agent
# treat crop-zoom observations identically to existing ones.
from light_ingest import SCENE_PROMPT, _frame_time_ms, _gen, _load, _place_bucket, _pose_degrees  # noqa: E402
from instance_perceive import perceive  # noqa: E402
import base64  # noqa: E402


def _compose(inst: dict) -> str:
    name = (inst.get("name") or inst.get("det_label") or "object").strip()
    bits = [name]
    desc = []
    for key in ("colour", "material", "state", "orient"):
        v = (inst.get(key) or "").strip()
        if v and v.lower() not in {"none", "unknown", "n/a", ""}:
            desc.append(v)
    if desc:
        bits.append(" — " + "; ".join(desc))
    txt = (inst.get("text") or "").strip()
    if txt and txt.lower() not in {"none", "no text", "n/a", ""}:
        bits.append(f'; text "{txt}"')
    return "".join(bits)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", required=True)
    ap.add_argument("--store", required=True)
    ap.add_argument("--max-instances", type=int, default=8)
    ap.add_argument("--observer", action="store_true",
                    help="run the CV observer first; only perceive sharp/novel frames (product behavior)")
    ap.add_argument("--scene", action="store_true",
                    help="also do a whole-frame scene pass (local gemma) for location/relations/screen")
    ap.add_argument("--scene-model", default="gemma3:12b-it-qat")
    args = ap.parse_args()

    frames_dir = Path(args.frames)
    frames = sorted(frames_dir.glob("*.jpg"), key=lambda p: float(p.stem))
    if args.observer:
        from trace_memory.capture import Observer
        obs = Observer()
        frames = [f for f in frames if obs.consider(f).keep]
        print(f"[observer] {obs.stats()}  -> perceiving {len(frames)} frames", flush=True)
    coordinate_frame = session_coordinate_frame(frames_dir.name)
    store = TraceMemoryStore(str(args.store))

    written = 0
    t_start = time.time()
    for index, frame_path in enumerate(frames):
        pose = _pose_degrees(_load(frame_path.with_suffix(".pose.json")))
        if not pose:
            # No pose sidecar (e.g. frames extracted from raw video with no ARKit telemetry).
            # A neutral placeholder keeps the pipeline running for text recall; it carries no
            # real geometry, so it must never feed coordinate individuation/counting.
            pose = {"yaw_deg": 0.0, "pitch_deg": 0.0, "roll_deg": 0.0}
        t_ms = _frame_time_ms(frame_path, index)
        place = _place_bucket(pose)

        # Whole-frame scene pass: gives the "where" (relations/location) and screen text that
        # isolated crops cannot. Written as a vlm scene observation alongside the instances.
        if args.scene:
            try:
                scene_text = _gen(base64.b64encode(frame_path.read_bytes()).decode(),
                                  args.scene_model, "local", SCENE_PROMPT)
            except Exception as exc:  # noqa: BLE001
                scene_text = ""
            if scene_text:
                store.write_canonical_observation(
                    text=scene_text, t_ms=t_ms, source="phone_camera", helper_type="vlm",
                    coordinate_frame=coordinate_frame, time_range=observation_time_range(t_ms),
                    spatial_anchor=scene_frustum_anchor(pose=pose, metadata={"frame_ids": [frame_path.name]}),
                    provenance={"frame": frame_path.name, "scene_pass": True},
                    source_support={"frame_ids": [frame_path.name], "frame_paths": [str(frame_path)]},
                    place=place, pose=pose,
                    metadata={"frame_index": index, "helper_prompt": "scene_perception"},
                    immutable_raw=True,
                )
                written += 1
        try:
            instances = perceive(str(frame_path), args.max_instances)
        except Exception as exc:  # noqa: BLE001
            print(f"  frame {index} FAILED {exc}", flush=True)
            continue
        for inst in instances:
            name = (inst.get("name") or inst.get("det_label") or "").strip()
            if not name:
                continue
            store.write_canonical_observation(
                text=_compose(inst),
                t_ms=t_ms,
                source="phone_camera",
                helper_type="vlm_object",
                coordinate_frame=coordinate_frame,
                time_range=observation_time_range(t_ms),
                spatial_anchor=scene_frustum_anchor(
                    pose=pose,
                    metadata={"frame_ids": [frame_path.name], "ingest_backend": "cropzoom"},
                ),
                provenance={"frame": frame_path.name, "crop_zoom": True, "box": inst.get("box")},
                source_support={"frame_ids": [frame_path.name], "frame_paths": [str(frame_path)]},
                place=place,
                pose=pose,
                metadata={
                    "frame_index": index,
                    "helper_prompt": "instance_crop_zoom",
                    "section_kind": "physical_object",
                    "subject_hint": name,
                    "det_label": inst.get("det_label"),
                    "attribute_value": inst.get("colour"),
                    "attribute_kind": "color",
                    "verbatim_text": inst.get("text"),
                },
                immutable_raw=True,
            )
            written += 1
        print(f"  frame {index+1}/{len(frames)} -> {len(instances)} instances "
              f"({written} total, {time.time()-t_start:.0f}s)", flush=True)

    print(f"[cropzoom] wrote {written} instance observations to {args.store} in {time.time()-t_start:.0f}s")
    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
