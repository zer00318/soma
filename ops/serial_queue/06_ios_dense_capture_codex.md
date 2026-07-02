# CODEX BRIEF — iOS DENSE CAPTURE (deep async decouple)
*Run ONLY if the constant relaxation (already applied) doesn't reach ~3-5 fps streaming. This is the
structural fix. Hardware: iPhone 17 (id 00008150-001460D83686401C). Rebuild + redeploy after.*

## PROBLEM (measured)
Spatial-mode capture streams ~0.1 fps (14 frames for a multi-minute recording). The frame POST is
welded to the slow on-device VLM loop, so the coordinate binder starves.

## ALREADY APPLIED (constants — Chief)
- `FrameSupplier.swift`: minInterval 0.30->0.12, settledMotion 0.045->0.10, moveToReemit 0.10->0.03,
  idleInterval 2.0->0.7.
- `ContentView.swift`: VISION_FRAME_DELAY 650ms->180ms.

## THE STRUCTURAL FIX (this brief)
Decouple frame STREAMING-TO-DISK from VLM inference. Frames + depth + pose must POST to the Mac on
their OWN cadence (~3-5 fps), independent of `analyzeVideoFrames()` / on-device VLM.

### Files / anchors (from recon)
- `FastVLM App/ContentView.swift`:
  - `analyzeVideoFrames()` loop ~L1189-1387; the `try await Task.sleep(for: VISION_FRAME_DELAY)` at
    ~L1225/L1384 gates everything. `sendDebugFrame(_:frameIndex:)` ~L2874 is the frame->Mac POST
    (carries pose + depth_grid). `distributeVideoFrames()` ~L1389 splits the frame stream.
  - `depthGridSnapshot()` (TraceARKitEngine.swift:149) is a synchronous 48-hittest call done per
    frame inside sendDebugFrame — cache it, refresh every 3rd frame.
### Directive
1. Add a SEPARATE async consumer of the camera frame stream that calls `sendDebugFrame` on a fixed
   ~200ms cadence (spatial) gated ONLY by FrameSupplier.emit + sharpness — NOT by the VLM loop.
2. Make `sendDebugFrame` non-blocking (fire-and-forget Task) and cache the depth grid (refresh every
   3rd frame) so the 48-hittest cost doesn't stall streaming.
3. Keep ARKit camera ownership intact (spatial mode); confirm depth+pose still ride each frame.

### VALIDATION
Rebuild + deploy; record a 60s slow dwell; confirm the Mac's session dir receives >=150 frames each
with matching .depth.json + .pose.json. (Was 14.)

### BUILD / DEPLOY
```
cd trace-native-fastvlm
xcodebuild -project FastVLM.xcodeproj -scheme "FastVLM App" \
  -destination 'platform=iOS,id=00008150-001460D83686401C' \
  -allowProvisioningUpdates -configuration Debug -derivedDataPath build/dd build
xcrun devicectl device install app --device D3A506B2-8923-5313-B8A3-FF769ABBA228 \
  "build/dd/Build/Products/Debug-iphoneos/FastVLM App.app"
```
