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

## Findings (founder walks 2026-07-02/03, analyzed from store metadata — VERDICT: CONDITIONAL GREEN)
Sessions analyzed: Jul 2 12:27 (1.2min, full crew), Jul 3 19:01 (8.6min, vlm+ocr),
Jul 3 21:01 (6.4min, detector, 31 track_ids, build cf3b08b). Data initially landed in
evaluation/day_in_life/day_in_life.sqlite3 — the hub had been left pointed at the demo
store; 164 nodes copied into data/trace_store.sqlite3, hub restarted on the canonical
store (spec: ONE store).
- **a. throughput:** crew runs on ARKit frames — Jul 3 live walk 12.6 rows/min sustained
  over 6.4min with 31 distinct track_ids; short bursts up to 117 rows/min (Jul 2). No
  starvation signal. Full crew simultaneously (detector+VLM+OCR+ASR) proven Jul 2 12:27.
- **b. tracking stability: THE defect.** 100% of observations in EVERY session were
  `Limited: relocalizing` — tracking never reached normal. Root cause: `start()` force-
  loads the saved ARWorldMap (`initialWorldMap`), and a stale map (other room/lighting)
  holds the session in relocalization forever. The engine's own `forceFreshStart()`
  comment admits the mode; it was never invoked automatically. FIXED same day: 10s
  relocalization watchdog → abandon map, track fresh (background save then overwrites the
  stale map with a good one — self-healing). Build green.
- **c. anchor sanity:** cross-session anchor persistence WORKS (Jul 3 19:01 and 21:01
  restored identical anchor positions from the saved map). Camera world position on ~100%
  of rows; travel extent 9.3m × 12.7m matches the flat. Spread: laptop 0.65m (≈target),
  bottle 1.46m, bed 4.71m. Two design flaws deferred to P10: anchors are keyed per LABEL
  (all bottles collapse to one anchor; must key per track/instance) and movable/moving
  labels (person, truck) get world-anchored (must be excluded).
- **d. crew integrity:** ASR absent in the Jul 3 walks (founder didn't speak or channel
  off — re-walk must include speech); OCR present 19:01, absent 21:01 (config differed
  between walks; needs one clean full-crew run).
- **VERDICT: CONDITIONAL GREEN.** ARKit proceeds as the session-geometry tier (P10 GREEN
  branch). Condition: one clean 10-min re-walk on the watchdog build, all helpers on,
  speech included, must show majority `Tracking` status. RED fallback unchanged.

## Condition met — FINAL VERDICT: GREEN (founder walk 2026-07-04 morning)
308 observations over the session window: tracking `Tracking` 261/308 (**85%**, watchdog
working — residual Limited rows are session starts and a 9-row insufficientFeatures
patch); ALL FOUR standing channels alive on ARKit frames simultaneously (detector 226,
vlm 38, ocr 16 — read shampoo brands ELVITAL/PANTENE — asr 28 after the audio-session
fix); frame accounting live: 10,928 received / 2,195 converted (20%, consistent with the
10fps cap). P10 proceeds on the ARKit branch. Known quality items spun out: ASR
fragmentation → P05; per-label anchors + moving-object anchors → P10.
