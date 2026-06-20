# CODEX BRIEF 11 — offline world fusion: inventory + poses -> 3D world

Auto-fired when your usage window reopened (lead scheduled it; it is
~03:30, work autonomously). The pivot landed: the phone records
(CaptureMode.swift — video + 10Hz poses.ndjson + meta.json), and a Mac
pipeline (scripts/walk_extract_frames.py -> walk_segment_frames.py ->
walk_label_crops.py -> walk_build_inventory.py) turns a walk video
into a labeled object inventory (/tmp/walk_inventory.json from the
office walk; crops carry source frame + box).

Your job: FUSE inventory objects into 3D and into the graph, so the
offline pipeline's output lands in the SAME world the founder
navigates (/world3d) and queries ("where is X").

BUDGET: P0 -> P1, commit per P (git may be read-only in your sandbox —
then leave uncommitted + loud RESULT warning). Stop after P1. Suite +
north-star green after soma_hub changes. Lead installs/verifies.

## P0 — scripts/walk_fuse_world.py (new, Mac-side)

Inputs: --inventory /tmp/walk_inventory.json, --labels
/tmp/walk_labels.json, --frames-manifest /tmp/walk_frames/manifest.json,
--poses <poses.ndjson or NONE>, --out /tmp/walk_world.json.

- WITH poses (capture-mode sessions): each labeled crop has frame
  timestamp t (manifest) + box center; nearest pose by t gives camera
  transform + intrinsics; backproject box center at an assumed depth:
  intersect the camera ray with the dominant horizontal plane band
  (y = floor estimate from the 5th percentile of pose heights minus
  1.4m default) OR depth=2.0m fallback; emit object {label, x, y, z,
  confidence: clip score, count, frame_evidence: [crop paths]}.
  Cluster same-label points within 1.0m (merge, count-weighted mean).
  HONESTY: mark each fused object with "depth_mode": "plane"|"fallback".
- WITHOUT poses (the office GT video has none): still produce
  /tmp/walk_world.json with objects label+count+evidence and
  x=y=z=null, depth_mode: "none" — the inventory is still ingestable
  as positionless objects.
- Self-test (--self-test, no files): synthetic 3 crops, 2 labels,
  stub poses on a line; assert clustering merges same-label nearby,
  assert null-position path works. SELF-TEST PASS / exit codes.

## P1 — Hub ingest + /world3d rendering of offline objects

- scripts/ingest_walk_world.py: POST each fused object to the hub
  (X-SOMA-Token, capture/perception) as source=offline_walk,
  memory_text "OBJECT | <label> | offline walk fusion | <depth_mode> |
  likely", metadata.spatial_words entry when xyz present (so existing
  spatial_pose flow applies); positionless objects post WITHOUT
  spatial_words but with metadata.offline_inventory={label,count}.
- /api/world: include offline objects; mark them "source":"offline".
  world3d: render offline-positioned objects slightly transparent
  (they are inferred, not raycast-pinned); positionless inventory is
  NOT rendered (it feeds recall only).
- Tests: fixture posts one positioned + one positionless offline
  object; spatial_pose row appears for the positioned one; /api/world
  carries source=offline. Suite + north-star green.

RESULT: ops/CODEX_BRIEF_11_RESULT.md — what shipped, fusion accuracy
caveats, what the lead should verify on real data first.
