# CODEX BRIEF 10 capture pivot RESULT

## Shipped

- Default app launch now opens `CAPTURE`, not the FastVLM/chat demo.
- Capture mode records an ARKit world-tracking session to `Documents/capture_<ts>/`:
  - `video.mov` from `ARFrame.capturedImage` via `AVAssetWriter`.
  - `poses.ndjson` at about 10 Hz with `t`, 16-float camera transform, 9-float intrinsics, and tracking state.
  - `meta.json` with device model, app build SHA, selected AR video format, camera resolution/FOV once first frame arrives, start/stop battery, thermal samples at start/every minute/stop, counts, sizes, and the devicectl pull command.
- Capture screen while recording shows only recording time, file size, battery, free disk, pose-tracking state, and Stop.
- `wide-FOV stills` setting attempts an ultrawide `AVCaptureMultiCamSession` alongside ARKit and writes `wide/*.jpg` every 2s if it actually starts. If setup/start fails, it marks `unavailable with AR tracking` and flips the toggle off.
- Spatial live word map remains behind `Live preview (experimental)`.
- Legacy FastVLM/chat/demo UI is quarantined behind a long press on the build label, then Debug -> Legacy FastVLM demo.
- Expensive default-flow flags are disabled: `ENABLE_OCR_STILL_PASS=false`, detector memory remains false, person enrichment remains false.
- `autoOpenSpatial` is migrated to `autoOpenCapture`; if both keys exist, `autoOpenCapture` wins and the old spatial key is cleared.
- `Sync to Mac` posts metadata only to `<traceHubURL>/capture/perception` with `X-TRACE-Token: dev-token`, `source=capture_session`, and `memory_text` shaped as `CAPTURE | <ts> | <duration>min | <size>MB`. File transfer remains devicectl pull.

## Verification

- Focused iPhoneOS Swift typecheck of `CaptureMode.swift` + app entry passed using SDK `iphoneos26.5`.
- Python suite: `124/124` passing.
- North-star: unchanged pre-existing result `9/10 = 0.90`, threshold `0.8`; same commitment-direction fixture miss as baseline.

## Not Device-Verified

Loud warning: git commits, full Xcode build, install, and physical device capture could not be completed from this managed sandbox.

- `git commit` blocked: `.git/index.lock` cannot be created (`Operation not permitted`).
- Documented `xcodebuild ... -sdk iphoneos26.5 ASSETCATALOG_EXEC=/tmp/actool_wrapper/actool build` blocked before source compilation by SwiftPM cache writes outside writable roots (`~/.cache`, `~/Library/Caches`). Redirecting caches caused Xcode's own `sandbox-exec` to fail.
- `xcrun devicectl list devices` blocked twice by CoreDeviceService initialization timeout.

## Multicam Verdict

Actual ARKit + ultrawide multicam coexistence is still pending physical device verification. The app now performs the requested runtime test: if `AVCaptureMultiCamSession` cannot start next to ARKit, capture continues with wide-FOV stills off and status `unavailable with AR tracking`.

## Thermal Observations

No local device run was possible, so there are no measured thermal observations. Capture metadata will log thermal state at start, every minute, and stop for the founder's 10-minute acceptance walk.

## Risks

- Needs lead-run build/install outside this sandbox before founder testing.
- The ultrawide still path may be unavailable with ARKit on the target iPhone; result will be known only after the on-device runtime test.
- `video.mov` records the raw AR camera buffer orientation; playback should be checked after the first device pull.
- The 10-minute cool-phone acceptance remains unverified.
