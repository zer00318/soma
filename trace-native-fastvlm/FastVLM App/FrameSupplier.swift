//  FrameSupplier.swift
//  The intake valve: turn the high-rate camera stream into a small set of SHARP,
//  information-rich keyframes for the Mac perception stack — while preserving the
//  SIGNAL OF MOVEMENT between them (so the temporal/action layer knows motion
//  happened even on frames we discard).
//
//  This first slice selects by MOTION (from device attitude): fast pans produce
//  motion-blurred frames, so we emit a keyframe when motion SETTLES (a fixation),
//  skip the blurry fast-motion frames, and report how much movement occurred since
//  the last keyframe. A sharpness gate and a true high-fps decoupled hook come next.

import Foundation
import CoreGraphics
import CoreImage
import CoreVideo

#if os(iOS)
import UIKit
#endif

@MainActor
final class FrameSupplier {
    static let shared = FrameSupplier()
    private init() {}

    private static let ciContext = CIContext(options: [.useSoftwareRenderer: false])
    /// Reject a keyframe candidate below this Laplacian-variance sharpness. Matches
    /// the Mac frame_quality gate (512-downscale, validated: blurry pan 1-28, sharp 270+).
    let sharpnessThreshold = 60.0

    /// Laplacian-variance sharpness of a frame (higher = sharper). Same method as the
    /// Mac scorer so the validated threshold transfers. Only run on motion-settled
    /// keyframe candidates (a few per second), so the cost is negligible.
    func sharpness(_ buffer: CVPixelBuffer) -> Double {
        let ci = CIImage(cvPixelBuffer: buffer)
        let longest = max(ci.extent.width, ci.extent.height)
        guard longest > 0 else { return 9999 }
        let scale = min(1.0, 512.0 / longest)
        let small = ci.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
        let gray = small.applyingFilter("CIColorControls", parameters: [kCIInputSaturationKey: 0.0])
        let w = Int(small.extent.width.rounded())
        let h = Int(small.extent.height.rounded())
        guard w > 4, h > 4 else { return 9999 }
        var px = [UInt8](repeating: 0, count: w * h * 4)
        Self.ciContext.render(gray, toBitmap: &px, rowBytes: w * 4,
                              bounds: CGRect(x: 0, y: 0, width: w, height: h),
                              format: .RGBA8, colorSpace: CGColorSpaceCreateDeviceRGB())
        var lum = [Double](repeating: 0, count: w * h)
        for i in 0..<(w * h) { lum[i] = Double(px[i * 4]) }
        var sum = 0.0, sum2 = 0.0, n = 0.0
        for y in 1..<(h - 1) {
            for x in 1..<(w - 1) {
                let lap = lum[(y - 1) * w + x] + lum[(y + 1) * w + x]
                        + lum[y * w + x - 1] + lum[y * w + x + 1] - 4 * lum[y * w + x]
                sum += lap; sum2 += lap * lap; n += 1
            }
        }
        guard n > 0 else { return 9999 }
        let mean = sum / n
        return sum2 / n - mean * mean
    }

    // Tunables (radians of attitude change per step; seconds).
    // REVAMP (dense capture): the sharpness gate already drops blur, so we no longer
    // need a tight motion gate to avoid blur — we want MANY sharp frames. Loosened to
    // stream ~6-8 keyframes/s during slow dwell instead of ~0.1/s. The Mac saves them
    // all to disk and the binder perceives them in batch (Q&A is async).
    private let settledMotion = 0.10       // accept mild motion; sharpness gate culls real blur
    private let minInterval: TimeInterval = 0.12   // cap keyframe rate (~8/s max)
    private let idleInterval: TimeInterval = 0.7   // emit often even when static (capture density)
    private let moveToReemit = 0.03        // re-emit after only a small view change

    private var lastYaw: Double?
    private var lastPitch: Double?
    private var lastKeyframeAt = Date.distantPast
    private var motionSinceKeyframe = 0.0   // accumulated attitude change (the movement signal)
    private var peakMotionSinceKeyframe = 0.0

    struct Decision {
        let emit: Bool
        /// total attitude change since the last emitted keyframe (the movement signal)
        let motionSinceKeyframe: Double
        /// the largest single-step motion since last keyframe (proxy for "was there a fast pan / blur")
        let peakMotion: Double
        let stepMotion: Double
    }

    /// Feed the current attitude (from PoseStamper.snapshot()) each frame; get a
    /// keyframe decision + the movement signal to attach to the packet.
    func consider(pose: [String: Any], now: Date = Date()) -> Decision {
        let yaw = (pose["yaw"] as? Double) ?? Double(truncating: (pose["yaw"] as? NSNumber) ?? 0)
        let pitch = (pose["pitch"] as? Double) ?? Double(truncating: (pose["pitch"] as? NSNumber) ?? 0)

        var step = 0.0
        if let ly = lastYaw, let lp = lastPitch {
            step = (yaw - ly).magnitude + (pitch - lp).magnitude
        }
        lastYaw = yaw
        lastPitch = pitch
        motionSinceKeyframe += step
        peakMotionSinceKeyframe = max(peakMotionSinceKeyframe, step)

        let dt = now.timeIntervalSince(lastKeyframeAt)
        let settled = step <= settledMotion          // this frame is steady (likely sharp)
        let changedEnough = motionSinceKeyframe >= moveToReemit
        let idle = dt >= idleInterval
        let emit = dt >= minInterval && settled && (changedEnough || idle)

        let decision = Decision(emit: emit,
                                motionSinceKeyframe: motionSinceKeyframe,
                                peakMotion: peakMotionSinceKeyframe,
                                stepMotion: step)
        if emit {
            lastKeyframeAt = now
            motionSinceKeyframe = 0
            peakMotionSinceKeyframe = 0
        }
        return decision
    }
}
