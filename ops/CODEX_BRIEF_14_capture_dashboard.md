# CODEX BRIEF 14 — capture-session dashboard (housekeeping, read-only)

Lead-fired while the home pipeline runs (do NOT touch
scripts/run_capture_pipeline.sh, scripts/walk_*.py, or anything under
data/walks/*/work/ — a pipeline is actively writing there). This is a
NEW, self-contained, READ-ONLY tool. One file. No soma_hub changes.

## Why
The pivot made captures the unit of work: each lives in
data/walks/<name>/ with meta.json (battery/thermal/duration/poses
counts), video.mov, poses.ndjson, and (after processing) work/run_*.json
artifacts. The founder needs ONE place to see every capture, its health,
and what was found in it.

## P0 — scripts/capture_index.py (new, stdlib only)
- Scan data/walks/*/ for capture dirs (have meta.json or video.mov).
- For each: read meta.json (battery start/stop, thermal samples, duration,
  pose count, build sha, device); stat video.mov size; detect pipeline
  outputs if present: work/run_inventory.json (distinct count),
  work/run_named.json (trusted vs rejected counts via the 'trust' field),
  work/run_world.json (positioned object count). All optional — a raw
  unprocessed capture still lists.
- Emit two things: a JSON summary to --out-json (default
  /tmp/capture_index.json) AND a dark-theme self-contained HTML dashboard
  to --out-html (default /tmp/capture_index.html): one card per capture,
  newest first, showing duration, battery drain, max thermal state,
  size, and IF processed: distinct objects / trusted / positioned, with a
  small bar. Unprocessed captures show a "not yet processed" badge.
- CLI: --walks-dir (default data/walks), --out-json, --out-html,
  --self-test.
- --self-test: build a temp walks dir with one fake capture
  (meta.json with battery 80->78, 3 nominal thermal samples, duration
  600, poses 5000; a 10-byte video.mov; a work/run_named.json with 3
  trusted + 1 rejected records); assert index has 1 capture, drain==2,
  trusted==3, html written and contains the capture name; print
  SELF-TEST PASS exit 0.

## Constraints
- Read-only: never write under data/walks/. Never call the network or a
  model. Never import cv2/torch.
- Commit if git works (else loud RESULT note). Stop after P0.
- RESULT: ops/CODEX_BRIEF_14_RESULT.md.
