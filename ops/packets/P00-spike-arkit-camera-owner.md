# P00 — SPIKE: ARKit as the single camera owner
wave: W0 · tag: judgment · executor: Opus effort=high (agent teams OK) or Fable · depends: none
timebox: 1 day. A spike answers a question; it does not ship features.

## The question this spike answers
Can ARKit own the camera on the founder's iPhone 17 (base, no LiDAR, iOS 26) while the
existing helper crew (detector/tracker, FastVLM, Vision OCR) consumes ARKit's frames at
useful throughput — giving us 6-DOF pose + world anchors for free?

## Context (self-contained)
The app today captures via AVCaptureSession (`trace-native-fastvlm/FastVLM App/CaptureV2.swift`,
`FrameSupplier.swift`). A previous attempt ran ARKit AND AVCapture simultaneously — iOS
forbids two camera owners, so ARKit was declared dead and reverted (commit 4c8a58a). The
third option was never tried: ARSession as the ONLY camera owner, with helpers consuming
`ARFrame.capturedImage` (a CVPixelBuffer — same type helpers already eat). ARKit world
tracking needs no LiDAR. A partial engine exists from the reverted attempt:
`trace-native-fastvlm/FastVLM App/TraceARKitEngine.swift` — study it first.
Deploy constraints: Xcode 26.3 on Sequoia; build via `scripts/deploy_ios.sh` (UDID/team inside).

## Laws that bind you
L1: no frame/audio leaves the phone (pose/anchor metadata + text may). L2: honesty — report
measured numbers, not hopes. Spike code lives on a branch `spike/arkit-owner`; it does NOT
merge to main.

## Do
1. Branch. Make ARSession the sole camera source behind the existing FrameSupplier seam so
   the helper crew runs unmodified on ARFrames.
2. Measure on the physical iPhone 17 (10-minute handheld walk around a room):
   a. helper throughput (frames/sec through detector + VLM + OCR) vs current AVCapture baseline;
   b. pose stability: does `ARCamera.transform` stay tracking (not `.limited`) during
      normal walking/panning? % of time in each tracking state;
   c. anchor persistence: place 5 ARAnchors on objects, leave the room, return — how many
      re-localize within ~0.5m?
   d. thermal/battery is OUT OF SCOPE (spec §1) — note it only if the phone throttles
      within the 10 minutes.
3. Write the numbers into this file under Findings, flip INDEX status.

## Done when
Findings section below contains the four measurements from a real device run, and a
one-paragraph verdict: GREEN (P10 proceeds on ARKit) or RED (P10 falls back to
track-anchor + on-device monocular depth). No merge to main.

## Findings
- (spike executor writes here)
