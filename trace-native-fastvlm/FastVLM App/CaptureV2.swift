// CaptureV2.swift — walk-1 capture overhaul (task #5).
//
// Walk-1 RAS -8.0 failure taxonomy, capture side:
//  - coarse scene classes → ObjectDetectorV2 (YOLO11n CoreML on ANE)
//  - walking stream-buffer OCR garbage → accurateOCR() on full-res stills
//    (still capture lives in CameraController.captureStill())
//  - no ground truth to audit capture precision → GroundTruthRecorder
//    (self-data video, walk-2 review protocol)
//  - observations carry no pose → PoseStamper (attitude quaternion +
//    battery), day-one insurance for the persistent spatial scene graph.

import AVFoundation
import CoreML
import Foundation
import Vision
#if os(iOS)
import CoreMotion
import UIKit
#endif

struct DetectedObjectV2 {
    let label: String
    let confidence: Float
    let box: CGRect
}

/// YOLO11n object detection (80 COCO classes — bicycle, bench, backpack…)
/// replacing whole-image scene classification as the object source.
final class ObjectDetectorV2 {
    static let shared = ObjectDetectorV2()
    private var vnModel: VNCoreMLModel?

    private init() {
        if let url = Bundle.main.url(forResource: "yolo11n", withExtension: "mlmodelc"),
           let model = try? MLModel(contentsOf: url) {
            vnModel = try? VNCoreMLModel(for: model)
        }
    }

    var isAvailable: Bool { vnModel != nil }

    func detect(_ frame: CVImageBuffer, minimumConfidence: Float = 0.40) -> [DetectedObjectV2] {
        guard let vnModel else { return [] }
        let request = VNCoreMLRequest(model: vnModel)
        request.imageCropAndScaleOption = .scaleFill
        let handler = VNImageRequestHandler(cvPixelBuffer: frame, orientation: .up)
        try? handler.perform([request])
        let observations = (request.results as? [VNRecognizedObjectObservation]) ?? []
        return observations.compactMap { obs in
            guard let top = obs.labels.first, top.confidence >= minimumConfidence else { return nil }
            return DetectedObjectV2(label: top.identifier, confidence: top.confidence, box: obs.boundingBox)
        }
    }
}

/// Read-only probe of the device's DEPTH capability. Touches NO capture session — it only
/// enumerates cameras and their depth-capable formats, so it cannot disturb the working video
/// pipeline. Result is posted once so we can decide whether dual-camera depth is even possible on
/// this specific (non-LiDAR) phone before risking any camera reconfiguration.
enum DepthProbe {
    static func report() -> String {
        #if os(iOS)
        let types: [AVCaptureDevice.DeviceType] = [
            .builtInDualCamera, .builtInDualWideCamera, .builtInTripleCamera,
            .builtInLiDARDepthCamera, .builtInTrueDepthCamera, .builtInWideAngleCamera,
        ]
        let disco = AVCaptureDevice.DiscoverySession(deviceTypes: types, mediaType: .video, position: .unspecified)
        var lines: [String] = []
        for d in disco.devices {
            let depthFmts = d.formats.filter { !$0.supportedDepthDataFormats.isEmpty }
            let posName = d.position == .back ? "back" : (d.position == .front ? "front" : "unspec")
            lines.append("\(d.localizedName)[\(d.deviceType.rawValue)] pos=\(posName) depthFormats=\(depthFmts.count)")
        }
        return "DEPTHPROBE | model=\(deviceModel()) | rearDepthCapable=\(disco.devices.contains { $0.position == .back && $0.formats.contains { !$0.supportedDepthDataFormats.isEmpty } }) | " + lines.joined(separator: " ;; ")
        #else
        return "DEPTHPROBE | not iOS"
        #endif
    }

    private static func deviceModel() -> String {
        var sysinfo = utsname(); uname(&sysinfo)
        let mirror = Mirror(reflecting: sysinfo.machine)
        return mirror.children.reduce(into: "") { acc, e in
            if let v = e.value as? Int8, v != 0 { acc.append(Character(UnicodeScalar(UInt8(v)))) }
        }
    }
}

// DepthReceiver lives in the Video target (CameraController.swift) so the camera code there can set
// it as the AVCaptureDepthDataOutput delegate; the App uses it via `import Video`. Moved out of the
// App target to fix a Video→App reference that never compiled.

/// MobileCLIP-S0 image encoder: an L2-normalized appearance embedding of an object crop, used to
/// RE-IDENTIFY a physical object after the camera pans away and back (so it keeps ONE track_id
/// instead of minting a new one each time IoU is lost). The model input is an image, so Vision
/// handles resize/normalization; we only crop to the detection box. Degrades safely to nil (re-ID
/// off) if the model is unavailable.
final class MobileClipEncoder {
    static let shared = MobileClipEncoder()
    private var vnModel: VNCoreMLModel?
    private init() {
        if let url = Bundle.main.url(forResource: "mobileclip_s0_image", withExtension: "mlmodelc"),
           let model = try? MLModel(contentsOf: url) {
            vnModel = try? VNCoreMLModel(for: model)
        }
    }
    var isAvailable: Bool { vnModel != nil }

    func embed(_ frame: CVPixelBuffer, box: CGRect) -> [Float]? {
        guard let vnModel else { return nil }
        let full = CIImage(cvPixelBuffer: frame)
        let W = full.extent.width, H = full.extent.height
        // Vision boundingBox: normalized, origin bottom-left — same convention as CIImage space.
        var rect = CGRect(x: box.minX * W, y: box.minY * H, width: box.width * W, height: box.height * H)
        rect = rect.intersection(full.extent)
        guard !rect.isNull, rect.width >= 8, rect.height >= 8 else { return nil }
        let crop = full.cropped(to: rect)
        let request = VNCoreMLRequest(model: vnModel)
        request.imageCropAndScaleOption = .centerCrop
        try? VNImageRequestHandler(ciImage: crop, options: [:]).perform([request])
        guard let obs = request.results?.first as? VNCoreMLFeatureValueObservation,
              let arr = obs.featureValue.multiArrayValue else { return nil }
        var v = [Float](repeating: 0, count: arr.count)
        for i in 0..<arr.count { v[i] = arr[i].floatValue }
        var norm: Float = 0; for x in v { norm += x * x }; norm = max(sqrt(norm), 1e-6)
        for i in 0..<v.count { v[i] /= norm }
        return v
    }
}

/// On-device object TRACKER with appearance RE-ID: associates per-frame YOLO detections into
/// persistent tracks so every observation of the same physical object shares a `track_id` — the
/// coordinate-free anchor the binder fuses on (ARKit world coords are unavailable on non-LiDAR
/// phones). Two-pass association: (1) IoU to RECENT same-label tracks; (2) for the rest, MobileCLIP
/// cosine re-ID against ANY same-label track (rescues pan-away-and-back). Conservative threshold:
/// prefers UNDER-merging (a little over-count) over collapsing two distinct objects into one.
final class TrackRegistry {
    static let shared = TrackRegistry()
    struct Assoc { let trackID: String; let det: DetectedObjectV2; let seenCount: Int }
    private struct Track { let id: String; var label: String; var box: CGRect; var lastSeen: Int; var seenCount: Int; var embedding: [Float]? }
    private var tracks: [Track] = []
    private var nextID = 1
    private let lock = NSLock()
    private let iouThreshold: CGFloat = 0.3
    private let recentFrames = 3          // IoU only trusts a track seen within this many ticks
    private let reidThreshold: Float = 0.90  // conservative — distinct objects rarely exceed this
    private let maxAgeFrames = 150        // keep lost tracks re-acquirable for ~30s at ~5 ticks/s

    func update(detections: [DetectedObjectV2], frameIndex: Int,
                embed: (DetectedObjectV2) -> [Float]?) -> [Assoc] {
        lock.lock(); defer { lock.unlock() }
        var result: [Assoc?] = Array(repeating: nil, count: detections.count)
        var used = Set<Int>()

        // Pass 1: IoU match to RECENT same-label tracks (cheap, no embedding).
        for (k, det) in detections.enumerated() {
            var bestIdx = -1; var bestIoU = iouThreshold
            for (i, t) in tracks.enumerated()
            where !used.contains(i) && t.label == det.label && frameIndex - t.lastSeen <= recentFrames {
                let v = TrackRegistry.iou(t.box, det.box)
                if v > bestIoU { bestIoU = v; bestIdx = i }
            }
            if bestIdx >= 0 {
                used.insert(bestIdx)
                tracks[bestIdx].box = det.box
                tracks[bestIdx].lastSeen = frameIndex
                tracks[bestIdx].seenCount += 1
                result[k] = Assoc(trackID: tracks[bestIdx].id, det: det, seenCount: tracks[bestIdx].seenCount)
            }
        }
        // Pass 2: appearance RE-ID for the unmatched — rescue a re-appearing object's id, else mint.
        for (k, det) in detections.enumerated() where result[k] == nil {
            let emb = embed(det)
            var bestIdx = -1; var bestSim = reidThreshold
            if let emb {
                for (i, t) in tracks.enumerated() where !used.contains(i) && t.label == det.label {
                    if let te = t.embedding {
                        let s = TrackRegistry.cosine(te, emb)
                        if s > bestSim { bestSim = s; bestIdx = i }
                    }
                }
            }
            if bestIdx >= 0 {
                used.insert(bestIdx)
                tracks[bestIdx].box = det.box
                tracks[bestIdx].lastSeen = frameIndex
                tracks[bestIdx].seenCount += 1
                if let emb { tracks[bestIdx].embedding = emb }
                result[k] = Assoc(trackID: tracks[bestIdx].id, det: det, seenCount: tracks[bestIdx].seenCount)
            } else {
                let id = "trk-\(nextID)"; nextID += 1
                tracks.append(Track(id: id, label: det.label, box: det.box, lastSeen: frameIndex, seenCount: 1, embedding: emb))
                used.insert(tracks.count - 1)
                result[k] = Assoc(trackID: id, det: det, seenCount: 1)
            }
        }
        tracks.removeAll { frameIndex - $0.lastSeen > maxAgeFrames }
        return result.compactMap { $0 }
    }

    static func iou(_ a: CGRect, _ b: CGRect) -> CGFloat {
        let i = a.intersection(b)
        if i.isNull || i.isEmpty { return 0 }
        let ia = i.width * i.height
        let ua = a.width * a.height + b.width * b.height - ia
        return ua > 0 ? ia / ua : 0
    }
    static func cosine(_ a: [Float], _ b: [Float]) -> Float {
        guard a.count == b.count, !a.isEmpty else { return 0 }
        var d: Float = 0; for i in 0..<a.count { d += a[i] * b[i] }
        return d  // inputs are already L2-normalized
    }
}

/// Accurate OCR pass for full-resolution stills — the antidote to walking
/// stream-buffer garbage. Use ONLY on dwell-triggered stills (expensive).
func accurateOCR(cgImage: CGImage) -> String {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    request.recognitionLanguages = ["en-US", "de-DE"]
    let handler = VNImageRequestHandler(cgImage: cgImage, orientation: .up)
    try? handler.perform([request])
    let lines = (request.results ?? []).compactMap { $0.topCandidates(1).first }
        .filter { $0.confidence >= 0.35 }
        .map { $0.string }
    return lines.joined(separator: "\n")
}

/// Latest device attitude + battery, stamped onto every perception packet.
/// Quaternion in the xArbitraryCorrectedZVertical reference frame — enough
/// to reconstruct camera orientation per observation for the spatial graph.
#if os(iOS)
final class PoseStamper {
    static let shared = PoseStamper()
    private let motion = CMMotionManager()
    private var latest: CMDeviceMotion?

    private init() {
        UIDevice.current.isBatteryMonitoringEnabled = true
        guard motion.isDeviceMotionAvailable else { return }
        motion.deviceMotionUpdateInterval = 0.2
        motion.startDeviceMotionUpdates(
            using: .xArbitraryCorrectedZVertical,
            to: OperationQueue()
        ) { [weak self] dm, _ in
            self?.latest = dm
        }
    }

    func snapshot() -> [String: Any] {
        var pose: [String: Any] = [:]
        if let dm = latest {
            let q = dm.attitude.quaternion
            pose["qw"] = round(q.w * 1000) / 1000
            pose["qx"] = round(q.x * 1000) / 1000
            pose["qy"] = round(q.y * 1000) / 1000
            pose["qz"] = round(q.z * 1000) / 1000
            pose["pitch"] = round(dm.attitude.pitch * 100) / 100
            pose["roll"] = round(dm.attitude.roll * 100) / 100
            pose["yaw"] = round(dm.attitude.yaw * 100) / 100
        }
        return pose
    }

    static var batteryPercent: Int {
        let level = UIDevice.current.batteryLevel
        return level >= 0 ? Int(level * 100) : -1
    }
}
#else
final class PoseStamper {
    static let shared = PoseStamper()

    private init() {}

    func snapshot() -> [String: Any] { [:] }

    static var batteryPercent: Int { -1 }
}
#endif

/// REMOVED from the production target (P0 honesty sprint). There is no
/// AVAssetWriter and no file-write path in this binary, so the no-raw-media
/// invariant is architectural, not a runtime toggle. Inert stub kept only so
/// `GroundTruthRecorder.toggleKey` / `.shared` still resolve.
final class GroundTruthRecorder {
    static let shared = GroundTruthRecorder()
    static var toggleKey: String { "gtRecordingEnabled" }
    var isRecording: Bool { false }
    var statusLine: String { "GT removed" }
    func ingest(_ sampleBuffer: CMSampleBuffer) { /* no-op: no raw capture in production */ }
}
