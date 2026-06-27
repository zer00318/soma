//  VideoRecorder.swift
//  Records the ENTIRE camera stream to a real video file (not sparse keyframes),
//  so the moment is captured continuously and can be worked with later. Taps the
//  raw 30fps sample-buffer stream via AVAssetWriter, independent of the slow
//  perception loop. On stop, the .mov is uploaded to the Mac.

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
    private var frameCount = 0

    private static var fileURL: URL {
        let dir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        return dir.appendingPathComponent("trace_capture.mov")
    }

    /// Append every camera frame. Lazily starts the writer on the first frame
    /// (so we get the real dimensions and start time from the stream itself).
    public func append(_ sample: CMSampleBuffer) {
        queue.async { [self] in
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
        let url = Self.fileURL
        try? FileManager.default.removeItem(at: url)
        guard let w = try? AVAssetWriter(outputURL: url, fileType: .mov) else { return }
        let settings: [String: Any] = [
            AVVideoCodecKey: AVVideoCodecType.h264,
            AVVideoWidthKey: Int(dims.width),
            AVVideoHeightKey: Int(dims.height),
        ]
        let inp = AVAssetWriterInput(mediaType: .video, outputSettings: settings)
        inp.expectsMediaDataInRealTime = true
        if w.canAdd(inp) { w.add(inp) }
        w.startWriting()
        writer = w
        input = inp
        outputURL = url
        frameCount = 0
        sessionStarted = false
    }

    /// Finalize the file and hand back its URL + frame count.
    public func finish(_ completion: @escaping (URL?, Int) -> Void) {
        queue.async { [self] in
            guard let writer, let input, writer.status == .writing else {
                completion(nil, 0); return
            }
            let n = frameCount
            input.markAsFinished()
            writer.finishWriting {
                let ok = writer.status == .completed
                let url = ok ? self.outputURL : nil
                self.writer = nil
                self.input = nil
                self.sessionStarted = false
                completion(url, n)
            }
        }
    }

    public var isRecording: Bool {
        queue.sync { writer != nil }
    }

    #if os(iOS)
    /// Finalize the recording and upload the full .mov to the Mac brain. Wrapped in
    /// a background task so a large file keeps uploading briefly after the app leaves.
    public func finishAndUpload(hubURL: String) {
        var bgTask = UIBackgroundTaskIdentifier.invalid
        bgTask = UIApplication.shared.beginBackgroundTask(withName: "trace.video.upload") {
            if bgTask != .invalid { UIApplication.shared.endBackgroundTask(bgTask); bgTask = .invalid }
        }
        finish { url, n in
            func done() {
                if bgTask != .invalid { UIApplication.shared.endBackgroundTask(bgTask); bgTask = .invalid }
            }
            guard let url else { done(); return }
            let base = hubURL.isEmpty ? "http://127.0.0.1:8765" : hubURL
            guard let dest = URL(string: "\(base)/debug/video?frames=\(n)") else { done(); return }
            var req = URLRequest(url: dest)
            req.httpMethod = "POST"
            req.setValue("video/quicktime", forHTTPHeaderField: "Content-Type")
            req.setValue("dev-token", forHTTPHeaderField: "X-TRACE-Token")
            req.timeoutInterval = 900
            let task = URLSession.shared.uploadTask(with: req, fromFile: url) { _, _, _ in done() }
            task.resume()
        }
    }
    #endif
}
