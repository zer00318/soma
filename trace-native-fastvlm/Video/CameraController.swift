//
// For licensing see accompanying LICENSE file.
// Copyright (C) 2025 Apple Inc. All Rights Reserved.
//

import AVFoundation
import CoreImage
import CoreMedia

#if os(iOS)
    import UIKit
#endif

// Depth capture via the rear dual-wide camera (disparity). Additive + fully gated: any failure in
// configureDepth() falls back to the exact prior wide-camera capture, so it cannot break the video
// pipeline. Flip to false to disable entirely.
let ENABLE_DEPTH = true

@Observable
public class CameraController: NSObject {

    private var framesContinuation: AsyncStream<CMSampleBuffer>.Continuation?

    public var backCamera = true {
        didSet {
            stop()
            start()
        }
    }

    public var devices = [AVCaptureDevice]()

    // Implicitly-unwrapped: the simulator has no camera and the force-unwrap crashed the
    // whole app at init (UI work was impossible off-device). On hardware this is always
    // non-nil; in the simulator start() guards it and the UI renders over a black feed.
    public var device: AVCaptureDevice! = AVCaptureDevice.default(for: .video) {
        didSet {
            stop()
            start()
        }
    }

    private var permissionGranted = true
    private var captureSession: AVCaptureSession?
    private let sessionQueue = DispatchQueue(label: "sessionQueue")
    // Full-resolution still path for dwell-triggered accurate OCR — the
    // 1080p stream buffer is too soft for poster/flyer text (walk-1 misses).
    private let photoOutput = AVCapturePhotoOutput()
    private var stillDelegates: [StillCaptureDelegate] = []
    // Depth (dual-wide disparity) — additive; nil when the device/format can't provide it.
    private var depthOutput: AVCaptureDepthDataOutput?
    @objc dynamic private var rotationCoordinator : AVCaptureDevice.RotationCoordinator?
    private var rotationObservation: NSKeyValueObservation?

    /// Capture one full-resolution still (async). Returns nil on failure —
    /// callers degrade to the stream buffer rather than blocking the loop.
    public func captureStill() async -> CGImage? {
        await withCheckedContinuation { (cont: CheckedContinuation<CGImage?, Never>) in
            sessionQueue.async { [self] in
                guard captureSession?.isRunning == true,
                      photoOutput.connections.first != nil else {
                    cont.resume(returning: nil)
                    return
                }
                let settings = AVCapturePhotoSettings()
                // Never exceed the output's configured ceiling (throws).
                settings.photoQualityPrioritization = photoOutput.maxPhotoQualityPrioritization
                let delegate = StillCaptureDelegate { [weak self] image in
                    cont.resume(returning: image)
                    self?.sessionQueue.async {
                        self?.stillDelegates.removeAll { $0.finished }
                    }
                }
                stillDelegates.append(delegate)
                photoOutput.capturePhoto(with: settings, delegate: delegate)
            }
        }
    }

    public func attach(continuation: AsyncStream<CMSampleBuffer>.Continuation) {
        sessionQueue.async {
            self.framesContinuation = continuation
        }
    }

    public func detatch() {
        sessionQueue.async {
            self.framesContinuation = nil
        }
    }

    public func stop() {
        sessionQueue.sync { [self] in
            captureSession?.stopRunning()
            captureSession = nil
        }

    }

    public func start() {
        guard device != nil else { return }  // simulator: no camera, UI still runs
        sessionQueue.async { [self] in
            let captureSession = AVCaptureSession()
            self.captureSession = captureSession

            self.checkPermission()
            self.setupCaptureSession(position: backCamera ? .back : .front)
            captureSession.startRunning()
        }
    }

    #if os(iOS)
        private func setOrientation(_ orientation: UIDeviceOrientation) {
            guard let captureSession else { return }

            let angle: Double?
            switch orientation {
            case .unknown, .faceDown:
                angle = nil
            case .portrait, .faceUp:
                angle = 90
            case .portraitUpsideDown:
                angle = 270
            case .landscapeLeft:
                angle = 0
            case .landscapeRight:
                angle = 180
            @unknown default:
                angle = nil
            }

            if let angle {
                for output in captureSession.outputs {
                    output.connection(with: .video)?.videoRotationAngle = angle
                }
            }
        }
    
    private func updateRotation(rotation : CGFloat) {
        guard let captureSession else { return }
        for output in captureSession.outputs {
            output.connection(with: .video)?.videoRotationAngle = rotation
        }
    }
    #endif

    func checkPermission() {
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized:
            // The user has previously granted access to the camera.
            self.permissionGranted = true

        case .notDetermined:
            // The user has not yet been asked for camera access.
            self.requestPermission()

        // Combine the two other cases into the default case
        default:
            self.permissionGranted = false
        }
    }

    func requestPermission() {
        // Strong reference not a problem here but might become one in the future.
        AVCaptureDevice.requestAccess(for: .video) { [unowned self] granted in
            self.permissionGranted = granted
        }
    }

    func setupCaptureSession(position: AVCaptureDevice.Position) {
        guard let captureSession else { return }

        let videoOutput = AVCaptureVideoDataOutput()

        guard permissionGranted else {
            print("No permission for camera")
            return
        }

        let deviceTypes: [AVCaptureDevice.DeviceType]
        #if os(iOS)
            // Prefer the dual-wide (depth-capable) camera; fall back to plain wide.
            deviceTypes = [.builtInDualWideCamera, .builtInDualCamera, .builtInWideAngleCamera]
        #else
            deviceTypes = [.external, .continuityCamera, .builtInWideAngleCamera]
        #endif

        let videoDeviceDiscoverySession = AVCaptureDevice.DiscoverySession(
            deviceTypes: deviceTypes,
            mediaType: .video,
            position: position)

        var videoDevice: AVCaptureDevice?
        #if os(iOS)
        if ENABLE_DEPTH {
            // Prefer a device that actually exposes depth formats (dual-wide on this phone).
            videoDevice = videoDeviceDiscoverySession.devices.first { device in
                device.formats.contains { !$0.supportedDepthDataFormats.isEmpty }
            }
        }
        #endif
        if videoDevice == nil {
            if videoDeviceDiscoverySession.devices.contains(self.device) {
                videoDevice = self.device
            } else {
                videoDevice = videoDeviceDiscoverySession.devices.first
            }
        }

        if devices.isEmpty {
            self.devices = videoDeviceDiscoverySession.devices
        }

        guard
            let videoDevice
        else {
            print("Unable to find video device")
            return
        }
        guard let videoDeviceInput = try? AVCaptureDeviceInput(device: videoDevice) else {
            print("Unable to create AVCaptureDeviceInput")
            return
        }
        guard captureSession.canAddInput(videoDeviceInput) else {
            print("Unable to add input")
            return
        }

        captureSession.beginConfiguration()
        captureSession.addInput(videoDeviceInput)

        videoOutput.setSampleBufferDelegate(self, queue: DispatchQueue(label: "sampleBufferQueue"))
        captureSession.addOutput(videoOutput)
        if captureSession.canAddOutput(photoOutput) {
            captureSession.addOutput(photoOutput)
            // Must be raised BEFORE requesting .quality in capture settings —
            // requesting above the output's max throws NSInvalidArgument
            // (walk-2 smoke crash, 2026-06-11 17:09).
            photoOutput.maxPhotoQualityPrioritization = .quality
        }

        var depthConfigured = false
        #if os(iOS)
        if ENABLE_DEPTH {
            depthConfigured = configureDepth(device: videoDevice, session: captureSession)
        }
        #endif
        if !depthConfigured {
            // Original, known-good path — unchanged when depth isn't set up.
            captureSession.sessionPreset = AVCaptureSession.Preset.hd1920x1080
        }
        captureSession.commitConfiguration()

        #if os(iOS)
        rotationCoordinator = AVCaptureDevice.RotationCoordinator(device: videoDevice, previewLayer: nil)
        rotationObservation = observe(\.rotationCoordinator!.videoRotationAngleForHorizonLevelCapture, options: [.initial, .new]) { [weak self] _, change in
            if let nv = change.newValue {
                self?.updateRotation(rotation: nv)
            }
        }
        #endif
    }

    #if os(iOS)
    /// Configure disparity depth on the dual-wide camera. Returns false (and changes nothing that
    /// breaks video) if no depth format is usable, so the caller falls back to the plain preset.
    private func configureDepth(device: AVCaptureDevice, session: AVCaptureSession) -> Bool {
        func videoArea(_ f: AVCaptureDevice.Format) -> Int {
            let d = CMVideoFormatDescriptionGetDimensions(f.formatDescription)
            return Int(d.width) * Int(d.height)
        }
        // Largest depth-capable video format at or below 1080p (keeps YOLO/VLM input sharp enough).
        let depthCapable = device.formats.filter { !$0.supportedDepthDataFormats.isEmpty }
            .sorted { videoArea($0) < videoArea($1) }
        guard let fmt = depthCapable.last(where: { videoArea($0) <= 1920 * 1080 }) ?? depthCapable.first else {
            return false
        }
        let depthFmt = fmt.supportedDepthDataFormats.first {
            CMFormatDescriptionGetMediaSubType($0.formatDescription) == kCVPixelFormatType_DepthFloat16
        } ?? fmt.supportedDepthDataFormats.first {
            CMFormatDescriptionGetMediaSubType($0.formatDescription) == kCVPixelFormatType_DisparityFloat16
        } ?? fmt.supportedDepthDataFormats.first
        guard let depthFmt else { return false }
        guard (try? device.lockForConfiguration()) != nil else { return false }
        device.activeFormat = fmt
        device.activeDepthDataFormat = depthFmt
        device.unlockForConfiguration()

        let output = AVCaptureDepthDataOutput()
        guard session.canAddOutput(output) else { return false }
        session.addOutput(output)
        output.isFilteringEnabled = true
        output.setDelegate(DepthReceiver.shared, callbackQueue: DispatchQueue(label: "depthQueue"))
        output.connection(with: .depthData)?.isEnabled = true
        // Manual activeFormat must be honored — a concrete preset would override it.
        session.sessionPreset = .inputPriority
        self.depthOutput = output
        return true
    }
    #endif
}

final class StillCaptureDelegate: NSObject, AVCapturePhotoCaptureDelegate {
    private let completion: (CGImage?) -> Void
    private(set) var finished = false

    init(completion: @escaping (CGImage?) -> Void) {
        self.completion = completion
    }

    func photoOutput(
        _ output: AVCapturePhotoOutput,
        didFinishProcessingPhoto photo: AVCapturePhoto,
        error: Error?
    ) {
        finished = true
        completion(error == nil ? photo.cgImageRepresentation() : nil)
    }
}

extension CameraController: AVCaptureVideoDataOutputSampleBufferDelegate {
    public func captureOutput(
        _ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer,
        from connection: AVCaptureConnection
    ) {
        if sampleBuffer.isValid && sampleBuffer.imageBuffer != nil {
            // Record the FULL video (every frame) alongside the perception stream.
            VideoRecorder.shared.append(sampleBuffer)
            framesContinuation?.yield(sampleBuffer)
        }
    }
}

/// Receives depth maps from the dual-wide camera's `AVCaptureDepthDataOutput` (set as its delegate in
/// `configureDepth`) and lets the perception loop sample per-object depth (metres) and unproject a
/// detection box to a METRIC 3D position + physical size. Holds only the latest map; if depth never
/// arrives (device/format unsupported) it stays nil and callers get nil — depth degrades safely.
/// Lives in the Video target (with the camera code); the App uses it via `import Video`.
public final class DepthReceiver: NSObject, AVCaptureDepthDataOutputDelegate {
    public static let shared = DepthReceiver()
    private var latest: AVDepthData?
    private let lock = NSLock()
    public var isReceiving: Bool { lock.lock(); defer { lock.unlock() }; return latest != nil }

    public func depthDataOutput(_ output: AVCaptureDepthDataOutput, didOutput depthData: AVDepthData,
                                timestamp: CMTime, connection: AVCaptureConnection) {
        let d = depthData.depthDataType == kCVPixelFormatType_DepthFloat32
            ? depthData
            : depthData.converting(toDepthDataType: kCVPixelFormatType_DepthFloat32)
        lock.lock(); latest = d; lock.unlock()
    }

    /// Depth in metres at a Vision-normalized point (origin bottom-left). nil if unavailable.
    public func depthMeters(atNormalizedX nx: CGFloat, y ny: CGFloat) -> Float? {
        lock.lock(); let d = latest; lock.unlock()
        guard let d else { return nil }
        let map = d.depthDataMap
        CVPixelBufferLockBaseAddress(map, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(map, .readOnly) }
        let w = CVPixelBufferGetWidth(map), h = CVPixelBufferGetHeight(map)
        guard w > 0, h > 0, let base = CVPixelBufferGetBaseAddress(map) else { return nil }
        let px = min(max(Int(nx * CGFloat(w)), 0), w - 1)
        let py = min(max(Int((1 - ny) * CGFloat(h)), 0), h - 1)  // depth map is top-left origin
        let rowBytes = CVPixelBufferGetBytesPerRow(map)
        let ptr = base.advanced(by: py * rowBytes + px * MemoryLayout<Float32>.size)
            .assumingMemoryBound(to: Float32.self)
        let v = ptr.pointee
        return (v.isFinite && v > 0) ? v : nil
    }

    /// COORDINATE-FIRST anchor: unproject a detection box to a METRIC 3D position + physical size in
    /// the camera frame, using the depth map's own camera intrinsics (falls back to a ~55° FOV focal
    /// if calibration is absent). Depth is the robust MEDIAN over the box's central region (rejects
    /// background/wall pixels bleeding in at the edges). This is the measured substrate the binder was
    /// missing: an object is a volume at a location + a real size, not a label + a guessed count.
    /// Returns nil (safely) when no depth is available. `box` is Vision-normalized, origin bottom-left.
    public func metricBox(_ box: CGRect) -> (x: Float, y: Float, z: Float, widthM: Float, heightM: Float)? {
        lock.lock(); let d = latest; lock.unlock()
        guard let d else { return nil }
        let map = d.depthDataMap
        CVPixelBufferLockBaseAddress(map, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(map, .readOnly) }
        let w = CVPixelBufferGetWidth(map), h = CVPixelBufferGetHeight(map)
        guard w > 0, h > 0, let base = CVPixelBufferGetBaseAddress(map) else { return nil }
        let rowBytes = CVPixelBufferGetBytesPerRow(map)
        func depthAt(_ nx: CGFloat, _ ny: CGFloat) -> Float? {
            let px = min(max(Int(nx * CGFloat(w)), 0), w - 1)
            let py = min(max(Int((1 - ny) * CGFloat(h)), 0), h - 1)  // map is top-left origin
            let v = base.advanced(by: py * rowBytes + px * MemoryLayout<Float32>.size)
                .assumingMemoryBound(to: Float32.self).pointee
            return (v.isFinite && v > 0) ? v : nil
        }
        // median depth over the central 50% of the box
        var samples: [Float] = []
        let x0 = box.minX + box.width * 0.25, x1 = box.maxX - box.width * 0.25
        let y0 = box.minY + box.height * 0.25, y1 = box.maxY - box.height * 0.25
        let steps = 5
        for i in 0...steps { for j in 0...steps {
            let nx = x0 + (x1 - x0) * CGFloat(i) / CGFloat(steps)
            let ny = y0 + (y1 - y0) * CGFloat(j) / CGFloat(steps)
            if let v = depthAt(nx, ny) { samples.append(v) }
        } }
        guard !samples.isEmpty else { return nil }
        samples.sort(); let z = samples[samples.count / 2]
        // focal + principal point in depth-map pixels; prefer real intrinsics, else FOV fallback
        var fx = Float(w) * 0.85, fy = Float(h) * 0.85
        var ppx = Float(w) / 2, ppy = Float(h) / 2
        if let cal = d.cameraCalibrationData {
            let m = cal.intrinsicMatrix
            let ref = cal.intrinsicMatrixReferenceDimensions
            let sx = Float(w) / Float(ref.width), sy = Float(h) / Float(ref.height)
            fx = m.columns.0.x * sx; fy = m.columns.1.y * sy
            ppx = m.columns.2.x * sx; ppy = m.columns.2.y * sy
        }
        let ucx = Float(box.midX) * Float(w)
        let ucy = Float(1 - box.midY) * Float(h)          // flip to top-left origin
        let X = (ucx - ppx) * z / fx
        let Y = (ucy - ppy) * z / fy
        let widthM = Float(box.width) * Float(w) * z / fx
        let heightM = Float(box.height) * Float(h) * z / fy
        return (X, Y, z, widthM, heightM)
    }
}
