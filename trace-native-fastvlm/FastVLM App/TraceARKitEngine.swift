#if os(iOS)
import ARKit
import Combine
import CoreGraphics
import Foundation
import simd

/// Runs an ARWorldTracking session in the background (no rendering).
/// Provides world-relative camera pose and persistent named anchors for detected objects.
///
/// P1 manual check on device:
/// 1. Launch the app and wait for `trackingStatus` to become `Tracking`.
/// 2. Point at a desk or other object until `arkit_anchors` appears in the brain log metadata.
/// 3. Walk away, return, and verify the same label stays within 0.5 m across consecutive posts.
@MainActor
final class TraceARKitEngine: NSObject, ObservableObject, ARSessionDelegate {

    static let shared = TraceARKitEngine()

    let session = ARSession()
    private var anchorMap: [String: (ARAnchor, simd_float3)] = [:]
    private var observedFrameCount = 0
    private var loggedFirstFrameState = false
    private var loggedTenFrameAnchorCount = false
    private var framesContinuation: AsyncStream<CMSampleBuffer>.Continuation?

    nonisolated private static let worldMapURL: URL = {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        return docs.appendingPathComponent("trace_arkit_worldmap.arworldmap")
    }()

    @Published var isTracking = false
    @Published var trackingStatus = "ARKit idle"

    private override init() {
        super.init()
    }

    /// Start (or resume) world tracking. Call on app foreground.
    func start() {
        guard ARWorldTrackingConfiguration.isSupported else {
            isTracking = false
            trackingStatus = "ARKit unsupported"
            print("[TraceARKitEngine] ARWorldTrackingConfiguration is not supported on this device")
            return
        }

        let config = ARWorldTrackingConfiguration()
        config.planeDetection = []
        config.environmentTexturing = .none
        config.isAutoFocusEnabled = false

        let savedMap = loadWorldMap()
        if let savedMap {
            config.initialWorldMap = savedMap
        }

        session.delegate = self
        observedFrameCount = 0
        loggedFirstFrameState = false
        loggedTenFrameAnchorCount = false
        session.run(config, options: savedMap != nil ? [] : [.resetTracking])
        isTracking = true
        trackingStatus = "ARKit starting"
    }

    /// Save ARWorldMap to disk. Call when app goes to background.
    func saveWorldMap() {
        let worldMapURL = Self.worldMapURL
        session.getCurrentWorldMap { map, error in
            if let error {
                print("[TraceARKitEngine] failed to fetch world map: \(error.localizedDescription)")
                return
            }
            guard let map else {
                print("[TraceARKitEngine] world map unavailable; nothing saved")
                return
            }
            do {
                let data = try NSKeyedArchiver.archivedData(withRootObject: map, requiringSecureCoding: true)
                try data.write(to: worldMapURL, options: .atomic)
                print("[TraceARKitEngine] saved world map to \(worldMapURL.path)")
            } catch {
                print("[TraceARKitEngine] failed to save world map: \(error.localizedDescription)")
            }
        }
    }

    /// Place or update a world anchor for a detected object label.
    /// `normalizedBox` is the object's bounding box in [0,1] image coordinates.
    /// `frame` is the current ARFrame from the running session.
    func placeOrUpdateAnchor(label: String, normalizedBox: CGRect, in frame: ARFrame) {
        let trimmedLabel = label.trimmingCharacters(in: .whitespacesAndNewlines)
        let anchorLabel = trimmedLabel.isEmpty ? "scene" : trimmedLabel
        let center = CGPoint(x: normalizedBox.midX, y: normalizedBox.midY)
        let worldPos = featurePointWorldPosition(at: center, in: frame) ?? fallbackWorldPosition(in: frame)

        if let existing = anchorMap[anchorLabel],
           simd_distance(existing.1, worldPos) <= 0.5 {
            return
        }

        let newAnchor = ARAnchor(name: "trace_\(anchorLabel)", transform: Self.translationMatrix(worldPos))
        session.add(anchor: newAnchor)
        anchorMap[anchorLabel] = (newAnchor, worldPos)
    }

    /// Current world position of an anchor for `label`, or nil if not yet anchored.
    func worldPosition(for label: String) -> simd_float3? {
        anchorMap[label]?.1
    }

    /// Mirror of CameraController.attach — ContentView feeds from ARKit frames instead of AVCaptureSession.
    func attach(continuation: AsyncStream<CMSampleBuffer>.Continuation) {
        framesContinuation = continuation
    }

    func detatch() {
        framesContinuation = nil
    }

    /// Snapshot for inclusion in each frame's metadata POST to the Mac brain.
    /// Returns dict with "arkit_tracking": Bool, "arkit_anchors": [{label, x, y, z}].
    func metadataSnapshot() -> [String: Any] {
        let anchors = anchorMap.keys.sorted().compactMap { label -> [String: Any]? in
            guard let pair = anchorMap[label] else { return nil }
            return [
                "label": label,
                "x": pair.1.x,
                "y": pair.1.y,
                "z": pair.1.z,
            ]
        }
        return [
            "arkit_tracking": isTracking,
            "arkit_tracking_status": trackingStatus,
            "arkit_anchors": anchors,
        ]
    }

    // MARK: - ARSessionDelegate

    nonisolated func session(_ session: ARSession, didUpdate frame: ARFrame) {
        Task { @MainActor in
            handleFrameUpdate(frame)
        }
    }

    nonisolated func session(_ session: ARSession, cameraDidChangeTrackingState camera: ARCamera) {
        Task { @MainActor in
            handleTrackingStateChange(camera)
        }
    }

    nonisolated func session(_ session: ARSession, didAdd anchors: [ARAnchor]) {
        Task { @MainActor in
            syncTrackedAnchors(anchors)
        }
    }

    nonisolated func session(_ session: ARSession, didUpdate anchors: [ARAnchor]) {
        Task { @MainActor in
            syncTrackedAnchors(anchors)
        }
    }

    nonisolated func session(_ session: ARSession, didRemove anchors: [ARAnchor]) {
        Task { @MainActor in
            let removedIDs = Set(anchors.map(\.identifier))
            anchorMap = anchorMap.filter { _, value in
                !removedIDs.contains(value.0.identifier)
            }
        }
    }

    nonisolated func session(_ session: ARSession, didFailWithError error: Error) {
        Task { @MainActor in
            isTracking = false
            trackingStatus = "Failed: \(error.localizedDescription)"
            print("[TraceARKitEngine] session failed: \(error.localizedDescription)")
        }
    }

    private func handleFrameUpdate(_ frame: ARFrame) {
        observedFrameCount += 1

        if !loggedFirstFrameState {
            loggedFirstFrameState = true
            print("[TraceARKitEngine] ARKit tracking state at first frame: \(trackingStateDescription(frame.camera.trackingState))")
        }

        if observedFrameCount >= 10, !loggedTenFrameAnchorCount {
            loggedTenFrameAnchorCount = true
            print("[TraceARKitEngine] anchor count after 10 frames: \(anchorMap.count)")
        }

        // Feed the captured image into the ContentView frame pipeline (replaces AVCaptureSession).
        if let continuation = framesContinuation,
           let sampleBuffer = Self.makeSampleBuffer(from: frame.capturedImage) {
            continuation.yield(sampleBuffer)
        }
    }

    private static func makeSampleBuffer(from pixelBuffer: CVPixelBuffer) -> CMSampleBuffer? {
        var formatDescription: CMFormatDescription?
        CMVideoFormatDescriptionCreateForImageBuffer(
            allocator: nil, imageBuffer: pixelBuffer, formatDescriptionOut: &formatDescription)
        guard let formatDescription else { return nil }
        var timingInfo = CMSampleTimingInfo(
            duration: CMTime(value: 1, timescale: 30),
            presentationTimeStamp: CMClockGetTime(CMClockGetHostTimeClock()),
            decodeTimeStamp: .invalid)
        var sampleBuffer: CMSampleBuffer?
        CMSampleBufferCreateReadyWithImageBuffer(
            allocator: nil, imageBuffer: pixelBuffer,
            formatDescription: formatDescription,
            sampleTiming: &timingInfo, sampleBufferOut: &sampleBuffer)
        return sampleBuffer
    }

    private func handleTrackingStateChange(_ camera: ARCamera) {
        switch camera.trackingState {
        case .normal:
            trackingStatus = "Tracking"
            isTracking = true
        case .limited(let reason):
            trackingStatus = "Limited: \(limitedReasonText(reason))"
            isTracking = false
        case .notAvailable:
            trackingStatus = "Not available"
            isTracking = false
        }
    }

    private func loadWorldMap() -> ARWorldMap? {
        guard FileManager.default.fileExists(atPath: Self.worldMapURL.path) else {
            return nil
        }
        do {
            let data = try Data(contentsOf: Self.worldMapURL)
            let map = try NSKeyedUnarchiver.unarchivedObject(ofClass: ARWorldMap.self, from: data)
            if map != nil {
                print("[TraceARKitEngine] loaded saved world map from \(Self.worldMapURL.path)")
            }
            return map
        } catch {
            print("[TraceARKitEngine] failed to load world map: \(error.localizedDescription)")
            return nil
        }
    }

    private func featurePointWorldPosition(at point: CGPoint, in frame: ARFrame) -> simd_float3? {
        let results = frame.hitTest(point, types: .featurePoint)
        guard let transform = results.first?.worldTransform else {
            return nil
        }
        return Self.position(from: transform)
    }

    private func fallbackWorldPosition(in frame: ARFrame) -> simd_float3 {
        let cameraTransform = frame.camera.transform
        let cameraPosition = Self.position(from: cameraTransform)
        let forwardColumn = cameraTransform.columns.2
        let forward = simd_normalize(simd_float3(-forwardColumn.x, -forwardColumn.y, -forwardColumn.z))
        return cameraPosition + forward * 1.5
    }

    private func syncTrackedAnchors(_ anchors: [ARAnchor]) {
        for anchor in anchors {
            guard let label = label(for: anchor) else { continue }
            anchorMap[label] = (anchor, Self.position(from: anchor.transform))
        }
    }

    private func label(for anchor: ARAnchor) -> String? {
        guard let name = anchor.name, name.hasPrefix("trace_") else {
            return nil
        }
        return String(name.dropFirst("trace_".count))
    }

    private func limitedReasonText(_ reason: ARCamera.TrackingState.Reason) -> String {
        switch reason {
        case .initializing:
            return "initializing"
        case .relocalizing:
            return "relocalizing"
        case .excessiveMotion:
            return "excessiveMotion"
        case .insufficientFeatures:
            return "insufficientFeatures"
        @unknown default:
            return "unknown"
        }
    }

    private func trackingStateDescription(_ state: ARCamera.TrackingState) -> String {
        switch state {
        case .normal:
            return "Tracking"
        case .limited(let reason):
            return "Limited: \(limitedReasonText(reason))"
        case .notAvailable:
            return "Not available"
        }
    }

    private static func position(from transform: simd_float4x4) -> simd_float3 {
        let column = transform.columns.3
        return simd_float3(column.x, column.y, column.z)
    }

    private static func translationMatrix(_ position: simd_float3) -> simd_float4x4 {
        var transform = matrix_identity_float4x4
        transform.columns.3 = simd_float4(position.x, position.y, position.z, 1)
        return transform
    }
}
#else
import Combine
import Foundation
import simd

@MainActor
final class TraceARKitEngine: ObservableObject {
    static let shared = TraceARKitEngine()

    @Published var isTracking = false
    @Published var trackingStatus = "ARKit unavailable on this platform"

    private init() {}

    func start() {}

    func saveWorldMap() {}

    func worldPosition(for label: String) -> simd_float3? { nil }

    func metadataSnapshot() -> [String: Any] {
        [
            "arkit_tracking": false,
            "arkit_tracking_status": trackingStatus,
            "arkit_anchors": [],
        ]
    }
}
#endif
