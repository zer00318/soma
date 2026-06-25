# CODEX BRIEF 13 pose sharp frames RESULT

## Shipped

- Added `scripts/walk_select_sharp_frames.py`.
  - Parses `poses.ndjson`, keeping only `tracking_state == "normal"`.
  - Computes camera motion from consecutive poses:
    `angular_speed + 0.5 * translational_speed`.
  - Uses the calmest motion percentile as the stillness threshold.
  - Picks the lowest-motion pose per `1 / target_fps` bucket.
  - Seeks `video.mov` at each selected timestamp, applies the final
    Laplacian sharpness guard (`>= 12`), writes JPGs plus `manifest.json`.
  - Empty or missing usable poses return an empty manifest instead of
    crashing.
  - `--self-test` uses synthetic moving/still poses and a stub frame loader.
- Added `scripts/run_capture_pipeline.sh`.
  - One command from `--capture-dir` to an ingested trusted world.
  - Uses pose-driven frame selection when `poses.ndjson` exists, otherwise
    falls back to `walk_extract_frames.py`.
  - Runs segmentation, CLIP labels, serial Gemma naming, inventory, fusion,
    and `ingest_walk_world.py`.
  - Logs stages with timestamps to `run_<basename(out-prefix)>.log`.
  - Final line is `PIPELINE DONE <trusted_distinct> trusted objects`.

## Preserved Device Capture Verification

Source: `data/walks/home_capture_20260613/{video.mov,poses.ndjson}`.

Command run:

```bash
.venv/bin/python scripts/walk_select_sharp_frames.py \
  --poses data/walks/home_capture_20260613/poses.ndjson \
  --video data/walks/home_capture_20260613/video.mov \
  --out-dir /tmp/walk_frames_pose13_run1 \
  --target-fps 3.0 \
  --still-percentile 40
```

Result:

- Normal poses parsed: 7,184
- Pose motion records: 7,183
- Motion threshold at still-percentile 40: `0.13928838888802664`
- Pose-selected frames considered: 1,235
- Frames kept after sharpness `>= 12`: 332
- Prior Laplacian-only threshold-40 kept count from brief: 55
- Improvement vs 55: +277 frames, 6.04x
- Output: `/tmp/walk_frames_pose13_run1`

Kept-frame manifest stats:

- Manifest/JPG count: 332 / 332
- Time span: `2.6s` to `719.439s`
- Sharpness min/median/max: `12.003` / `27.0515` / `106.773`
- Motion min/median/max: `0.014493` / `0.0701775` / `0.138683`

This verifies the intended density lever on the preserved device capture:
the frame source is now biased to low-motion dwell/still moments, then
guarded by cheap sharpness, and produces more usable frames than the 55-frame
Laplacian-only baseline.

## Pipeline Status

- `scripts/run_capture_pipeline.sh` was syntax-checked but not run.
- This is intentional: the brief explicitly says not to run the full pipeline
  because Gemma may already be occupying the GPU, and the one-heavy-job law
  requires serial GPU work.
- No `trace_hub` files and no iOS files were changed.
- No live device install/build was performed; this brief is Mac-side only.
  The verification above is against the preserved capture pulled from the
  device, not a new live-device run.

## Verification

- `.venv/bin/python scripts/walk_select_sharp_frames.py --self-test` PASS
- `.venv/bin/python scripts/walk_extract_frames.py --self-test` PASS
- `.venv/bin/python scripts/walk_segment_frames.py --self-test` PASS
- `.venv/bin/python scripts/walk_label_crops.py --self-test` PASS
- `.venv/bin/python scripts/walk_name_objects.py --self-test` PASS
- `.venv/bin/python scripts/walk_build_inventory.py --self-test` PASS
- `.venv/bin/python scripts/walk_fuse_world.py --self-test` PASS
- `PYTHONPYCACHEPREFIX=/tmp/trace_pycache .venv/bin/python -m py_compile ...` PASS
- `bash -n scripts/run_capture_pipeline.sh` PASS
- `python3 -m unittest discover -s tests -p "test_*.py"`: 128/128 PASS
- `python3 evaluation/run_north_star.py`: 9/10 = 0.90, threshold PASS

North-star note: the 0.90 result was the baseline before these changes in
this session. The same `Alice Tester.open_commitments_none` case failed
before and after.

## LOUD GIT NOTE

The brief requested commit-per-P. Git is read-only in this sandbox:

```text
fatal: Unable to create '/Users/zer00/Documents/VLM/.git/index.lock': Operation not permitted
```

The P0/P1 changes and this result are therefore left uncommitted.
