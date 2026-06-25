# CODEX BRIEF 10 — the capture pivot: phone records, Mac understands

ARCHITECTURE DECISION (lead, 2026-06-13, founder-driven): realtime
on-device dense perception hit the thermal/compute wall (measured:
dense build plateaued at +20 new objects, 676 rejections, founder
verdict "marginal"). The product thesis is CAPTURE precedes intent —
capture must be realtime; UNDERSTANDING moves to the Mac (offline
pipeline, built tonight by the local fleet: FastSAM + open-CLIP over
extracted frames). Your job: make the phone a flawless recorder and
quarantine the dinosaurs.

BUDGET: P0 → P1 → P2, commit per P if git works (else loud warning +
RESULT file). Stop after P2. Lead installs.

Laws: suite+north-star green if you touch trace_hub (you shouldn't);
build recipe unchanged (-sdk iphoneos26.5 + ASSETCATALOG_EXEC wrapper).

## P0 — Capture mode: one screen, records everything, computes nothing

- New default screen on app launch: CAPTURE. Big start/stop button.
  When running, an ARKit world-tracking session records to
  Documents/capture_<ts>/ :
  - video.mov: the ARKit camera feed (reuse GroundTruthRecorder
    machinery), highest available resolution.
  - poses.ndjson: one line per ARFrame at ~10Hz: {t, transform (16
    floats), intrinsics (9), tracking_state}.
  - meta.json: device model, fov, start ts, app build sha.
- NO MobileCLIP, NO FastVLM, NO OCR, NO yolo, NO posting during
  capture. Battery % at start/stop into meta.json. Thermal state
  logged each minute. The screen shows: recording time, file size so
  far, battery, free disk, pose-tracking state. That is ALL.
- Stop → files finalized; show "captured N min, M GB, ready to sync".
- 0.5x NOTE (founder request): ARKit world tracking cannot run on the
  ultrawide camera. Add a Settings toggle "wide-FOV stills": when ON,
  every 2s during capture, grab an ultrawide STILL via a secondary
  AVCaptureSession IF AVCaptureMultiCamSession.isSupported allows it
  alongside ARKit (TEST THIS — if ARKit + multicam conflict, the
  toggle shows 'unavailable with AR tracking' and falls back to OFF;
  document which in RESULT). Stills go to capture_<ts>/wide/*.jpg.
- Spatial mode (live word map) stays in the app behind a "Live
  preview (experimental)" button — untouched, not default.

## P1 — Dinosaur quarantine

- Default UI = Capture screen only. Chat/FastVLM demo UI, yolo
  detector paths, OCR still pass, person enrichment: NOT in the
  default flow; reachable only behind a debug menu (long-press on
  version label). Do not delete code — quarantine it (founder may
  resurrect pieces). ENABLE_OCR_STILL_PASS=false and detector path
  disabled flags where they exist.
- The autoOpenSpatial pref now opens CAPTURE mode instead (rename
  handled: read both keys, prefer autoOpenCapture).

## P2 — Sync without the cable dance

- "Sync to Mac" button on the capture screen: POSTs capture_<ts>
  metadata to the hub (X-TRACE-Token) at traceHubURL as
  source=capture_session memory_text "CAPTURE | <ts> | <duration>min
  | <size>MB" so the Mac knows a session exists; actual file transfer
  stays devicectl (lead pulls) — print the exact pull command into
  meta.json for convenience.
- Acceptance: founder hits record, walks 10 min, phone stays COOL
  (thermal nominal/fair logged), stops; lead pulls capture dir with
  one devicectl command; poses.ndjson parses; video plays.

## RESULT file: ops/CODEX_BRIEF_10_capture_pivot_RESULT.md — what
shipped, multicam verdict, thermal observations from any local run,
risks.
