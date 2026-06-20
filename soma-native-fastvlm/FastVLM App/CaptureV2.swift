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

/// Ground-truth recorder for walk-2 capture-precision review. Self-data
/// only, founder-toggled; the file is pulled off-device afterwards and the
/// graph is audited frame-by-frame against what was actually in view.
final class GroundTruthRecorder {
    static let shared = GroundTruthRecorder()
    private let queue = DispatchQueue(label: "gt.recorder")
    private var writer: AVAssetWriter?
    private var input: AVAssetWriterInput?
    private var startTime: CMTime?
    private var frameCounter = 0
    private var enabledCache = false
    private(set) var currentURL: URL?

    static var toggleKey: String { "gtRecordingEnabled" }

    var isRecording: Bool { writer != nil }

    /// Call with every camera sample buffer; cheap when disabled.
    func ingest(_ sampleBuffer: CMSampleBuffer) {
        frameCounter += 1
        if frameCounter % 30 == 1 {
            enabledCache = UserDefaults.standard.bool(forKey: Self.toggleKey)
        }
        queue.async { [self] in
            if !enabledCache {
                if writer != nil { finishLocked() }
                return
            }
            guard let pixelBuffer = sampleBuffer.imageBuffer else { return }
            let pts = CMSampleBufferGetPresentationTimeStamp(sampleBuffer)
            if writer == nil { startLocked(pixelBuffer: pixelBuffer, at: pts) }
            guard let writer, let input, writer.status == .writing, input.isReadyForMoreMediaData else { return }
            input.append(sampleBuffer)
        }
    }

    private func startLocked(pixelBuffer: CVPixelBuffer, at pts: CMTime) {
        let dir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let url = dir.appendingPathComponent("walk_gt_\(Int(Date().timeIntervalSince1970)).mov")
        guard let w = try? AVAssetWriter(outputURL: url, fileType: .mov) else { return }
        let settings: [String: Any] = [
            AVVideoCodecKey: AVVideoCodecType.h264,
            AVVideoWidthKey: CVPixelBufferGetWidth(pixelBuffer),
            AVVideoHeightKey: CVPixelBufferGetHeight(pixelBuffer),
            AVVideoCompressionPropertiesKey: [AVVideoAverageBitRateKey: 4_000_000],
        ]
        let inp = AVAssetWriterInput(mediaType: .video, outputSettings: settings)
        inp.expectsMediaDataInRealTime = true
        guard w.canAdd(inp) else { return }
        w.add(inp)
        w.startWriting()
        w.startSession(atSourceTime: pts)
        writer = w
        input = inp
        startTime = pts
        currentURL = url
    }

    private func finishLocked() {
        guard let w = writer else { return }
        input?.markAsFinished()
        w.finishWriting { }
        writer = nil
        input = nil
        startTime = nil
    }

    var statusLine: String {
        guard isRecording, let url = currentURL else { return "GT off" }
        let size = ((try? FileManager.default.attributesOfItem(atPath: url.path)[.size]) as? Int64) ?? 0
        return "GT REC \(ByteCountFormatter.string(fromByteCount: size, countStyle: .file))"
    }
}
