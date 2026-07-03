# P00 — SPIKE: ARKit as the single camera owner (MEASURE, don't build — apparatus exists)
wave: W0 · tag: judgment · executor: founder (device walk) + Fable (analysis) · depends: none
timebox: one 15-minute device session. A spike answers a question; it ships no features.

## The question this spike answers
Does ARKit-as-sole-camera-owner run the FULL helper crew (detector/tracker + FastVLM +
OCR) at useful throughput with stable tracking on the founder's iPhone 17 (base, no
LiDAR, iOS 26)?

## Discovery that reshaped this packet (2026-07-03 code audit)
The spike apparatus ALREADY EXISTS and the old "ARKit is dead" verdict tested a different
configuration:
- `TraceARKitEngine.swift` is a complete ARKit-sole-owner engine: feeds the SAME
  AsyncStream<CMSampleBuffer> seam the helpers consume, fixes the 90°-rotation bug of the
  first attempt (sensor-landscape → portrait BGRA), autofocus fix in (296da44 — off meant
  unreadable text), 6-DOF pose + intrinsics + 8×6 depth-grid in every metadata POST
  (aa7f8b6), ARWorldMap save/load for cross-session relocalization.
- `ContentView.swift` line ~808: `spatialMode` (@AppStorage, Settings toggle "Spatial
  mode (ARKit)") cleanly switches the camera owner: ARKit OR AVCapture, never both — the
  old two-owners conflict (4c8a58a) does not apply to this path.
- `ENABLE_LOCAL_DETECTOR_MEMORY = true` today, so spatialMode now runs detector too —
  the config in which ARKit was written off had the detector story differently wired.

## Laws that bind you
L1: frames/audio never leave the phone (pose/anchor metadata + text may — already true:
metadata carries numbers only). L2: report measured numbers, not hopes.

## Do
1. Founder: deploy current main (`scripts/deploy_ios.sh`; Xcode 26.3/Sequoia), toggle
   Settings → "Spatial mode (ARKit)" ON, then a 10-minute capture: 5 min slow room walk,
   2 min desk dwell, 1 min brisk pan (stress), leave the room and return (relocalization
   probe). Speak one sentence mid-walk (ASR liveness).
2. Fable: compute the verdict FROM THE STORE (no Swift changes needed — every observation
   POST already carries `arkit_tracking_status` + `arkit_camera`):
   a. helper throughput: observation rows/min by helper vs the most recent AVCapture
      session on the same store;
   b. tracking stability: % of observations with status Tracking vs Limited(reason);
   c. anchor sanity: do arkit_anchors for static desk objects stay within ~0.5 m across
      the dwell? does the return-to-room relocalize (status + anchor continuity)?
   d. crew integrity: detector tracks + OCR reads + VLM text + ASR all present in the
      session (nothing starved by ARKit owning the camera).
3. Write Findings below; flip INDEX.

## Verdict rule
GREEN (all four sane) → P10 proceeds on ARKit pose as the session-geometry tier.
RED → fallback is the coordinate-light place-graph (place recognition + fingerprints +
tracks) per spec §2's coordinates ruling — NOT open-source SLAM, NOT proprietary VIO.

## Findings
- (written after the device session)
