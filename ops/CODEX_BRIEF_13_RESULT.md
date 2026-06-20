# CODEX BRIEF 13 RESULT

Canonical detailed result: `ops/CODEX_BRIEF_13_pose_sharp_frames_RESULT.md`.

Key preserved-capture numbers:

- Source: `data/walks/home_capture_20260613/{video.mov,poses.ndjson}`
- Motion threshold at still-percentile 40: `0.13928838888802664`
- Pose-selected frames considered: 1,235
- Frames kept after sharpness `>= 12`: 332
- Prior Laplacian-only threshold-40 baseline from brief: 55
- Improvement: +277 frames, 6.04x

`scripts/run_capture_pipeline.sh` was shipped and syntax-checked but not run,
per the brief's explicit Gemma/one-heavy-job instruction.

LOUD GIT NOTE: commit-per-P was attempted, but `.git` is read-only in this
sandbox (`.git/index.lock: Operation not permitted`), so changes are left
uncommitted.
