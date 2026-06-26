# CODEX BRIEF 07 — CP4 (brain side): parse pose/GPS/time into observation spatial_anchor

Branch: `codex/07-pose-spatial`. Python via `.venv/bin/python`. Additive. Do NOT touch
`trace-native-fastvlm/` or `src/trace_memory/domain/`. Builds on `src/trace_memory/adapters/live_eventlog.py`.

## Why
The cross-frame binder (brief 03) dedups by `spatial_anchor`, but `append_perception_observations` does not
populate it — so on REAL captures the binder cannot dedup. The phone already sends device pose in the
perception packet `metadata.pose` (PoseStamper attitude: qw/qx/qy/qz, pitch/roll/yaw) and a `location_hint`.
Wire those through so each observation carries a spatial anchor.

## Tasks
1. In `append_perception_observations` (and its caller in `scripts/trace_brain_server.py` `_capture`), read
   `payload.metadata.pose` + `location_hint` and derive a coarse, stable `spatial_anchor` string, e.g.
   `bucket(yaw,15deg)|bucket(pitch,15deg)|<location_hint>` — quantize the heading/tilt into ~15-degree
   buckets so the same view maps to the same anchor (this is what lets the binder treat "same heading at
   same place" as the same object). Pass it into each Observation's `spatial_anchor`.
2. If no pose is present, `spatial_anchor=None` (binder already handles that → count stays "at least 1").
3. Keep the GPS/time already in provenance; ensure `t_ms` comes from the record time.

## Acceptance (`tests/test_pose_spatial_anchor.py`)
- Two perception packets with poses 40 degrees apart (same location) → observations get DIFFERENT
  spatial_anchor buckets → binder counts them as 2 instances.
- Two packets with poses 5 degrees apart (same location) → SAME bucket → binder counts 1.
- A packet with no pose → spatial_anchor None, no crash.

## Guardrails
- Additive; `pytest tests/ -q` must pass. No domain edits. Commit on branch. Report the bucketing function + results.
