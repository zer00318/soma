import AVFoundation
import CryptoKit
import Foundation
import SwiftUI

#if os(iOS)
import ARKit
import Darwin
import UIKit

struct CaptureSessionSummary: Identifiable {
    let id: String
    let directoryName: String
    let url: URL
    let durationSeconds: TimeInterval
    let sizeBytes: Int64

    var durationMinutesText: String {
        String(format: "%.1f", durationSeconds / 60.0)
    }

    var sizeMBText: String {
        String(format: "%.0f", Double(sizeBytes) / 1_000_000.0)
    }

    var sizeGBText: String {
        String(format: "%.2f", Double(sizeBytes) / 1_000_000_000.0)
    }
}

@MainActor
final class CaptureModeRecorder: NSObject, ObservableObject, ARSessionDelegate {
    @Published var isRecording = false
    @Published var isFinalizing = false
    @Published var elapsedText = "00:00"
    @Published var fileSizeText = "0 MB"
    @Published var batteryText = "--"
    @Published var freeDiskText = "--"
    @Published var trackingState = "not running"
    @Published var wideFOVStatus = "wide-FOV stills off"
    @Published var wideFOVFallbackOff = false
    @Published var syncStatus = ""
    @Published var stopSummary = ""
    @Published var lastSummary: CaptureSessionSummary?

    let session = ARSession()

    private var captureID = ""
    private var captureDir: URL?
    private var videoURL: URL?
    private var audioURL: URL?
    private var posesURL: URL?
    private var metaURL: URL?
    private var wideDir: URL?
    private var writer: AVAssetWriter?
    private var writerInput: AVAssetWriterInput?
    private var pixelAdaptor: AVAssetWriterInputPixelBufferAdaptor?
    private var audioRecorder: AVAudioRecorder?
    private var poseHandle: FileHandle?
    private var setupStartedDate: Date?
    private var startDate: Date?
    private var stopDate: Date?
    private var audioStartedDate: Date?
    private var captureStartUptime: TimeInterval = 0
    private var firstFrameTimestamp: TimeInterval?
    private var firstVideoAppendedTimestamp: TimeInterval?
    private var lastVideoAppendedTimestamp: TimeInterval?
    private var lastPoseTimestamp: TimeInterval = -.infinity
    private var lastFrameTimestamp: TimeInterval = 0
    private var maxFrameGapSeconds: TimeInterval = 0
    private var poseStartSeconds: TimeInterval?
    private var poseEndSeconds: TimeInterval?
    private var audioStartOffsetSeconds: TimeInterval = 0
    private var audioDurationSeconds: TimeInterval = 0
    private var audioRecorded = false
    private var audioError = ""
    private var rawFileHashes: [String: String] = [:]
    private var captureIdentitySHA256 = ""
    private var frameCount = 0
    private var appendedVideoFrames = 0
    private var droppedVideoFrames = 0
    private var poseCount = 0
    private var stillCount = 0
    private var batteryStart = -1
    private var batteryStop = -1
    private var selectedVideoFormat = "default"
    private var cameraResolution = ""
    private var fov: [String: Double] = [:]
    private var thermalSamples: [[String: Any]] = []
    private var uiTask: Task<Void, Never>?
    private var thermalTask: Task<Void, Never>?
    private var wideStillTask: Task<Void, Never>?
    private var wideSession: AVCaptureMultiCamSession?
    private var widePhotoOutput: AVCapturePhotoOutput?
    private var widePhotoDelegates: [CaptureWidePhotoDelegate] = []

    override init() {
        super.init()
        UIDevice.current.isBatteryMonitoringEnabled = true
        loadMostRecentCapture()
        refreshMetrics()
    }

    func start(requestWideFOVStills: Bool) {
        guard !isRecording, !isFinalizing else { return }
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .notDetermined:
            stopSummary = "microphone permission required for complete capture"
            AVCaptureDevice.requestAccess(for: .audio) { [weak self] granted in
                Task { @MainActor in
                    guard let self else { return }
                    if granted {
                        self.start(requestWideFOVStills: requestWideFOVStills)
                    } else {
                        self.stopSummary = "capture not started: microphone permission denied"
                    }
                }
            }
            return
        case .denied, .restricted:
            stopSummary = "capture not started: microphone permission denied"
            return
        case .authorized:
            break
        @unknown default:
            stopSummary = "capture not started: microphone permission unavailable"
            return
        }

        resetRunState()
        let start = Date()
        setupStartedDate = start
        let id = "capture_\(Self.directoryTimestamp.string(from: start))"
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let dir = documents.appendingPathComponent(id, isDirectory: true)
        let poses = dir.appendingPathComponent("poses.ndjson")
        let video = dir.appendingPathComponent("video.mov")
        let audio = dir.appendingPathComponent("audio.m4a")
        let meta = dir.appendingPathComponent("meta.json")
        let wide = dir.appendingPathComponent("wide", isDirectory: true)

        do {
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            try FileManager.default.createDirectory(at: wide, withIntermediateDirectories: true)
            FileManager.default.createFile(atPath: poses.path, contents: nil)
            poseHandle = try FileHandle(forWritingTo: poses)
        } catch {
            stopSummary = "capture setup failed: \(error.localizedDescription)"
            return
        }

        captureID = id
        captureDir = dir
        posesURL = poses
        videoURL = video
        audioURL = audio
        metaURL = meta
        wideDir = wide
        batteryStart = Self.batteryPercent()
        batteryText = "\(batteryStart)%"

        let config = ARWorldTrackingConfiguration()
        config.worldAlignment = .gravity
        config.planeDetection = []
        if let bestFormat = Self.highestResolutionFormat() {
            config.videoFormat = bestFormat
            let size = bestFormat.imageResolution
            selectedVideoFormat = "\(Int(size.width))x\(Int(size.height)) @ \(bestFormat.framesPerSecond)fps"
        }
        session.delegate = self
        session.run(config, options: [.resetTracking, .removeExistingAnchors])

        guard startAudioRecording(at: audio) else {
            session.pause()
            poseHandle?.closeFile()
            poseHandle = nil
            let reason = audioError.isEmpty ? "unknown audio recorder error" : audioError
            try? FileManager.default.removeItem(at: dir)
            resetRunState()
            stopSummary = "capture setup failed: \(reason)"
            return
        }

        // The experience clock starts only when the raw channels are armed and frame acceptance
        // is enabled. Setup/permission latency is recorded separately and cannot create a false
        // video-tail failure.
        captureStartUptime = ProcessInfo.processInfo.systemUptime
        let captureStart = Date()
        startDate = captureStart
        audioStartOffsetSeconds = audioStartedDate?.timeIntervalSince(captureStart) ?? 0
        isRecording = true
        appendThermalSample(label: "start")
        writeMeta(final: false)
        trackingState = "initializing"
        stopSummary = ""
        refreshMetrics()
        startMetricLoop()
        startThermalLoop()
        if requestWideFOVStills {
            startWideFOVStills()
        } else {
            wideFOVStatus = "wide-FOV stills off"
        }
    }

    func stop() {
        guard isRecording else { return }
        isRecording = false
        isFinalizing = true
        stopDate = Date()
        finishAudioRecording()
        uiTask?.cancel()
        thermalTask?.cancel()
        wideStillTask?.cancel()
        uiTask = nil
        thermalTask = nil
        wideStillTask = nil
        stopWideFOVStills()
        session.pause()
        appendThermalSample(label: "stop")
        batteryStop = Self.batteryPercent()
        poseHandle?.closeFile()
        poseHandle = nil
        writerInput?.markAsFinished()

        guard let writer else {
            finishStoppedCaptureAfterHashing()
            return
        }
        writer.finishWriting { [weak self] in
            Task { @MainActor in
                self?.finishStoppedCaptureAfterHashing()
            }
        }
    }

    func loadMostRecentCapture() {
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        guard let urls = try? FileManager.default.contentsOfDirectory(
            at: documents,
            includingPropertiesForKeys: [.contentModificationDateKey],
            options: [.skipsHiddenFiles]
        ) else { return }
        let captures = urls
            .filter { $0.lastPathComponent.hasPrefix("capture_") }
            .sorted {
                let lhs = ((try? $0.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast)
                let rhs = ((try? $1.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast)
                return lhs > rhs
            }
        guard let latest = captures.first else { return }
        lastSummary = summary(for: latest)
    }

    func syncLatest(to hubURL: String) {
        guard !isRecording, !isFinalizing else { return }
        guard let summary = lastSummary else {
            syncStatus = "no capture session to sync"
            return
        }
        let durationMinutes = summary.durationSeconds / 60.0
        let sizeMB = Double(summary.sizeBytes) / 1_000_000.0
        let memoryText = "CAPTURE | \(summary.directoryName) | \(String(format: "%.1f", durationMinutes))min | \(String(format: "%.0f", sizeMB))MB"
        var metadata = loadMeta(for: summary.url)
        metadata["capture_mode"] = "capture_session"
        metadata["capture_dir"] = summary.directoryName
        metadata["duration_minutes"] = durationMinutes
        metadata["size_mb"] = sizeMB
        metadata["file_transfer"] = "devicectl_pull_only"
        metadata["build"] = BuildStamp.sha

        let payload: [String: Any] = [
            "timestamp": Self.iso.string(from: Date()),
            "source_type": "vision",
            "source": "capture_session",
            "provider": "capture_session",
            "scene_phase": "capture_session",
            "confidence": 1.0,
            "stability_count": 1,
            "active_entity_labels": [],
            "memory_text": memoryText,
            "metadata": metadata,
        ]
        guard JSONSerialization.isValidJSONObject(payload),
              let body = try? JSONSerialization.data(withJSONObject: payload) else {
            syncStatus = "sync failed: invalid metadata"
            return
        }
        let baseURL = hubURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            ? "http://127.0.0.1:8765"
            : hubURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: "\(baseURL)/capture/perception") else {
            syncStatus = "sync failed: bad hub URL"
            return
        }
        syncStatus = "syncing metadata..."
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("dev-token", forHTTPHeaderField: "X-SOMA-Token")
        request.httpBody = body
        URLSession.shared.dataTask(with: request) { _, response, error in
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            Task { @MainActor in
                if error == nil, (200..<300).contains(status) {
                    self.syncStatus = "metadata synced; pull files with devicectl"
                } else if let error {
                    self.syncStatus = "sync failed: \(error.localizedDescription)"
                } else {
                    self.syncStatus = "sync failed: HTTP \(status)"
                }
            }
        }.resume()
    }

    nonisolated func session(_ session: ARSession, didUpdate frame: ARFrame) {
        Task { @MainActor in
            self.handle(frame: frame)
        }
    }

    private func handle(frame: ARFrame) {
        guard isRecording else { return }
        // AR callbacks queued during setup may execute after isRecording flips true. Reject those
        // pre-arm buffers by their source clock so video duration cannot begin before start_ts.
        guard frame.timestamp >= captureStartUptime else { return }
        if lastFrameTimestamp > 0 {
            maxFrameGapSeconds = max(maxFrameGapSeconds, frame.timestamp - lastFrameTimestamp)
        }
        lastFrameTimestamp = frame.timestamp
        frameCount += 1
        trackingState = Self.trackingDescription(frame.camera.trackingState)

        if writer == nil {
            startVideoWriter(pixelBuffer: frame.capturedImage, frameTimestamp: frame.timestamp, camera: frame.camera)
        }
        appendVideoFrame(frame.capturedImage, frameTimestamp: frame.timestamp)

        if frame.timestamp - lastPoseTimestamp >= 0.095 {
            lastPoseTimestamp = frame.timestamp
            appendPose(frame: frame)
        }
    }

    private func startVideoWriter(pixelBuffer: CVPixelBuffer, frameTimestamp: TimeInterval, camera: ARCamera) {
        guard let videoURL else { return }
        try? FileManager.default.removeItem(at: videoURL)
        let width = CVPixelBufferGetWidth(pixelBuffer)
        let height = CVPixelBufferGetHeight(pixelBuffer)
        cameraResolution = "\(width)x\(height)"
        fov = Self.fieldOfView(width: width, height: height, intrinsics: camera.intrinsics)
        firstFrameTimestamp = frameTimestamp

        do {
            let writer = try AVAssetWriter(outputURL: videoURL, fileType: .mov)
            let settings: [String: Any] = [
                AVVideoCodecKey: AVVideoCodecType.h264,
                AVVideoWidthKey: width,
                AVVideoHeightKey: height,
                AVVideoCompressionPropertiesKey: [
                    AVVideoAverageBitRateKey: 12_000_000,
                    AVVideoProfileLevelKey: AVVideoProfileLevelH264HighAutoLevel,
                ],
            ]
            let input = AVAssetWriterInput(mediaType: .video, outputSettings: settings)
            input.expectsMediaDataInRealTime = true
            let adaptor = AVAssetWriterInputPixelBufferAdaptor(
                assetWriterInput: input,
                sourcePixelBufferAttributes: [
                    kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_420YpCbCr8BiPlanarFullRange,
                    kCVPixelBufferWidthKey as String: width,
                    kCVPixelBufferHeightKey as String: height,
                ]
            )
            guard writer.canAdd(input) else { return }
            writer.add(input)
            writer.startWriting()
            writer.startSession(atSourceTime: .zero)
            self.writer = writer
            writerInput = input
            pixelAdaptor = adaptor
            writeMeta(final: false)
        } catch {
            stopSummary = "video writer failed: \(error.localizedDescription)"
        }
    }

    private func appendVideoFrame(_ pixelBuffer: CVPixelBuffer, frameTimestamp: TimeInterval) {
        guard let firstFrameTimestamp,
              let writer,
              let writerInput,
              let pixelAdaptor,
              writer.status == .writing else { return }
        guard writerInput.isReadyForMoreMediaData else {
            droppedVideoFrames += 1
            return
        }
        let pts = CMTime(seconds: max(0, frameTimestamp - firstFrameTimestamp), preferredTimescale: 600)
        if pixelAdaptor.append(pixelBuffer, withPresentationTime: pts) {
            if firstVideoAppendedTimestamp == nil {
                firstVideoAppendedTimestamp = frameTimestamp
            }
            lastVideoAppendedTimestamp = frameTimestamp
            appendedVideoFrames += 1
        } else {
            droppedVideoFrames += 1
        }
    }

    private func appendPose(frame: ARFrame) {
        guard let firstFrameTimestamp else { return }
        let t = max(0, frame.timestamp - firstFrameTimestamp)
        if poseStartSeconds == nil { poseStartSeconds = t }
        poseEndSeconds = t
        let payload: [String: Any] = [
            "t": round(t * 1000) / 1000,
            "transform": Self.matrix4(frame.camera.transform),
            "intrinsics": Self.matrix3(frame.camera.intrinsics),
            "tracking_state": Self.trackingDescription(frame.camera.trackingState),
        ]
        guard let data = try? JSONSerialization.data(withJSONObject: payload),
              var line = String(data: data, encoding: .utf8) else { return }
        line.append("\n")
        try? poseHandle?.write(contentsOf: Data(line.utf8))
        poseCount += 1
    }

    private func finishStoppedCaptureAfterHashing() {
        let files = [
            "video.mov": videoURL,
            "audio.m4a": audioURL,
            "poses.ndjson": posesURL,
        ].compactMapValues { $0 }
        Task { [weak self] in
            let hashes = await Task.detached(priority: .utility) {
                Self.hashRawFiles(files)
            }.value
            guard let self else { return }
            self.rawFileHashes = hashes
            self.captureIdentitySHA256 = Self.captureIdentity(for: hashes)
            self.finishStoppedCapture()
        }
    }

    private func finishStoppedCapture() {
        refreshMetrics()
        writeMeta(final: true)
        if let captureDir {
            lastSummary = summary(for: captureDir)
        }
        if let summary = lastSummary {
            stopSummary = "captured \(summary.durationMinutesText) min, \(summary.sizeGBText) GB, ready to sync"
        } else {
            stopSummary = "capture finalized, ready to sync"
        }
        writer = nil
        writerInput = nil
        pixelAdaptor = nil
        isFinalizing = false
    }

    private func resetRunState() {
        captureID = ""
        captureDir = nil
        videoURL = nil
        audioURL = nil
        posesURL = nil
        metaURL = nil
        wideDir = nil
        writer = nil
        writerInput = nil
        pixelAdaptor = nil
        audioRecorder = nil
        poseHandle = nil
        setupStartedDate = nil
        startDate = nil
        stopDate = nil
        audioStartedDate = nil
        captureStartUptime = 0
        firstFrameTimestamp = nil
        firstVideoAppendedTimestamp = nil
        lastVideoAppendedTimestamp = nil
        lastPoseTimestamp = -.infinity
        lastFrameTimestamp = 0
        maxFrameGapSeconds = 0
        poseStartSeconds = nil
        poseEndSeconds = nil
        audioStartOffsetSeconds = 0
        audioDurationSeconds = 0
        audioRecorded = false
        audioError = ""
        rawFileHashes = [:]
        captureIdentitySHA256 = ""
        frameCount = 0
        appendedVideoFrames = 0
        droppedVideoFrames = 0
        poseCount = 0
        stillCount = 0
        batteryStart = -1
        batteryStop = -1
        selectedVideoFormat = "default"
        cameraResolution = ""
        fov = [:]
        thermalSamples = []
        wideFOVFallbackOff = false
        wideFOVStatus = "wide-FOV stills off"
    }

    private func startAudioRecording(at url: URL) -> Bool {
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.record, mode: .measurement, options: [])
            try session.setActive(true)
            let settings: [String: Any] = [
                AVFormatIDKey: kAudioFormatMPEG4AAC,
                AVSampleRateKey: 48_000,
                AVNumberOfChannelsKey: 1,
                AVEncoderBitRateKey: 128_000,
                AVEncoderAudioQualityKey: AVAudioQuality.high.rawValue,
            ]
            let recorder = try AVAudioRecorder(url: url, settings: settings)
            guard recorder.prepareToRecord(), recorder.record() else {
                audioError = "microphone recorder did not start"
                try? session.setActive(false)
                return false
            }
            audioStartedDate = Date()
            audioRecorder = recorder
            audioRecorded = true
            return true
        } catch {
            audioError = error.localizedDescription
            return false
        }
    }

    private func finishAudioRecording() {
        guard let recorder = audioRecorder else {
            audioRecorded = false
            return
        }
        // AVAudioRecorder.stop() synchronously closes/finalizes the M4A. Final meta is written
        // only later, after the video writer's asynchronous finishWriting callback completes.
        audioDurationSeconds = max(0, recorder.currentTime)
        recorder.stop()
        audioRecorder = nil
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        if let audioURL {
            audioRecorded = audioDurationSeconds > 0 && FileManager.default.fileExists(atPath: audioURL.path)
        } else {
            audioRecorded = false
        }
    }

    private func startMetricLoop() {
        uiTask?.cancel()
        uiTask = Task { [weak self] in
            while !Task.isCancelled {
                self?.refreshMetrics()
                try? await Task.sleep(nanoseconds: 1_000_000_000)
            }
        }
    }

    private func startThermalLoop() {
        thermalTask?.cancel()
        thermalTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 60_000_000_000)
                guard !Task.isCancelled else { return }
                self?.appendThermalSample(label: "minute")
                self?.writeMeta(final: false)
            }
        }
    }

    private func refreshMetrics() {
        let elapsed = startDate.map { Date().timeIntervalSince($0) } ?? 0
        elapsedText = Self.durationText(elapsed)
        batteryText = "\(Self.batteryPercent())%"
        freeDiskText = Self.byteText(Self.freeDiskBytes())
        if let captureDir {
            fileSizeText = Self.byteText(Self.directorySize(captureDir))
        } else {
            fileSizeText = "0 MB"
        }
    }

    private func appendThermalSample(label: String) {
        thermalSamples.append([
            "ts": Self.iso.string(from: Date()),
            "label": label,
            "state": Self.thermalStateText(ProcessInfo.processInfo.thermalState),
        ])
    }

    private func writeMeta(final: Bool) {
        guard let metaURL, let captureDir, let startDate else { return }
        let sizeBytes = Self.directorySize(captureDir)
        // Freeze the experience duration at the user's Stop tap. Container finalization may take
        // additional wall time, but it must not masquerade as missing captured tail.
        let duration = (stopDate ?? Date()).timeIntervalSince(startDate)
        let videoDuration = max(
            0,
            (lastVideoAppendedTimestamp ?? firstVideoAppendedTimestamp ?? 0)
                - (firstVideoAppendedTimestamp ?? 0)
        )
        let poseEnd = poseEndSeconds ?? 0
        let integrity = integritySummary(
            final: final,
            wallDuration: duration,
            videoDuration: videoDuration,
            poseEnd: poseEnd
        )
        let meta: [String: Any] = [
            "capture_id": captureID,
            "setup_started_ts": setupStartedDate.map { Self.iso.string(from: $0) } ?? "",
            "start_ts": Self.iso.string(from: startDate),
            "updated_ts": Self.iso.string(from: Date()),
            "final": final,
            "device_model": Self.deviceModelIdentifier(),
            "device_name": UIDevice.current.name,
            "system_name": UIDevice.current.systemName,
            "system_version": UIDevice.current.systemVersion,
            "app_build_sha": BuildStamp.sha,
            "video_file": "video.mov",
            "audio_file": "audio.m4a",
            "poses_file": "poses.ndjson",
            "video_format": selectedVideoFormat,
            "camera_resolution": cameraResolution,
            "fov": fov,
            "duration_seconds": duration,
            "video_first_source_timestamp_seconds": firstVideoAppendedTimestamp as Any? ?? NSNull(),
            "video_last_source_timestamp_seconds": lastVideoAppendedTimestamp as Any? ?? NSNull(),
            "video_duration_seconds": videoDuration,
            "max_frame_gap_seconds": maxFrameGapSeconds,
            "appended_video_frames": appendedVideoFrames,
            "audio_recorded": audioRecorded,
            "audio_start_offset_seconds": audioStartOffsetSeconds,
            "audio_duration_seconds": audioDurationSeconds,
            "audio_error": audioError,
            "pose_start_seconds": poseStartSeconds as Any? ?? NSNull(),
            "pose_end_seconds": poseEnd,
            "size_bytes": sizeBytes,
            "frame_count": frameCount,
            "dropped_video_frames": droppedVideoFrames,
            "pose_count": poseCount,
            "writer_status": Self.writerStatusText(writer?.status),
            "writer_error": writer?.error?.localizedDescription ?? "",
            "raw_file_sha256": rawFileHashes,
            "capture_identity_sha256": captureIdentitySHA256,
            "battery_start_pct": batteryStart,
            "battery_stop_pct": final ? batteryStop : NSNull(),
            "thermal": thermalSamples,
            "wide_fov_stills": [
                "requested": wideSession != nil || stillCount > 0 || wideFOVStatus != "wide-FOV stills off",
                "active": wideSession?.isRunning == true,
                "status": wideFOVStatus,
                "count": stillCount,
                "directory": "wide",
            ],
            "pull_command": Self.pullCommand(directoryName: captureDir.lastPathComponent),
            "integrity": integrity,
        ]
        guard JSONSerialization.isValidJSONObject(meta),
              let data = try? JSONSerialization.data(withJSONObject: meta, options: [.prettyPrinted, .sortedKeys]) else {
            return
        }
        try? data.write(to: metaURL, options: [.atomic])
    }

    private func integritySummary(
        final: Bool,
        wallDuration: TimeInterval,
        videoDuration: TimeInterval,
        poseEnd: TimeInterval
    ) -> [String: Any] {
        let videoTailGap = max(0, wallDuration - videoDuration)
        let audioEnd = audioStartOffsetSeconds + audioDurationSeconds
        let audioTailGap = max(0, videoDuration - audioEnd)
        let poseTailGap = max(0, videoDuration - poseEnd)
        var issues: [String] = []
        if final {
            if writer?.status != .completed { issues.append("video_writer_not_completed") }
            if appendedVideoFrames == 0 || videoDuration <= 0 { issues.append("video_evidence_missing") }
            if droppedVideoFrames > 0 { issues.append("video_frames_dropped") }
            if maxFrameGapSeconds > 0.25 { issues.append("video_timeline_gap") }
            if videoTailGap > 0.75 { issues.append("video_tail_missing") }
            if !audioRecorded { issues.append("audio_evidence_missing") }
            if abs(audioStartOffsetSeconds) > 0.75 { issues.append("audio_start_late") }
            if audioTailGap > 0.75 { issues.append("audio_tail_missing") }
            if poseCount == 0 { issues.append("pose_evidence_missing") }
            if poseTailGap > 0.5 { issues.append("pose_tail_missing") }
            if rawFileHashes.count != 3 || captureIdentitySHA256.count != 64 {
                issues.append("raw_hash_missing")
            }
        }
        return [
            "status": final ? (issues.isEmpty ? "complete" : "incomplete") : "recording",
            "complete": final && issues.isEmpty,
            "issues": issues,
            "video_tail_gap_seconds": videoTailGap,
            "audio_tail_gap_seconds": audioTailGap,
            "pose_tail_gap_seconds": poseTailGap,
            "max_frame_gap_seconds": maxFrameGapSeconds,
            "raw_channels": ["video", "audio", "pose"],
        ]
    }

    private func summary(for dir: URL) -> CaptureSessionSummary {
        let metaURL = dir.appendingPathComponent("meta.json")
        var duration: TimeInterval = 0
        if let data = try? Data(contentsOf: metaURL),
           let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let seconds = json["duration_seconds"] as? Double {
            duration = seconds
        }
        return CaptureSessionSummary(
            id: dir.lastPathComponent,
            directoryName: dir.lastPathComponent,
            url: dir,
            durationSeconds: duration,
            sizeBytes: Self.directorySize(dir)
        )
    }

    private func loadMeta(for dir: URL) -> [String: Any] {
        let metaURL = dir.appendingPathComponent("meta.json")
        guard let data = try? Data(contentsOf: metaURL),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return [
                "pull_command": Self.pullCommand(directoryName: dir.lastPathComponent),
            ]
        }
        return json
    }

    private func startWideFOVStills() {
        guard AVCaptureMultiCamSession.isMultiCamSupported else {
            markWideFOVUnavailable("unavailable with AR tracking")
            return
        }
        let discovery = AVCaptureDevice.DiscoverySession(
            deviceTypes: [.builtInUltraWideCamera],
            mediaType: .video,
            position: .back
        )
        guard let ultraWide = discovery.devices.first else {
            markWideFOVUnavailable("unavailable: no ultrawide camera")
            return
        }
        do {
            let session = AVCaptureMultiCamSession()
            let input = try AVCaptureDeviceInput(device: ultraWide)
            let output = AVCapturePhotoOutput()
            guard session.canAddInput(input), session.canAddOutput(output) else {
                markWideFOVUnavailable("unavailable with AR tracking")
                return
            }
            session.beginConfiguration()
            session.addInput(input)
            session.addOutput(output)
            output.maxPhotoQualityPrioritization = .quality
            session.commitConfiguration()
            session.startRunning()
            guard session.isRunning else {
                markWideFOVUnavailable("unavailable with AR tracking")
                return
            }
            wideSession = session
            widePhotoOutput = output
            wideFOVStatus = "wide-FOV stills on"
            startWideStillLoop()
        } catch {
            markWideFOVUnavailable("unavailable with AR tracking")
        }
    }

    private func startWideStillLoop() {
        wideStillTask?.cancel()
        wideStillTask = Task { [weak self] in
            while !Task.isCancelled {
                self?.captureWideStill()
                try? await Task.sleep(nanoseconds: 2_000_000_000)
            }
        }
    }

    private func captureWideStill() {
        guard isRecording,
              let wideDir,
              let output = widePhotoOutput,
              wideSession?.isRunning == true else { return }
        let filename = "\(Self.directoryTimestamp.string(from: Date()))_\(stillCount + 1).jpg"
        let url = wideDir.appendingPathComponent(filename)
        let settings: AVCapturePhotoSettings
        if output.availablePhotoCodecTypes.contains(.jpeg) {
            settings = AVCapturePhotoSettings(format: [AVVideoCodecKey: AVVideoCodecType.jpeg])
        } else {
            settings = AVCapturePhotoSettings()
        }
        settings.photoQualityPrioritization = output.maxPhotoQualityPrioritization
        let delegate = CaptureWidePhotoDelegate(url: url) { [weak self] ok in
            Task { @MainActor in
                guard let self else { return }
                if ok { self.stillCount += 1 }
                self.widePhotoDelegates.removeAll { $0.finished }
                self.writeMeta(final: false)
            }
        }
        widePhotoDelegates.append(delegate)
        output.capturePhoto(with: settings, delegate: delegate)
    }

    private func stopWideFOVStills() {
        wideSession?.stopRunning()
        wideSession = nil
        widePhotoOutput = nil
        widePhotoDelegates.removeAll()
        if wideFOVStatus == "wide-FOV stills on" {
            wideFOVStatus = "wide-FOV stills stopped"
        }
    }

    private func markWideFOVUnavailable(_ status: String) {
        stopWideFOVStills()
        wideFOVStatus = status
        wideFOVFallbackOff = true
    }

    private static func highestResolutionFormat() -> ARConfiguration.VideoFormat? {
        ARWorldTrackingConfiguration.supportedVideoFormats.max { lhs, rhs in
            let l = lhs.imageResolution.width * lhs.imageResolution.height
            let r = rhs.imageResolution.width * rhs.imageResolution.height
            if l == r { return lhs.framesPerSecond < rhs.framesPerSecond }
            return l < r
        }
    }

    private static func fieldOfView(width: Int, height: Int, intrinsics: simd_float3x3) -> [String: Double] {
        let fx = Double(intrinsics.columns.0.x)
        let fy = Double(intrinsics.columns.1.y)
        guard fx > 0, fy > 0 else { return [:] }
        let horizontal = 2.0 * atan(Double(width) / (2.0 * fx)) * 180.0 / .pi
        let vertical = 2.0 * atan(Double(height) / (2.0 * fy)) * 180.0 / .pi
        return [
            "horizontal_deg": round(horizontal * 10) / 10,
            "vertical_deg": round(vertical * 10) / 10,
        ]
    }

    private static func matrix4(_ matrix: simd_float4x4) -> [Float] {
        [
            matrix.columns.0.x, matrix.columns.0.y, matrix.columns.0.z, matrix.columns.0.w,
            matrix.columns.1.x, matrix.columns.1.y, matrix.columns.1.z, matrix.columns.1.w,
            matrix.columns.2.x, matrix.columns.2.y, matrix.columns.2.z, matrix.columns.2.w,
            matrix.columns.3.x, matrix.columns.3.y, matrix.columns.3.z, matrix.columns.3.w,
        ]
    }

    private static func matrix3(_ matrix: simd_float3x3) -> [Float] {
        [
            matrix.columns.0.x, matrix.columns.0.y, matrix.columns.0.z,
            matrix.columns.1.x, matrix.columns.1.y, matrix.columns.1.z,
            matrix.columns.2.x, matrix.columns.2.y, matrix.columns.2.z,
        ]
    }

    private static func trackingDescription(_ state: ARCamera.TrackingState) -> String {
        switch state {
        case .normal:
            return "normal"
        case .notAvailable:
            return "not available"
        case .limited(let reason):
            return "limited: \(reason)"
        }
    }

    private static func batteryPercent() -> Int {
        UIDevice.current.isBatteryMonitoringEnabled = true
        let level = UIDevice.current.batteryLevel
        return level >= 0 ? Int((level * 100).rounded()) : -1
    }

    private static func durationText(_ seconds: TimeInterval) -> String {
        let total = max(0, Int(seconds.rounded()))
        return String(format: "%02d:%02d", total / 60, total % 60)
    }

    private static func freeDiskBytes() -> Int64 {
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let values = try? documents.resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey])
        return Int64(values?.volumeAvailableCapacityForImportantUsage ?? 0)
    }

    private static func directorySize(_ url: URL) -> Int64 {
        guard let enumerator = FileManager.default.enumerator(
            at: url,
            includingPropertiesForKeys: [.fileSizeKey],
            options: [.skipsHiddenFiles]
        ) else { return 0 }
        var total: Int64 = 0
        for case let fileURL as URL in enumerator {
            let size = (try? fileURL.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
            total += Int64(size)
        }
        return total
    }

    private static func byteText(_ bytes: Int64) -> String {
        ByteCountFormatter.string(fromByteCount: bytes, countStyle: .file)
    }

    private static func thermalStateText(_ state: ProcessInfo.ThermalState) -> String {
        switch state {
        case .nominal: return "nominal"
        case .fair: return "fair"
        case .serious: return "serious"
        case .critical: return "critical"
        @unknown default: return "unknown"
        }
    }

    private static func writerStatusText(_ status: AVAssetWriter.Status?) -> String {
        guard let status else { return "not_started" }
        switch status {
        case .unknown: return "unknown"
        case .writing: return "writing"
        case .completed: return "completed"
        case .failed: return "failed"
        case .cancelled: return "cancelled"
        @unknown default: return "unknown"
        }
    }

    nonisolated private static func hashRawFiles(_ files: [String: URL]) -> [String: String] {
        var hashes: [String: String] = [:]
        for (name, url) in files.sorted(by: { $0.key < $1.key }) {
            guard let handle = try? FileHandle(forReadingFrom: url) else { continue }
            var hasher = SHA256()
            while true {
                let data: Data
                do {
                    guard let chunk = try handle.read(upToCount: 1024 * 1024) else { break }
                    data = chunk
                } catch {
                    break
                }
                if data.isEmpty { break }
                hasher.update(data: data)
            }
            try? handle.close()
            hashes[name] = hasher.finalize().map { String(format: "%02x", $0) }.joined()
        }
        return hashes
    }

    nonisolated private static func captureIdentity(for hashes: [String: String]) -> String {
        guard !hashes.isEmpty else { return "" }
        let canonical = hashes.sorted(by: { $0.key < $1.key })
            .map { "\($0.key)\0\($0.value)" }
            .joined(separator: "\0")
        let digest = SHA256.hash(data: Data(canonical.utf8))
        return digest.map { String(format: "%02x", $0) }.joined()
    }

    private static func deviceModelIdentifier() -> String {
        var systemInfo = utsname()
        uname(&systemInfo)
        let mirror = Mirror(reflecting: systemInfo.machine)
        return mirror.children.reduce(into: "") { result, element in
            guard let value = element.value as? Int8, value != 0 else { return }
            result.append(String(UnicodeScalar(UInt8(value))))
        }
    }

    private static func pullCommand(directoryName: String) -> String {
        "xcrun devicectl device copy from --device D3A506B2-8923-5313-B8A3-FF769ABBA228 --domain-type appDataContainer --domain-identifier de.zer00.soma --source Documents/\(directoryName) --destination /tmp/\(directoryName)"
    }

    private static let iso = ISO8601DateFormatter()

    private static let directoryTimestamp: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyyMMdd_HHmmss"
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        return formatter
    }()
}

private final class CaptureWidePhotoDelegate: NSObject, AVCapturePhotoCaptureDelegate {
    private let url: URL
    private let completion: (Bool) -> Void
    private(set) var finished = false

    init(url: URL, completion: @escaping (Bool) -> Void) {
        self.url = url
        self.completion = completion
    }

    func photoOutput(
        _ output: AVCapturePhotoOutput,
        didFinishProcessingPhoto photo: AVCapturePhoto,
        error: Error?
    ) {
        finished = true
        guard error == nil, let data = photo.fileDataRepresentation() else {
            completion(false)
            return
        }
        do {
            try data.write(to: url, options: [.atomic])
            completion(true)
        } catch {
            completion(false)
        }
    }
}

struct CaptureRootView: View {
    @StateObject private var recorder = CaptureModeRecorder()
    @AppStorage("captureWideFOVStills") private var wideFOVStills = false
    @AppStorage("somaHubURL") private var somaHubURL = ""
    @State private var showSpatialWorld = false
    @State private var showDebugMenu = false
    @State private var showLegacyDemo = false

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 18) {
                header
                if recorder.isRecording || recorder.isFinalizing {
                    recordingPanel
                } else {
                    idlePanel
                }
                Spacer(minLength: 0)
                Text("build \(BuildStamp.sha)")
                    .font(.caption2.monospaced())
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .onLongPressGesture {
                        showDebugMenu = true
                    }
            }
            .padding(20)
            .navigationTitle("CAPTURE")
            .navigationBarTitleDisplayMode(.inline)
        }
        .onAppear {
            migrateAutoOpenCapturePreference()
        }
        .onChange(of: recorder.wideFOVFallbackOff) { _, fallback in
            if fallback { wideFOVStills = false }
        }
        .fullScreenCover(isPresented: $showSpatialWorld) {
            SpatialWorldView(hubURL: somaHubURL)
        }
        .sheet(isPresented: $showLegacyDemo) {
            ContentView()
        }
        .sheet(isPresented: $showDebugMenu) {
            debugMenu
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("CAPTURE")
                .font(.system(size: 34, weight: .black, design: .rounded))
            Text("Phone records. Mac understands.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
    }

    private var recordingPanel: some View {
        VStack(alignment: .leading, spacing: 14) {
            MetricRow(label: "recording time", value: recorder.elapsedText)
            MetricRow(label: "file size", value: recorder.fileSizeText)
            MetricRow(label: "battery", value: recorder.batteryText)
            MetricRow(label: "free disk", value: recorder.freeDiskText)
            MetricRow(label: "pose tracking", value: recorder.trackingState)
            Button {
                recorder.stop()
            } label: {
                Text(recorder.isFinalizing ? "Finalizing..." : "Stop")
                    .font(.title2.weight(.bold))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 18)
            }
            .buttonStyle(.borderedProminent)
            .tint(.red)
            .disabled(recorder.isFinalizing)
        }
    }

    private var idlePanel: some View {
        VStack(alignment: .leading, spacing: 18) {
            Button {
                recorder.start(requestWideFOVStills: wideFOVStills)
            } label: {
                Text("Start Recording")
                    .font(.title2.weight(.bold))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 22)
            }
            .buttonStyle(.borderedProminent)

            if !recorder.stopSummary.isEmpty {
                Text(recorder.stopSummary)
                    .font(.headline)
                    .foregroundStyle(.primary)
            } else if let summary = recorder.lastSummary {
                Text("latest: \(summary.directoryName) · \(summary.durationMinutesText) min · \(summary.sizeGBText) GB")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            Divider()

            VStack(alignment: .leading, spacing: 8) {
                TextField("Hub URL", text: $somaHubURL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)
                    .textFieldStyle(.roundedBorder)
                Toggle("wide-FOV stills", isOn: $wideFOVStills)
                    .disabled(recorder.wideFOVFallbackOff)
                Text(recorder.wideFOVFallbackOff ? recorder.wideFOVStatus : "when enabled, ultrawide stills are attempted every 2s during capture")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Button {
                recorder.syncLatest(to: somaHubURL)
            } label: {
                Text("Sync to Mac")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .disabled(recorder.lastSummary == nil)

            if !recorder.syncStatus.isEmpty {
                Text(recorder.syncStatus)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Button {
                showSpatialWorld = true
            } label: {
                Text("Live preview (experimental)")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
        }
    }

    private var debugMenu: some View {
        NavigationStack {
            List {
                Section("Debug") {
                    Button("Legacy FastVLM demo") {
                        showDebugMenu = false
                        showLegacyDemo = true
                    }
                    Button("Live preview (experimental)") {
                        showDebugMenu = false
                        showSpatialWorld = true
                    }
                }
            }
            .navigationTitle("Debug")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { showDebugMenu = false }
                }
            }
        }
    }
}

private struct MetricRow: View {
    let label: String
    let value: String

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(label)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            Spacer()
            Text(value)
                .font(.title3.monospacedDigit().weight(.semibold))
                .multilineTextAlignment(.trailing)
        }
    }
}

func migrateAutoOpenCapturePreference() {
    let defaults = UserDefaults.standard
    let hasCaptureValue = defaults.object(forKey: "autoOpenCapture") != nil
    if !hasCaptureValue, defaults.bool(forKey: "autoOpenSpatial") {
        defaults.set(true, forKey: "autoOpenCapture")
    }
    if defaults.object(forKey: "autoOpenSpatial") != nil {
        defaults.set(false, forKey: "autoOpenSpatial")
    }
}

#else
struct CaptureRootView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("CAPTURE")
                .font(.largeTitle.weight(.bold))
            Text("Capture mode requires iPhone ARKit world tracking.")
                .foregroundStyle(.secondary)
        }
        .padding()
    }
}
#endif
