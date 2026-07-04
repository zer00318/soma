//  VideoRecorder.swift
//  Explicit start/stop recorder for the full camera stream. The user controls when
//  recording begins and ends, and every finished capture is preserved locally as a
//  real .mov while also being uploaded to the Mac for later forensic analysis.

import AVFoundation
import Foundation

#if os(iOS)
import UIKit
#endif

public final class VideoRecorder {
    public static let shared = VideoRecorder()
    private init() {}

    private let queue = DispatchQueue(label: "trace.videoRecorder")
    private var writer: AVAssetWriter?
    private var input: AVAssetWriterInput?
    private var sessionStarted = false
    private(set) var outputURL: URL?
    private(set) var latestSavedURL: URL?
    private var frameCount = 0
    private var hubURL = ""
    private var recordingEnabled = false
    private var recordingID = ""
    /// Lock-free mirror of recordingEnabled for per-frame checks from the capture
    /// path. `isRecording` does queue.sync — calling that 60x/s from the main actor
    /// can stall behind an in-flight encoder append. A benign-race Bool cannot.
    public private(set) var isRecordingHint = false

    private static func recordingsDirectory() -> URL {
        let dir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("TraceCaptures", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true, attributes: nil)
        return dir
    }

    private static func makeRecordingID(now: Date = Date()) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyyMMdd_HHmmss"
        return formatter.string(from: now)
    }

    private static func fileURL(for recordingID: String) -> URL {
        recordingsDirectory().appendingPathComponent("trace_capture_\(recordingID).mov")
    }

    /// Configure the upload destination. Safe to call repeatedly when the hub URL changes.
    public func configure(hubURL: String) {
        queue.async { [self] in
            self.hubURL = hubURL
        }
    }

    public func startRecording(hubURL: String) {
        isRecordingHint = true
        queue.async { [self] in
            self.hubURL = hubURL
            guard !recordingEnabled else { return }
            recordingEnabled = true
            recordingID = Self.makeRecordingID()
            outputURL = Self.fileURL(for: recordingID)
            latestSavedURL = nil
            frameCount = 0
            sessionStarted = false
        }
    }

    public func stopRecording(upload: Bool = true, completion: @escaping (URL?, Int) -> Void) {
        isRecordingHint = false
        queue.async { [self] in
            guard recordingEnabled || writer != nil else {
                completion(nil, 0)
                return
            }
            recordingEnabled = false
            _finishCurrentRecording(upload: upload, completion: completion)
        }
    }

    /// Append every camera frame while explicit recording is enabled. Lazily starts the
    /// writer on the first frame so the stream defines dimensions + start time.
    public func append(_ sample: CMSampleBuffer) {
        queue.async { [self] in
            guard recordingEnabled else { return }
            if writer == nil { _start(with: sample) }
            guard let writer, let input, writer.status == .writing else { return }
            if !sessionStarted {
                writer.startSession(atSourceTime: CMSampleBufferGetPresentationTimeStamp(sample))
                sessionStarted = true
            }
            if input.isReadyForMoreMediaData {
                input.append(sample)
                frameCount += 1
            }
        }
    }

    private func _start(with sample: CMSampleBuffer) {
        guard let fmt = CMSampleBufferGetFormatDescription(sample) else { return }
        let dims = CMVideoFormatDescriptionGetDimensions(fmt)
        let url = outputURL ?? Self.fileURL(for: recordingID.isEmpty ? Self.makeRecordingID() : recordingID)
        try? FileManager.default.removeItem(at: url)
        guard let w = try? AVAssetWriter(outputURL: url, fileType: .mov) else { return }
        let settings: [String: Any] = [
            AVVideoCodecKey: AVVideoCodecType.h264,
            AVVideoWidthKey: Int(dims.width),
            AVVideoHeightKey: Int(dims.height),
        ]
        let inp = AVAssetWriterInput(mediaType: .video, outputSettings: settings)
        inp.expectsMediaDataInRealTime = true
        // Raw ARKit buffers arrive in sensor-landscape orientation; rotate at
        // PLAYBACK via metadata (free) instead of re-rendering pixels per frame.
        if dims.width > dims.height {
            inp.transform = CGAffineTransform(rotationAngle: .pi / 2)
        }
        if w.canAdd(inp) { w.add(inp) }
        w.startWriting()
        writer = w
        input = inp
        outputURL = url
        frameCount = 0
        sessionStarted = false
    }

    private func _finishCurrentRecording(
        upload: Bool,
        completion: @escaping (URL?, Int) -> Void
    ) {
        guard let writer, let input, writer.status == .writing, frameCount > 0 else {
            writer = nil
            input = nil
            outputURL = nil
            sessionStarted = false
            frameCount = 0
            recordingID = ""
            completion(nil, 0)
            return
        }
        let url = outputURL
        let n = frameCount
        input.markAsFinished()
        self.writer = nil
        self.input = nil
        self.sessionStarted = false
        self.outputURL = nil
        self.frameCount = 0
        self.recordingID = ""
        writer.finishWriting { [weak self] in
            guard writer.status == .completed, let url else {
                completion(nil, n)
                return
            }
            self?.queue.async {
                self?.latestSavedURL = url
            }
            if upload {
                self?._upload(url, frames: n, deleteAfterUpload: false)
            }
            completion(url, n)
        }
    }

    public func finish(_ completion: @escaping (URL?, Int) -> Void) {
        stopRecording(upload: false, completion: completion)
    }

    public var isRecording: Bool { queue.sync { recordingEnabled } }

    #if os(iOS)
    /// Final flush when the app backgrounds. If the user actively started a recording,
    /// preserve the finished movie locally and upload a copy before the app suspends.
    public func finishAndUpload(hubURL: String) {
        queue.async { [self] in self.hubURL = hubURL }
        var bgTask = UIBackgroundTaskIdentifier.invalid
        bgTask = UIApplication.shared.beginBackgroundTask(withName: "trace.video.upload") {
            if bgTask != .invalid { UIApplication.shared.endBackgroundTask(bgTask); bgTask = .invalid }
        }
        stopRecording(upload: true) { url, _ in
            func done() {
                if bgTask != .invalid { UIApplication.shared.endBackgroundTask(bgTask); bgTask = .invalid }
            }
            guard url != nil else { done(); return }
            done()
        }
    }

    /// POST one finalized capture to the Mac brain. The local movie remains on-device so
    /// the team can replay the exact session during postmortems.
    private func _upload(
        _ url: URL,
        frames n: Int,
        deleteAfterUpload: Bool,
        completion: (() -> Void)? = nil
    ) {
        let base = hubURL.isEmpty ? "http://127.0.0.1:8765" : hubURL
        guard let dest = URL(string: "\(base)/debug/video?frames=\(n)") else { completion?(); return }
        var req = URLRequest(url: dest)
        req.httpMethod = "POST"
        req.setValue("video/quicktime", forHTTPHeaderField: "Content-Type")
        req.setValue("dev-token", forHTTPHeaderField: "X-TRACE-Token")
        req.timeoutInterval = 300
        let task = URLSession.shared.uploadTask(with: req, fromFile: url) { _, _, _ in
            if deleteAfterUpload {
                try? FileManager.default.removeItem(at: url)
            }
            completion?()
        }
        task.resume()
    }
    #else
    private func _upload(
        _ url: URL,
        frames n: Int,
        deleteAfterUpload: Bool,
        completion: (() -> Void)? = nil
    ) { completion?() }
    #endif
}
