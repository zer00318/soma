# CODEX BRIEF 14 — ARKit P1: world-anchored pose + ARWorldMap persistence

Branch: `codex/14-arkit-p1`. Swift. iOS 18.2 target. iPhone 17 base (no LiDAR; depth = estimated).
**Do NOT touch kf_memory.json, events.db, or any Python.** Only add/edit Swift files inside
`trace-native-fastvlm/FastVLM App/`.

## Why this matters
Current `PoseStamper` uses CoreMotion (relative IMU attitude: yaw/pitch/roll from device start).
This gives NO world position — two captures of the same chair from different directions look
unrelated. ARKit world-tracking gives a SHARED world coordinate frame across the entire session.
P1 proves: place an anchor at a detected object → move camera away and back → same anchor
reads at the SAME world position (within tolerance). This is the falsifiable core of the
spatial context engine.

## Files to create/edit

### NEW: `trace-native-fastvlm/FastVLM App/TraceARKitEngine.swift`

Create this file. It owns all ARKit state. No ARSCNView or ARView needed — just `ARSession`.
`import ARKit` (system framework; no .pbxproj edit needed on iOS 18).

```swift
import ARKit
import simd

/// Runs an ARWorldTracking session in the background (no rendering).
/// Provides world-relative camera pose and persistent named anchors for detected objects.
@MainActor
final class TraceARKitEngine: NSObject, ObservableObject, ARSessionDelegate {

    static let shared = TraceARKitEngine()
    private let session = ARSession()
    private var anchorMap: [String: (ARAnchor, simd_float3)] = [:]  // label → (anchor, world_xyz)
    private static let worldMapURL: URL = {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        return docs.appendingPathComponent("trace_arkit_worldmap.arworldmap")
    }()

    @Published var isTracking = false
    @Published var trackingStatus = "ARKit idle"

    private override init() { super.init() }

    /// Start (or resume) world tracking. Call on app foreground.
    func start() { ... }

    /// Save ARWorldMap to disk. Call when app goes to background.
    func saveWorldMap() { ... }

    /// Place or update a world anchor for a detected object label.
    /// `normalizedBox` is the object's bounding box in [0,1] image coordinates.
    /// `frame` is the current ARFrame from the running session.
    func placeOrUpdateAnchor(label: String, normalizedBox: CGRect, in frame: ARFrame) { ... }

    /// Current world position of an anchor for `label`, or nil if not yet anchored.
    func worldPosition(for label: String) -> simd_float3? { ... }

    /// Snapshot for inclusion in each frame's metadata POST to the Mac brain.
    /// Returns dict with "arkit_tracking": Bool, "arkit_anchors": [{label, x, y, z}].
    func metadataSnapshot() -> [String: Any] { ... }

    // MARK: - ARSessionDelegate
    func session(_ session: ARSession, didUpdate frame: ARFrame) { ... }
    func session(_ session: ARSession, cameraDidChangeTrackingState camera: ARCamera) { ... }
    func session(_ session: ARSession, didFailWithError error: Error) { ... }
}
```

**Implementation rules:**

`start()`:
- Try to load `trace_arkit_worldmap.arworldmap` from disk (if it exists, use as `initialWorldMap`).
- Configure with `ARWorldTrackingConfiguration()`, `planeDetection = []` (no plane detection in P1),
  `environmentTexturing = .none`, `isAutoFocusEnabled = false`.
- `session.delegate = self`, then `session.run(config, options: savedMap != nil ? [] : .resetTracking)`.
- Update `isTracking = true`, `trackingStatus = "ARKit starting"`.

`saveWorldMap()`:
- `session.getCurrentWorldMap { map, error in guard let map else { return }; ... }`
- Serialize with `NSKeyedArchiver.archivedData(withRootObject: map, requiringSecureCoding: true)`
- Write to `worldMapURL`. Log success/failure to console.

`placeOrUpdateAnchor(label:normalizedBox:in:)`:
- Get the box center in normalized image coords: `CGPoint(x: box.midX, y: box.midY)`.
- Use `frame.hitTest(center, types: .featurePoint)` to get an estimated world position.
  If hit results are empty, fall back to projecting the camera ray to a default depth (1.5m):
  ```
  let ray = frame.camera.unprojectPoint(center, ontoPlane: ...) // or manual ray cast
  ```
  Simpler fallback: `let worldPos = frame.camera.transform.columns.3; let depth: Float = 1.5;
  let forward = -simd_float3(frame.camera.transform.columns.2.x, .y, .z);
  let pos = simd_float3(worldPos.x, worldPos.y, worldPos.z) + forward * depth`
- Check `anchorMap[label]`: if an existing anchor for this label is within 0.5m of the new pos,
  do nothing (same object). Otherwise, create `ARAnchor(name: "trace_\(label)", transform: ...)`
  and `session.add(anchor: newAnchor)`, then `anchorMap[label] = (newAnchor, pos)`.

`worldPosition(for:)`: return `anchorMap[label]?.1`.

`metadataSnapshot()`:
```swift
let anchors = anchorMap.map { (label, pair) in
    ["label": label, "x": pair.1.x, "y": pair.1.y, "z": pair.1.z]
}
return ["arkit_tracking": isTracking, "arkit_anchors": anchors]
```

`session(_:cameraDidChangeTrackingState:)`:
- `.normal` → `trackingStatus = "Tracking"`; `isTracking = true`
- `.limited(reason:)` → `trackingStatus = "Limited: \(reason)"`
- `.notAvailable` → `trackingStatus = "Not available"`

### EDIT: `trace-native-fastvlm/FastVLM App/ContentView.swift`

Two changes only:

1. **Start ARKit on launch.** In the `.task { }` block near the top of `body` (or alongside where
   `audioContext.start()` is called), add:
   ```swift
   TraceARKitEngine.shared.start()
   ```

2. **Save world map on background.** Find the `.onChange(of: scenePhase)` handler (or add one).
   When `scenePhase == .background`, add:
   ```swift
   TraceARKitEngine.shared.saveWorldMap()
   ```

3. **Include ARKit metadata in the POST.** In `postFrameToHub()` (the function that builds the
   metadata dict and POSTs to the brain), merge `TraceARKitEngine.shared.metadataSnapshot()`
   into the `meta` dict before posting:
   ```swift
   let arkitMeta = TraceARKitEngine.shared.metadataSnapshot()
   for (k, v) in arkitMeta { meta[k] = v }
   ```

4. **Place anchor when VLM detects an object.** After the VLM caption is generated and before
   `postFrameToHub()` is called, if a detected object label is available, call:
   ```swift
   if let frame = TraceARKitEngine.shared.session.currentFrame {
       TraceARKitEngine.shared.placeOrUpdateAnchor(label: topLabel, normalizedBox: topBox, in: frame)
   }
   ```
   Where `topLabel` is the primary VLM/detector label (use whatever variable holds the detected
   object label in the current frame path). If unsure, just call it with a placeholder like
   `"scene"` and the center box `CGRect(x: 0.25, y: 0.25, width: 0.5, height: 0.5)` — the
   anchor placement logic is what matters for P1, exact label binding is P3.

## P1 test (manual, needs phone — document in code comment)
Open app → point at desk → observe `trackingStatus` becomes "Tracking" + anchors appear in
ARKit metadata in the brain log → walk away → return → same anchor `world_xyz` within 0.5m of
original. Verify in `/tmp/trace_brain.log` that consecutive POSTs for the same label show
stable world_xyz values.

## Automated acceptance test (`tests/test_arkit_engine.py` — write this)
Since ARSession can't run in a test environment, mock the ARFrame/ARCamera. Test:
1. `placeOrUpdateAnchor` with a fake frame → anchor appears in `anchorMap`.
2. Second call within 0.5m → no new anchor added (still 1 anchor).
3. Call at >0.5m → second anchor added.
4. `metadataSnapshot()` returns dict with `"arkit_tracking"` key and `"arkit_anchors"` list.
5. `worldPosition(for: label)` returns correct coordinates.
Mock `ARSession` with a protocol or subclass; `ARFrame` with a simple struct stub.

## Guardrails
- ARKit runs ON iOS ONLY. Wrap all ARKit code in `#if os(iOS)` if the target might build on Mac.
  (This target is iOS-only, so it's fine, but be explicit.)
- `TraceARKitEngine.shared.session` is a `let` — do NOT replace it, only `run`/`pause` it.
- The existing `AVCaptureSession` in ContentView continues running. On iOS 18 / iPhone 17 these
  coexist. If there is a conflict at runtime (session error), log it and mark `isTracking = false`.
- No raw frames, no images, no camera data ever stored or transmitted — only the derived
  `world_xyz` floats in the metadata dict.
- Commit on branch. Report: "ARKit tracking state at first frame" + "anchor count after 10 frames".
