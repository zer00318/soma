# CODEX BRIEF 13 — pose-driven sharp-frame selection (Mac-side, no device)

Context: the home walk lost 96% of frames to motion blur (median Laplacian
sharpness 6; threshold-40 kept 55/1440). The capture writes poses.ndjson
(~10Hz: t, 16-float transform, intrinsics, tracking_state). DWELL MOMENTS
— when the camera is nearly still — are exactly the sharp frames AND the
moments the wearer is paying attention to. Select frames by LOW CAMERA
MOTION from poses, not by post-hoc Laplacian alone. This is the density
lever and needs no phone (it's being restored) — verify on the preserved
data: data/walks/home_capture_20260613/{video.mov,poses.ndjson}.

BUDGET: P0 then P1, commit per P (git may be read-only in sandbox -> leave
uncommitted + loud RESULT note). Stop after P1. Mac-side only, no soma_hub
change, no iOS. Scripts use .venv/bin/python (cv2 there).

## P0 — scripts/walk_select_sharp_frames.py (new)

Inputs: --poses <poses.ndjson>, --video <mov>, --out-dir /tmp/walk_frames,
--target-fps 3.0 (max frames/sec to emit), --still-percentile 40
(keep frames in the calmest X% of motion).

- parse_poses(path) -> list[{t, R (3x3 from transform cols 0-2), pos
  (transform[12..14]), tracking}]. Skip non-'normal' tracking rows.
- angular_speed between consecutive poses: relative rotation
  R_rel = R_prev^T @ R_cur; angle = arccos((trace(R_rel)-1)/2); divide by
  dt. translational_speed = |pos_cur - pos_prev| / dt. motion =
  angular_speed + 0.5*translational_speed (rad/s + m/s blend).
- Select timestamps: within each 1/target_fps-second bucket, pick the
  pose with the LOWEST motion that is also below the still-percentile
  motion threshold (computed over all poses). This yields steady frames
  spread across the walk, not clustered.
- For each selected t: seek the video (cv2 CAP_PROP_POS_MSEC = t*1000),
  read the frame, ALSO compute Laplacian sharpness, and keep only if
  sharpness >= 12 (cheap final guard). Save out_dir/frame_<idx>_<t>s.jpg
  + manifest.json (file, t, sharpness, motion). Print kept/considered.
- Honesty: if poses are absent/empty, print a clear message and fall back
  to nothing (the caller can use the old extractor). Do NOT crash.
- Self-test (--self-test, no real files): synth 60 poses — 30 "moving"
  (rotation stepping 0.2 rad each) then 30 "still" (tiny 0.001 rad jitter);
  stub the video read with a loader callable so no file needed; assert the
  selected timestamps come overwhelmingly (>=80%) from the still half;
  assert empty-poses path returns [] without crashing. SELF-TEST PASS.

## P1 — wire into the pipeline as the default frame source

- scripts/run_capture_pipeline.sh (new): one command, capture_dir ->
  trusted world. Steps: walk_select_sharp_frames (if poses.ndjson present,
  else walk_extract_frames fallback) -> walk_segment_frames ->
  walk_label_crops -> walk_name_objects (gemma, SERIAL — one-heavy-job
  law) -> walk_build_inventory -> walk_fuse_world -> ingest_walk_world.
  Args: --capture-dir, --out-prefix /tmp/run, --floor 0.30. Log each
  stage with timestamps; write run_<prefix>.log; final line "PIPELINE
  DONE <trusted_distinct> trusted objects".
- Do NOT run it (gemma marathon is occupying the GPU now) — just ship it
  runnable. Lead runs it on the preserved home capture after the marathon.

## ACCEPTANCE (lead verifies on preserved data)
1. walk_select_sharp_frames on data/walks/home_capture_20260613 yields
   MORE usable frames than the 55 the Laplacian gate kept, biased to
   steady/dwell moments.
2. run_capture_pipeline.sh runs end-to-end on that capture dir.
3. RESULT ops/CODEX_BRIEF_13_RESULT.md: frames-selected count vs 55,
   motion-threshold used, any caveats.
