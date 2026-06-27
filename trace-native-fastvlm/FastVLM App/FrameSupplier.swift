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

#if os(iOS)
import UIKit
#endif

@MainActor
final class FrameSupplier {
    static let shared = FrameSupplier()
    private init() {}

    // Tunables (radians of attitude change per step; seconds).
    private let settledMotion = 0.045      // <~2.5°/step => steady enough to be sharp
    private let minInterval: TimeInterval = 0.30   // cap keyframe rate (~3/s max)
    private let idleInterval: TimeInterval = 2.0   // emit at least this often when static
    private let moveToReemit = 0.10        // emit again once the view has changed this much

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
