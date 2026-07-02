import CoreImage
import Foundation
#if os(iOS)
import UIKit
#endif
// MARK: - Payload models
struct Detection: Codable {
    let type: String
    let bbox: [CGFloat]
}

struct HubPayload: Codable {
    let objects: [Detection]
    let location_hint: [String: String]
}
#if os(macOS)
import AppKit
#endif

@MainActor
final class TraceDetectorBridge: ObservableObject {
    static let shared = TraceDetectorBridge()
    @Published var status = "Detector idle"
    @Published var lastMemoryText = ""

    #if os(macOS)
    private var process: Process?
    private var inputPipe: Pipe?
    private var outputPipe: Pipe?
    #endif
    private var outputBuffer = ""
    private var lastSubmittedAt = Date.distantPast
    private var startedAt = Date.distantPast
    private var isReady = false
    private let ciContext = CIContext()
    // Networking constants
    private let hubURL = URL(string: "http://localhost:8000/hub")!
    private let session = URLSession.shared

    func start() {
        #if os(macOS)
        guard process == nil else { return }

        let missing = TraceLocalRuntime.missingDetectorRequirements()
        guard missing.isEmpty else {
            status = "Detector unavailable: \(missing.joined(separator: "; "))"
            return
        }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: TraceLocalRuntime.detectorPython)
        process.currentDirectoryURL = URL(fileURLWithPath: TraceLocalRuntime.workspace)
        process.arguments = [
            "-m",
            "trace_perception.stream_worker",
            "--model",
            TraceLocalRuntime.detectorModel,
            "--confidence",
            "0.35",
        ]

        let inputPipe = Pipe()
        let outputPipe = Pipe()
        let errorPipe = Pipe()
        process.standardInput = inputPipe
        process.standardOutput = outputPipe
        process.standardError = errorPipe

        outputPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let text = String(data: data, encoding: .utf8) else { return }
            Task { @MainActor in
                self?.consumeDetectorOutput(text)
            }
        }
        errorPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let text = String(data: data, encoding: .utf8) else { return }
            Task { @MainActor in
                self?.status = "Detector stderr: \(text.trimmingCharacters(in: .whitespacesAndNewlines).prefix(160))"
            }
        }

        do {
            try process.run()
            self.process = process
            self.inputPipe = inputPipe
            self.outputPipe = outputPipe
            self.startedAt = Date()
            self.isReady = false
            status = "Detector running locally"
        } catch {
            status = "Detector failed to start: \(error.localizedDescription)"
        }
        #else
        status = "Detector worker unavailable on iOS build"
        #endif
    }

    func stop() {
        #if os(macOS)
        inputPipe?.fileHandleForWriting.closeFile()
        outputPipe?.fileHandleForReading.readabilityHandler = nil
        process?.terminate()
        process = nil
        inputPipe = nil
        outputPipe = nil
        isReady = false
        #endif
        status = "Detector stopped"
    }

    func submit(frame: CVImageBuffer) {
        #if os(macOS)
        guard process?.isRunning == true, let inputPipe else { return }
        guard isReady else {
            status = "Detector warming up"
            return
        }
        let now = Date()
        guard now.timeIntervalSince(lastSubmittedAt) >= 8 else { return }
        lastSubmittedAt = now

        guard let data = jpegData(from: frame) else {
            status = "Detector could not encode frame"
            return
        }

        var length = UInt32(data.count).bigEndian
        let header = Data(bytes: &length, count: MemoryLayout<UInt32>.size)

        do {
            try inputPipe.fileHandleForWriting.write(contentsOf: header)
            try inputPipe.fileHandleForWriting.write(contentsOf: data)
            status = "Detector frame submitted"
        } catch {
            status = "Detector write failed: \(error.localizedDescription)"
            stop()
        }
        #endif
    }

    private func consumeDetectorOutput(_ text: String) {
        outputBuffer.append(text)
        while let newline = outputBuffer.firstIndex(of: "\n") {
            let line = String(outputBuffer[..<newline])
            outputBuffer.removeSubrange(...newline)
            consumeDetectorLine(line)
        }
    }

    private func consumeDetectorLine(_ line: String) {
        guard let data = line.data(using: .utf8),
              let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return
        }

        if let message = payload["message"] as? String {
            status = "Detector error: \(message)"
            return
        }
        if payload["type"] as? String == "detector_ready" {
            isReady = true
            status = "Detector ready"
            return
        }

        let tracks = payload["tracks"] as? [[String: Any]] ?? []
        let events = payload["events"] as? [[String: Any]] ?? []
        status = "Detector tracks: \(tracks.count), events: \(events.count)"

        let eventMemory = events.compactMap(detectorMemoryLine)
        let trackMemory = tracks.compactMap(detectorTrackMemoryLine)
        let memory = (eventMemory.isEmpty ? trackMemory : eventMemory).joined(separator: "\n")
        if !memory.isEmpty {
            lastMemoryText = memory
        }
    }

    private func detectorMemoryLine(_ event: [String: Any]) -> String? {
        if let summary = event["summary_text"] as? String {
            let cleaned = summary.trimmingCharacters(in: .whitespacesAndNewlines)
            if cleaned.hasPrefix("OBJECT |") || cleaned.hasPrefix("EVENT |") {
                return cleaned
            }
        }

        guard let data = event["data"] as? [String: Any],
              let label = data["label"] as? String else {
            return nil
        }
        let color = (data["color"] as? String) ?? "unknown"
        let confidence = (event["confidence"] as? Double) ?? 0
        let certainty = confidence >= 0.55 ? "likely" : "uncertain"

        if label == "person" {
            let attributes = color == "unknown"
                ? "person detected by local tracker; body/upper body visible"
                : "person detected by local tracker; body/upper body visible; mostly \(color) upper-body clothing"
            return "OBJECT | visible person | \(attributes) | detector stream | \(certainty)"
        }

        let attributes = color == "unknown" ? "detected by local tracker" : "\(color) \(label) detected by local tracker"
        return "OBJECT | \(label) | \(attributes) | detector stream | \(certainty)"
    }

    private func detectorTrackMemoryLine(_ track: [String: Any]) -> String? {
        guard let label = track["label"] as? String else {
            return nil
        }
        let seenCount = (track["seen_count"] as? Int) ?? 0
        guard seenCount >= 3 else {
            return nil
        }

        let color = (track["color"] as? String) ?? "unknown"
        let confidence = (track["confidence"] as? Double) ?? 0
        let position = (track["frame_position"] as? String) ?? "visible frame"
        let areaRatio = (track["area_ratio"] as? Double) ?? 0
        let certainty = confidence >= 0.55 ? "likely" : "uncertain"
        let dominance = detectorDominance(areaRatio)
        let relation = "\(position); \(dominance); detector stream"

        if label == "person" {
            let attributes = color == "unknown"
                ? "person tracked by local detector; body/upper body visible"
                : "person tracked by local detector; body/upper body visible; mostly \(color) upper-body clothing"
            return "OBJECT | visible person | \(attributes) | \(relation) | \(certainty)"
        }

        let attributes = color == "unknown"
            ? "tracked by local detector"
            : "\(color) \(label) tracked by local detector"
        return "OBJECT | \(label) | \(attributes) | \(relation) | \(certainty)"
    }

    private func detectorDominance(_ areaRatio: Double) -> String {
        if areaRatio >= 0.35 {
            return "dominant foreground object"
        }
        if areaRatio >= 0.12 {
            return "large visible object"
        }
        if areaRatio >= 0.03 {
            return "medium visible object"
        }
        return "small visible object"
    }

    #if os(macOS)
    private func jpegData(from frame: CVImageBuffer) -> Data? {
        let ciImage = CIImage(cvPixelBuffer: frame)
        guard let cgImage = ciContext.createCGImage(ciImage, from: ciImage.extent) else {
            return nil
        }
        let bitmap = NSBitmapImageRep(cgImage: cgImage)
        return bitmap.representation(using: .jpeg, properties: [.compressionFactor: 0.55])
    }
    #endif
// MARK: - Helper to convert raw detections
private func makeDetections(from raw: [(String, Float, [Float])]) -> [Detection] {
    return raw
        .filter { $0.1 >= 0.5 }
        .map { (type, _, bbox) in
#if os(iOS)
            let normalized = bbox.map { CGFloat($0) / UIScreen.main.bounds.width }
            return Detection(type: type, bbox: normalized)
#else
            // Fallback: assume a default width of 640 pts for macOS
            let normalized = bbox.map { CGFloat($0) / 640.0 }
            return Detection(type: type, bbox: normalized)
#endif
        }
}

    // Provides a placeholder location hint dictionary for the HubPayload.
    private func locationHint() -> [String: String] {
        // TODO: Populate with actual location hint data if needed.
        return [:]
    }

// MARK: - Public API to send detections as JSON
func sendDetections(_ detections: [(String, Float, [Float])]) {
    let payload = HubPayload(objects: makeDetections(from: detections),
                             location_hint: locationHint())
    guard let jsonData = try? JSONEncoder().encode(payload) else { return }

    var request = URLRequest(url: hubURL)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.httpBody = jsonData

    session.dataTask(with: request) { data, response, error in
        if let err = error {
            print("⚠️ Hub POST error: \(err)")
            return
        }
        if let http = response as? HTTPURLResponse,
           !(200...299).contains(http.statusCode) {
            print("⚠️ Unexpected status: \(http.statusCode) \(HTTPURLResponse.localizedString(forStatusCode: http.statusCode))")
        }
    }.resume()
}
}

