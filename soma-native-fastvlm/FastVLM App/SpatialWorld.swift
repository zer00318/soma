// SpatialWorld.swift — genesis-frame world engine (founder redirect 2026-06-12).
//
// First ARKit frame = genesis. World tracking (gyro+accel+camera VIO) gives
// the camera pose in that frame. MobileCLIP names salient regions as short
// object words; ARKit raycasts those regions into the
// genesis coordinate frame. The output is a visual word map, not a question
// answerer and not a geometry viewer.

import Combine
import CoreImage
import Foundation
import SwiftUI

#if os(iOS)
import ARKit
import ImageIO
import MLXLMCommon
import UIKit
import Vision

// MARK: - Model

struct SpatialObject: Identifiable, Codable {
    var id = UUID()
    var label: String
    var position: simd_float3        // genesis frame, meters
    var extent: simd_float2 = .zero  // width, height (m), zero until measured
    var sightings: Int = 1
    var lastSeen: Date = Date()
    var supportPlaneID: UUID?
    var footprint: [[Float]] = []
    var heightM: Float = 0
    var verified: Bool = false
    var relabeledFrom: [String] = []
    var phantomStrikes: Int = 0
    var phantom: Bool = false
    var lastMobileCLIPScore: Float = 0
    var lastMobileCLIPMargin: Float = 0
    var positionSampleCount: Int = 1
    var positionMean: simd_float3
    var positionM2: Float = 0

    init(
        id: UUID = UUID(),
        label: String,
        position: simd_float3,
        extent: simd_float2 = .zero,
        sightings: Int = 1,
        lastSeen: Date = Date(),
        supportPlaneID: UUID? = nil,
        footprint: [[Float]] = [],
        heightM: Float = 0,
        verified: Bool = false,
        relabeledFrom: [String] = [],
        phantomStrikes: Int = 0,
        phantom: Bool = false,
        lastMobileCLIPScore: Float = 0,
        lastMobileCLIPMargin: Float = 0,
        positionSampleCount: Int? = nil,
        positionMean: simd_float3? = nil,
        positionM2: Float = 0
    ) {
        self.id = id
        self.label = label
        self.position = position
        self.extent = extent
        self.sightings = sightings
        self.lastSeen = lastSeen
        self.supportPlaneID = supportPlaneID
        self.footprint = Self.sanitizedFootprint(footprint)
        self.heightM = heightM.isFinite ? max(0, heightM) : 0
        self.verified = verified
        self.relabeledFrom = relabeledFrom
        self.phantomStrikes = max(0, phantomStrikes)
        self.phantom = phantom
        self.lastMobileCLIPScore = lastMobileCLIPScore
        self.lastMobileCLIPMargin = lastMobileCLIPMargin
        self.positionSampleCount = max(1, positionSampleCount ?? sightings)
        self.positionMean = positionMean ?? position
        self.positionM2 = max(0, positionM2)
    }

    var positionSpread: Float {
        guard positionSampleCount > 1 else { return 0 }
        return sqrt(max(0, positionM2 / Float(positionSampleCount - 1)))
    }

    var positionConfidence: String {
        if verified && sightings >= 5 && positionSpread <= 0.5 {
            return "high"
        }
        if sightings >= 3 && positionSpread <= 1.0 {
            return "medium"
        }
        return "low"
    }

    private enum CodingKeys: String, CodingKey {
        case id, label, x, y, z, w, h, sightings, lastSeen, supportPlaneID
        case footprint, heightM
        case verified, relabeledFrom, phantomStrikes, phantom, lastMobileCLIPScore, lastMobileCLIPMargin
        case positionSampleCount, positionMeanX, positionMeanY, positionMeanZ, positionM2
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decodeIfPresent(UUID.self, forKey: .id) ?? UUID()
        label = try container.decode(String.self, forKey: .label)
        let x = try container.decode(Float.self, forKey: .x)
        let y = try container.decode(Float.self, forKey: .y)
        let z = try container.decode(Float.self, forKey: .z)
        position = simd_float3(x, y, z)
        let w = try container.decodeIfPresent(Float.self, forKey: .w) ?? 0
        let h = try container.decodeIfPresent(Float.self, forKey: .h) ?? 0
        extent = simd_float2(max(0, w), max(0, h))
        sightings = try container.decodeIfPresent(Int.self, forKey: .sightings) ?? 1
        lastSeen = try container.decodeIfPresent(Date.self, forKey: .lastSeen) ?? Date()
        supportPlaneID = try container.decodeIfPresent(UUID.self, forKey: .supportPlaneID)
        footprint = Self.sanitizedFootprint(try container.decodeIfPresent([[Float]].self, forKey: .footprint) ?? [])
        let decodedHeight = try container.decodeIfPresent(Float.self, forKey: .heightM) ?? 0
        heightM = decodedHeight.isFinite ? max(0, decodedHeight) : 0
        verified = try container.decodeIfPresent(Bool.self, forKey: .verified) ?? false
        relabeledFrom = try container.decodeIfPresent([String].self, forKey: .relabeledFrom) ?? []
        phantomStrikes = max(0, try container.decodeIfPresent(Int.self, forKey: .phantomStrikes) ?? 0)
        phantom = try container.decodeIfPresent(Bool.self, forKey: .phantom) ?? false
        lastMobileCLIPScore = try container.decodeIfPresent(Float.self, forKey: .lastMobileCLIPScore) ?? 0
        lastMobileCLIPMargin = try container.decodeIfPresent(Float.self, forKey: .lastMobileCLIPMargin) ?? 0
        positionSampleCount = max(1, try container.decodeIfPresent(Int.self, forKey: .positionSampleCount) ?? sightings)
        let mx = try container.decodeIfPresent(Float.self, forKey: .positionMeanX) ?? x
        let my = try container.decodeIfPresent(Float.self, forKey: .positionMeanY) ?? y
        let mz = try container.decodeIfPresent(Float.self, forKey: .positionMeanZ) ?? z
        positionMean = simd_float3(mx, my, mz)
        positionM2 = max(0, try container.decodeIfPresent(Float.self, forKey: .positionM2) ?? 0)
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(id, forKey: .id)
        try container.encode(label, forKey: .label)
        try container.encode(position.x, forKey: .x)
        try container.encode(position.y, forKey: .y)
        try container.encode(position.z, forKey: .z)
        try container.encode(extent.x, forKey: .w)
        try container.encode(extent.y, forKey: .h)
        try container.encode(sightings, forKey: .sightings)
        try container.encode(lastSeen, forKey: .lastSeen)
        try container.encodeIfPresent(supportPlaneID, forKey: .supportPlaneID)
        try container.encode(footprint, forKey: .footprint)
        try container.encode(heightM, forKey: .heightM)
        try container.encode(verified, forKey: .verified)
        try container.encode(relabeledFrom, forKey: .relabeledFrom)
        try container.encode(phantomStrikes, forKey: .phantomStrikes)
        try container.encode(phantom, forKey: .phantom)
        try container.encode(lastMobileCLIPScore, forKey: .lastMobileCLIPScore)
        try container.encode(lastMobileCLIPMargin, forKey: .lastMobileCLIPMargin)
        try container.encode(positionSampleCount, forKey: .positionSampleCount)
        try container.encode(positionMean.x, forKey: .positionMeanX)
        try container.encode(positionMean.y, forKey: .positionMeanY)
        try container.encode(positionMean.z, forKey: .positionMeanZ)
        try container.encode(positionM2, forKey: .positionM2)
    }

    private static func sanitizedFootprint(_ raw: [[Float]]) -> [[Float]] {
        raw.compactMap { pair in
            guard pair.count >= 2, pair[0].isFinite, pair[1].isFinite else { return nil }
            return [pair[0], pair[1]]
        }
    }
}

struct SpatialWord: Identifiable {
    let id: UUID
    var label: String
    var position: simd_float3
    var extent: simd_float2 = .zero
    var kind: String
    var strength: Int
    var verified: Bool = true
    var relabeledFrom: [String] = []
    var supportPlaneID: UUID?
    var footprint: [[Float]] = []
    var heightM: Float = 0
    var positionSpread: Float = 0
    var positionConfidence: String = "high"
}

struct SpatialLabelCandidate {
    var label: String
    var point: CGPoint
    var roi: CGRect? = nil
    var maskPolygon: [CGPoint] = []
    var score: Float = 0
    var margin: Float = 0
}

struct SpatialWordScanResult {
    var labels: [SpatialLabelCandidate]
    var debug: String
    var elapsedMilliseconds: Int = 0
    var namerMilliseconds: [Int] = []
    var proposalsConsidered: Int = 0
    var proposalCap: Int = 0
}

struct SpatialPlane: Identifiable {
    let id: UUID                     // ARPlaneAnchor identifier
    var classification: String       // table/floor/wall/seat/window/door/none
    var center: simd_float3
    var extent: simd_float2          // width, depth (m)
    var alignment: String            // horizontal/vertical
    var isEstimated: Bool = false
}

struct PendingSpatialObject: Identifiable {
    let id = UUID()
    var label: String
    var position: simd_float3
    var extent: simd_float2 = .zero
    var footprint: [[Float]] = []
    var heightM: Float = 0
    var sightings: Int = 1
    var firstSeen: Date = Date()
    var lastSeen: Date = Date()
}

private struct SpatialShapeEstimate {
    var footprint: [[Float]]
    var heightM: Float
}

private struct SpatialPositionEstimate {
    var position: simd_float3
    var cameraPosition: simd_float3
    var cameraForward: simd_float3
    var raycastDistance: Float?
    var planeID: UUID?
    var usedRaycast: Bool
}

private struct SpatialObjectUpsertResult {
    var objectID: UUID?
    var changedPermanentObject: Bool
}

private struct SpatialVerificationCrop {
    var image: CIImage
    var mobileclipLabel: String
    var score: Float
    var margin: Float
    var updatedAt: Date
}

private final class BackgroundTask: @unchecked Sendable {
    private var identifier: UIBackgroundTaskIdentifier = .invalid
    private let lock = NSLock()

    init(name: String, enabled: Bool) {
        guard enabled else { return }
        identifier = UIApplication.shared.beginBackgroundTask(withName: name) { [weak self] in
            self?.end()
        }
    }

    func end() {
        lock.lock()
        let task = identifier
        identifier = .invalid
        lock.unlock()
        guard task != .invalid else { return }
        DispatchQueue.main.async {
            UIApplication.shared.endBackgroundTask(task)
        }
    }
}

// MARK: - Engine

@MainActor
final class SpatialWorldEngine: NSObject, ObservableObject, ARSessionDelegate {
    @Published var worldText: String = "waiting for genesis frame…"
    @Published var words: [SpatialWord] = []
    @Published var namingStatus: String = "word scanner waiting"
    @Published var lastScannerOutput: String = ""
    @Published var trackingState: String = "initializing"
    @Published var objectCount = 0
    @Published var planeCount = 0

    let session = ARSession()
    var hubURL: String = ""
    var onFrameForNaming: ((CVImageBuffer, Int) -> Void)?
    var onVerifyObjectName: ((UUID, CIImage, String) -> Void)?

    private var genesisAt: Date?
    private var planes: [UUID: SpatialPlane] = [:]
    private let floorProbeID = UUID()
    private var floorProbe: SpatialPlane?
    private var objects: [SpatialObject] = []
    private var pendingObjects: [PendingSpatialObject] = []
    private var verificationAttempts: [UUID: Int] = [:]
    private var verificationLastAttempt: [UUID: Date] = [:]
    private var latestFrame: ARFrame?
    private var lastFloorProbeAt = Date.distantPast
    private var lastNamingAt = Date.distantPast
    private var lastTreeAt = Date.distantPast
    private var namingInFlight = false
    private var lastPostAt = Date.distantPast
    private var lastPostedSignature = ""
    private var spatialPostsOK = 0
    private var spatialPostsSpooled = 0
    private var lastNamingStatusCore = "word scanner waiting"
    private var scanWordTimestamps: [Date] = []
    private var scanElapsedSamples: [Int] = []
    private var namerElapsedSamples: [Int] = []
    private var namingInterval: TimeInterval = 1.1
    private var proposalCap = 40
    private var thermalProposalCapActive = false
    private var worldMapStatus = "world map not loaded"
    private var worldMapLoadedAt: Date?
    private var upsertsBlockedForRelocalization = false
    private var relocalizationTimeoutLogged = false
    private var saveDebounceTask: Task<Void, Never>?
    private var periodicSaveTask: Task<Void, Never>?
    private var lifecycleObservers: [NSObjectProtocol] = []
    private var verificationCrops: [UUID: SpatialVerificationCrop] = [:]
    private var verificationInFlight = false
    private var lastVerificationAt = Date.distantPast
    private var phantomLastStrikeCropAt: [UUID: Date] = [:]
    private var phantomRejudgeAllowed: Set<UUID> = []

    private nonisolated static let perceptionSpoolQueue = DispatchQueue(label: "de.zer00.soma.spatial-perception-spool")
    private static let verificationCooldown: TimeInterval = 5
    private static let verificationLowMargin: Float = 0.02

    private var buildSuffix: String {
        " · build \(BuildStamp.sha)"
    }

    private var phantomCount: Int {
        objects.filter { $0.phantom }.count
    }

    private func stampedStatus(_ status: String) -> String {
        "\(status) · ph:\(phantomCount) · hub ok:\(spatialPostsOK) spooled:\(spatialPostsSpooled)\(buildSuffix)"
    }

    private func setNamingStatus(_ status: String) {
        lastNamingStatusCore = status
        namingStatus = stampedStatus(status)
    }

    func start() {
        let config = ARWorldTrackingConfiguration()
        config.planeDetection = [.horizontal, .vertical]
        config.worldAlignment = .gravity
        if let worldMap = loadWorldMap() {
            config.initialWorldMap = worldMap
            worldMapStatus = "world map loaded"
            worldMapLoadedAt = Date()
            upsertsBlockedForRelocalization = true
            relocalizationTimeoutLogged = false
        } else {
            worldMapStatus = "new world map"
            worldMapLoadedAt = nil
            upsertsBlockedForRelocalization = false
            relocalizationTimeoutLogged = false
        }
        session.delegate = self
        let runOptions: ARSession.RunOptions = config.initialWorldMap == nil
            ? [.resetTracking, .removeExistingAnchors]
            : [.removeExistingAnchors]
        loadPersistentObjects()
        session.run(config, options: runOptions)
        genesisAt = nil
        planes = [:]
        floorProbe = nil
        pendingObjects = []
        verificationAttempts = [:]
        verificationLastAttempt = [:]
        latestFrame = nil
        namingInFlight = false
        spatialPostsOK = 0
        spatialPostsSpooled = 0
        lastNamingStatusCore = "word scanner waiting"
        scanWordTimestamps = []
        scanElapsedSamples = []
        namerElapsedSamples = []
        namingInterval = 1.1
        proposalCap = 40
        thermalProposalCapActive = false
        verificationCrops = [:]
        verificationInFlight = false
        lastVerificationAt = Date.distantPast
        phantomLastStrikeCropAt = [:]
        phantomRejudgeAllowed = []
        objectCount = objects.count
        regenerateWords(floor: nil, surfaces: [], verticals: [], objects: objects.filter { !$0.phantom })
        setNamingStatus("\(MobileCLIPNamer.shared.status); \(worldMapStatus); loaded \(objects.count)")
        lastScannerOutput = ""
        worldText = "waiting for genesis frame…"
        installLifecycleObservers()
        startPeriodicSave()
    }

    func stop() {
        saveDebounceTask?.cancel()
        saveDebounceTask = nil
        periodicSaveTask?.cancel()
        periodicSaveTask = nil
        savePersistentState(reason: "stop", includeWorldMap: true)
        removeLifecycleObservers()
        session.pause()
    }

    private var somaSupportDirectory: URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        let dir = base.appendingPathComponent("SOMA", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    private var objectsURL: URL {
        somaSupportDirectory.appendingPathComponent("spatial_world.json")
    }

    private var worldMapURL: URL {
        somaSupportDirectory.appendingPathComponent("spatial_world.arexperience")
    }

    private var diagnosticsURL: URL {
        somaSupportDirectory.appendingPathComponent("spatial_diag.ndjson")
    }

    private func loadPersistentObjects() {
        guard let data = try? Data(contentsOf: objectsURL) else {
            objects = []
            return
        }
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        if let loaded = try? decoder.decode([SpatialObject].self, from: data) {
            objects = dedupeOnLoad(loaded)
        }
    }

    /// Collapse duplicate same-word objects at session start. Runtime
    /// merging (2.0m nearest) can FEED two existing twins but never
    /// collapse them — device data 2026-06-12 had same-word pairs 0.16m
    /// apart with sightings 1417/21, and every dup group was one dominant
    /// object plus low-sighting raycast-scatter ghosts. Rules:
    /// (1) same word within 1.0m → merge into higher-sighting twin;
    /// (2) ghost satellites (sightings < 10% of group max AND < 30,
    ///     within 3.5m of the dominant) → absorbed into the dominant.
    /// A genuinely distinct second object re-accumulates as its own
    /// entry afterwards, so a wrong absorb self-heals.
    private func dedupeOnLoad(_ loaded: [SpatialObject]) -> [SpatialObject] {
        var kept: [SpatialObject] = []
        var absorbed = 0
        let groups = Dictionary(grouping: loaded, by: { $0.label })
        for (_, group) in groups {
            var members = group.sorted { $0.sightings > $1.sightings }
            var result: [SpatialObject] = []
            while !members.isEmpty {
                var dominant = members.removeFirst()
                let maxSightings = dominant.sightings
                members.removeAll { candidate in
                    let d = simd_distance(candidate.position, dominant.position)
                    let twin = d <= 1.0
                    let ghost = d <= 3.5
                        && candidate.sightings < max(3, maxSightings / 10)
                        && candidate.sightings < 30
                    guard twin || ghost else { return false }
                    dominant.sightings += candidate.sightings
                    dominant.relabeledFrom = Array(Set(dominant.relabeledFrom + candidate.relabeledFrom))
                    absorbed += 1
                    return true
                }
                result.append(dominant)
            }
            kept.append(contentsOf: result)
        }
        if absorbed > 0 {
            appendSpatialDiagnostic(
                word: "__dedupe__",
                score: 0,
                elapsedMilliseconds: 0,
                position: nil,
                decision: "load_dedupe",
                extra: ["absorbed": absorbed, "before": loaded.count, "after": kept.count]
            )
        }
        return kept
    }

    private func savePersistentObjects(reason: String) {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        guard let data = try? encoder.encode(objects) else {
            appendSpatialDiagnostic(
                word: "__system__",
                score: 0,
                elapsedMilliseconds: 0,
                position: nil,
                decision: "rejected",
                extra: ["reason": "json_encode_failed", "save_reason": reason]
            )
            return
        }
        do {
            try data.write(to: objectsURL, options: [.atomic])
        } catch {
            appendSpatialDiagnostic(
                word: "__system__",
                score: 0,
                elapsedMilliseconds: 0,
                position: nil,
                decision: "rejected",
                extra: ["reason": "json_write_failed", "save_reason": reason, "error": error.localizedDescription]
            )
        }
    }

    private func savePersistentState(
        reason: String,
        includeWorldMap: Bool,
        useBackgroundTask: Bool = false
    ) {
        savePersistentObjects(reason: reason)
        guard includeWorldMap else { return }
        saveWorldMap(reason: reason, useBackgroundTask: useBackgroundTask)
    }

    private func scheduleDebouncedSave() {
        saveDebounceTask?.cancel()
        saveDebounceTask = Task { @MainActor [weak self] in
            try? await Task.sleep(nanoseconds: 2_000_000_000)
            guard !Task.isCancelled else { return }
            self?.savePersistentState(reason: "debounced_upsert", includeWorldMap: false)
        }
    }

    private func startPeriodicSave() {
        guard periodicSaveTask == nil else { return }
        periodicSaveTask = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 30_000_000_000)
                guard !Task.isCancelled else { return }
                self?.savePersistentState(reason: "periodic_30s", includeWorldMap: true)
            }
        }
    }

    private func installLifecycleObservers() {
        guard lifecycleObservers.isEmpty else { return }
        let center = NotificationCenter.default
        let notifications: [(Notification.Name, String)] = [
            (UIApplication.willResignActiveNotification, "will_resign_active"),
            (UIApplication.didEnterBackgroundNotification, "did_enter_background"),
            (UIApplication.willTerminateNotification, "will_terminate"),
        ]
        lifecycleObservers = notifications.map { name, reason in
            center.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in
                Task { @MainActor in
                    self?.saveBeforeSuspension(reason: reason)
                }
            }
        }
    }

    private func removeLifecycleObservers() {
        let center = NotificationCenter.default
        for observer in lifecycleObservers {
            center.removeObserver(observer)
        }
        lifecycleObservers = []
    }

    func saveBeforeSuspension(reason: String) {
        saveDebounceTask?.cancel()
        saveDebounceTask = nil
        savePersistentState(reason: reason, includeWorldMap: true, useBackgroundTask: true)
    }

    private func loadWorldMap() -> ARWorldMap? {
        guard let data = try? Data(contentsOf: worldMapURL) else { return nil }
        return try? NSKeyedUnarchiver.unarchivedObject(ofClass: ARWorldMap.self, from: data)
    }

    private func saveWorldMap(reason: String, useBackgroundTask: Bool = false) {
        let url = worldMapURL
        let backgroundTask = BackgroundTask(name: "SOMA Spatial WorldMap", enabled: useBackgroundTask)
        session.getCurrentWorldMap { worldMap, error in
            defer { backgroundTask.end() }
            guard error == nil, let worldMap else { return }
            guard let data = try? NSKeyedArchiver.archivedData(
                withRootObject: worldMap,
                requiringSecureCoding: true
            ) else { return }
            try? data.write(to: url, options: [.atomic])
        }
    }

    // MARK: ARSessionDelegate

    nonisolated func session(_ session: ARSession, didUpdate frame: ARFrame) {
        let camState: String
        let trackingIsNormal: Bool
        switch frame.camera.trackingState {
        case .normal:
            camState = "normal"
            trackingIsNormal = true
        case .limited(let reason):
            camState = "limited (\(reason))"
            trackingIsNormal = false
        case .notAvailable:
            camState = "unavailable"
            trackingIsNormal = false
        }
        Task { @MainActor in
            if self.genesisAt == nil { self.genesisAt = Date() }
            self.trackingState = camState
            self.updateRelocalizationGate(trackingIsNormal: trackingIsNormal)
            self.tick(frame: frame)
        }
    }

    nonisolated func session(_ session: ARSession, didAdd anchors: [ARAnchor]) {
        updatePlanes(anchors)
    }

    nonisolated func session(_ session: ARSession, didUpdate anchors: [ARAnchor]) {
        updatePlanes(anchors)
    }

    nonisolated private func updatePlanes(_ anchors: [ARAnchor]) {
        let snapshot: [SpatialPlane] = anchors.compactMap { anchor in
            guard let p = anchor as? ARPlaneAnchor else { return nil }
            let cls: String
            switch p.classification {
            case .table: cls = "table"
            case .floor: cls = "floor"
            case .wall: cls = "wall"
            case .seat: cls = "seat"
            case .window: cls = "window"
            case .door: cls = "door"
            case .ceiling: cls = "ceiling"
            default: cls = p.alignment == .horizontal ? "surface" : "vertical surface"
            }
            let centerLocal = p.center
            let centerWorld = p.transform * simd_float4(centerLocal.x, centerLocal.y, centerLocal.z, 1)
            return SpatialPlane(
                id: p.identifier,
                classification: cls,
                center: simd_float3(centerWorld.x, centerWorld.y, centerWorld.z),
                extent: simd_float2(p.planeExtent.width, p.planeExtent.height),
                alignment: p.alignment == .horizontal ? "horizontal" : "vertical"
            )
        }
        Task { @MainActor in
            for plane in snapshot { self.planes[plane.id] = plane }
            self.planeCount = self.planes.count
        }
    }

    // MARK: per-frame work (throttled)

    private func updateRelocalizationGate(trackingIsNormal: Bool) {
        guard upsertsBlockedForRelocalization, trackingIsNormal else { return }
        upsertsBlockedForRelocalization = false
        worldMapStatus = "world map relocalized"
        appendSpatialDiagnostic(
            word: "__system__",
            score: 0,
            elapsedMilliseconds: 0,
            position: nil,
            decision: "merged",
            extra: ["event": "relocalized"]
        )
    }

    private func checkRelocalizationTimeout(now: Date) {
        guard upsertsBlockedForRelocalization,
              !relocalizationTimeoutLogged,
              let worldMapLoadedAt,
              now.timeIntervalSince(worldMapLoadedAt) >= 20 else {
            return
        }
        upsertsBlockedForRelocalization = false
        relocalizationTimeoutLogged = true
        worldMapStatus = "relocalization timeout"
        appendSpatialDiagnostic(
            word: "__system__",
            score: 0,
            elapsedMilliseconds: 0,
            position: nil,
            decision: "rejected",
            extra: ["event": "relocalization_timeout"]
        )
    }

    private func tick(frame: ARFrame) {
        latestFrame = frame
        let now = Date()
        checkRelocalizationTimeout(now: now)
        if now.timeIntervalSince(lastFloorProbeAt) >= 0.6 {
            lastFloorProbeAt = now
            probeFloor(frame: frame)
        }
        if now.timeIntervalSince(lastNamingAt) >= namingInterval, !namingInFlight {
            lastNamingAt = now
            namingInFlight = true
            setNamingStatus("scanning words…")
            onFrameForNaming?(frame.capturedImage, currentProposalCap())
        }
        if now.timeIntervalSince(lastTreeAt) >= 1.0 {
            lastTreeAt = now
            regenerateTree()
        }
    }

    func finishWordScan(_ result: SpatialWordScanResult) {
        namingInFlight = false
        lastScannerOutput = result.debug
        let labels = result.labels
        let now = Date()
        recordScanElapsed(result.elapsedMilliseconds, namerMilliseconds: result.namerMilliseconds)
        if !labels.isEmpty {
            scanWordTimestamps.append(contentsOf: labels.map { _ in now })
            scanWordTimestamps.removeAll { now.timeIntervalSince($0) > 60 }
        }
        let timing = scanTimingStatus(
            currentMilliseconds: result.elapsedMilliseconds,
            proposals: result.proposalsConsidered,
            proposalCap: result.proposalCap
        )
        let wordsPerMinute = scanWordTimestamps.count
        guard let frame = latestFrame, !labels.isEmpty else {
            setNamingStatus("no object words yet · \(timing) · \(wordsPerMinute)/min")
            appendSpatialDiagnostic(
                word: "__none__",
                score: 0,
                elapsedMilliseconds: result.elapsedMilliseconds,
                position: nil,
                decision: "rejected",
                extra: ["reason": "no_confident_words"]
            )
            regenerateTree()
            return
        }
        var permanentChanges = 0
        for label in labels {
            let estimate = positionEstimate(for: label.point, frame: frame)
            let extent = extent(for: label.roi, frame: frame)
            let shape = shapeEstimate(
                for: label.maskPolygon,
                roi: label.roi,
                frame: frame,
                objectPosition: estimate.position,
                extent: extent,
                planeID: estimate.planeID
            )
            if upsertsBlockedForRelocalization {
                let nearest = nearestSameWordObject(label: label.label, position: estimate.position)
                appendSpatialDiagnostic(
                    word: label.label,
                    score: label.score,
                    elapsedMilliseconds: result.elapsedMilliseconds,
                    position: estimate.position,
                    decision: "rejected",
                    matchedID: nearest.map { objects[$0.index].id },
                    distanceToNearestSameWord: nearest?.distance,
                    extra: diagnosticExtra(
                        extent: extent,
                        shape: shape,
                        estimate: estimate,
                        extra: [
                        "reason": "waiting_for_relocalization",
                        ]
                    )
                )
                continue
            }
            let upsert = upsertObject(
                label: label.label,
                estimate: estimate,
                extent: extent,
                shape: shape,
                score: label.score,
                margin: label.margin,
                elapsedMilliseconds: result.elapsedMilliseconds
            )
            if let objectID = upsert.objectID {
                cacheVerificationCrop(
                    for: objectID,
                    frame: frame.capturedImage,
                    roi: label.roi,
                    mobileclipLabel: label.label,
                    score: label.score,
                    margin: label.margin
                )
                maybeStartVerification(for: objectID, reason: label.margin < Self.verificationLowMargin ? "low_margin" : "sightings")
            }
            if upsert.changedPermanentObject {
                permanentChanges += 1
            }
        }
        objectCount = objects.count
        if permanentChanges > 0 {
            scheduleDebouncedSave()
        }
        let gate = upsertsBlockedForRelocalization ? " · waiting relocalization" : ""
        setNamingStatus("scanner \(labels.count) words · \(timing) · \(wordsPerMinute)/min\(gate)")
        regenerateTree()
        postSpatialSnapshotIfNeeded()
    }

    private func recordScanElapsed(_ milliseconds: Int, namerMilliseconds: [Int]) {
        guard milliseconds > 0 else { return }
        scanElapsedSamples.append(milliseconds)
        if scanElapsedSamples.count > 60 {
            scanElapsedSamples.removeFirst(scanElapsedSamples.count - 60)
        }
        namerElapsedSamples.append(contentsOf: namerMilliseconds.filter { $0 > 0 })
        if namerElapsedSamples.count > 120 {
            namerElapsedSamples.removeFirst(namerElapsedSamples.count - 120)
        }
        guard let p95 = percentile(scanElapsedSamples, 0.95) else {
            return
        }
        if p95 > 600, proposalCap > 20 {
            proposalCap = max(20, proposalCap / 2)
            appendSpatialDiagnostic(
                word: "__system__",
                score: 0,
                elapsedMilliseconds: milliseconds,
                position: nil,
                decision: "proposal_cap_reduced",
                extra: ["reason": "scan_p95_over_600ms", "p95_ms": p95, "proposal_cap": proposalCap]
            )
        }
        if p95 > 350, namingInterval < 2.2 {
            namingInterval = 2.2
            appendSpatialDiagnostic(
                word: "__system__",
                score: 0,
                elapsedMilliseconds: milliseconds,
                position: nil,
                decision: "rejected",
                extra: ["event": "scan_rate_halved", "p95_ms": p95]
            )
        }
    }

    private func currentProposalCap() -> Int {
        let thermalState = ProcessInfo.processInfo.thermalState
        switch thermalState {
        case .serious, .critical:
            let capped = max(10, proposalCap / 2)
            if !thermalProposalCapActive {
                thermalProposalCapActive = true
                appendSpatialDiagnostic(
                    word: "__system__",
                    score: 0,
                    elapsedMilliseconds: 0,
                    position: nil,
                    decision: "proposal_cap_reduced",
                    extra: ["reason": "thermal_\(thermalState)", "proposal_cap": capped]
                )
            }
            return capped
        default:
            if thermalProposalCapActive {
                thermalProposalCapActive = false
                appendSpatialDiagnostic(
                    word: "__system__",
                    score: 0,
                    elapsedMilliseconds: 0,
                    position: nil,
                    decision: "proposal_cap_restored",
                    extra: ["proposal_cap": proposalCap]
                )
            }
            return proposalCap
        }
    }

    private func scanTimingStatus(currentMilliseconds: Int, proposals: Int, proposalCap: Int) -> String {
        let current = currentMilliseconds > 0 ? "scan \(currentMilliseconds)ms" : "scan n/a"
        let p50 = percentile(namerElapsedSamples, 0.5).map { "namer p50 \($0)ms" } ?? "namer p50 n/a"
        let p95 = percentile(namerElapsedSamples, 0.95).map { "p95 \($0)ms" } ?? "p95 n/a"
        let throttle = namingInterval > 1.1 ? " · scan 0.5x" : ""
        return "\(current) · \(p50) · \(p95) · proposals \(proposals)/\(proposalCap)\(throttle)"
    }

    private func percentile(_ samples: [Int], _ percentile: Double) -> Int? {
        guard !samples.isEmpty else { return nil }
        let sorted = samples.sorted()
        let rank = Int(ceil(Double(sorted.count) * percentile)) - 1
        return sorted[min(max(rank, 0), sorted.count - 1)]
    }

    func failWordScan(_ message: String) {
        namingInFlight = false
        lastScannerOutput = message
        setNamingStatus("scanner failed: \(message.prefix(80))")
    }

    private func probeFloor(frame: ARFrame) {
        let cameraY = frame.camera.transform.columns.3.y
        for point in [CGPoint(x: 0.5, y: 0.65), CGPoint(x: 0.5, y: 0.5), CGPoint(x: 0.5, y: 0.8)] {
            let query = frame.raycastQuery(
                from: point,
                allowing: .estimatedPlane,
                alignment: .horizontal
            )
            guard let hit = session.raycast(query).first else { continue }
            let pos = simd_float3(
                hit.worldTransform.columns.3.x,
                hit.worldTransform.columns.3.y,
                hit.worldTransform.columns.3.z
            )
            guard pos.y < cameraY - 0.25 else { continue }
            floorProbe = SpatialPlane(
                id: floorProbeID,
                classification: "floor?",
                center: pos,
                extent: simd_float2(1.5, 1.5),
                alignment: "horizontal",
                isEstimated: true
            )
            return
        }
    }

    @discardableResult
    private func upsertObject(
        label: String,
        estimate: SpatialPositionEstimate,
        extent: simd_float2,
        shape: SpatialShapeEstimate,
        score: Float,
        margin: Float,
        elapsedMilliseconds: Int
    ) -> SpatialObjectUpsertResult {
        purgeStalePendingObjects()
        let pos = estimate.position
        let nearestPermanent = nearestSameWordObject(label: label, position: pos)
        if let nearestPermanent, nearestPermanent.distance <= 2.0 {
            mergeObject(
                at: nearestPermanent.index,
                with: pos,
                extent: extent,
                shape: shape,
                score: score,
                margin: margin,
                elapsedMilliseconds: elapsedMilliseconds,
                distance: nearestPermanent.distance,
                estimate: estimate
            )
            return SpatialObjectUpsertResult(objectID: objects[nearestPermanent.index].id, changedPermanentObject: true)
        }

        if let nearestPending = nearestSameWordPending(label: label, position: pos),
           nearestPending.distance <= 0.5 {
            pendingObjects[nearestPending.index].position = pendingObjects[nearestPending.index].position * 0.8 + pos * 0.2
            pendingObjects[nearestPending.index].extent = refinedExtent(old: pendingObjects[nearestPending.index].extent, new: extent)
            pendingObjects[nearestPending.index].footprint = refinedFootprint(old: pendingObjects[nearestPending.index].footprint, new: shape.footprint)
            pendingObjects[nearestPending.index].heightM = refinedDimension(old: pendingObjects[nearestPending.index].heightM, new: shape.heightM)
            pendingObjects[nearestPending.index].sightings += 1
            pendingObjects[nearestPending.index].lastSeen = Date()
            let pending = pendingObjects[nearestPending.index]
            if pending.sightings < 3 {
                appendSpatialDiagnostic(
                    word: label,
                    score: score,
                    elapsedMilliseconds: elapsedMilliseconds,
                    position: pending.position,
                    decision: "pending",
                    distanceToNearestSameWord: nearestPermanent?.distance,
                    extra: diagnosticExtra(
                        extent: pending.extent,
                        shape: SpatialShapeEstimate(footprint: pending.footprint, heightM: pending.heightM),
                        estimate: estimate,
                        extra: [
                            "reason": "needs_3_close_sightings",
                            "pending_distance": rounded(nearestPending.distance),
                            "sightings": pending.sightings,
                        ]
                    )
                )
                return SpatialObjectUpsertResult(objectID: nil, changedPermanentObject: false)
            }
            let stats = initialPositionStats(first: pending.position, second: pos)
            var obj = SpatialObject(
                label: label,
                position: pending.position,
                extent: pending.extent,
                sightings: max(3, pending.sightings),
                lastSeen: Date(),
                footprint: pending.footprint,
                heightM: pending.heightM,
                lastMobileCLIPScore: score,
                lastMobileCLIPMargin: margin,
                positionSampleCount: stats.count,
                positionMean: stats.mean,
                positionM2: stats.m2
            )
            obj.supportPlaneID = supportPlane(for: pending.position)?.id
            let objectID = obj.id
            objects.append(obj)
            pendingObjects.remove(at: nearestPending.index)
            appendSpatialDiagnostic(
                word: label,
                score: score,
                elapsedMilliseconds: elapsedMilliseconds,
                position: obj.position,
                decision: "created",
                matchedID: obj.id,
                distanceToNearestSameWord: nearestPermanent?.distance,
                extra: diagnosticExtra(
                    object: obj,
                    estimate: estimate,
                    extra: [
                    "pending_distance": rounded(nearestPending.distance),
                    ]
                )
            )
            return SpatialObjectUpsertResult(objectID: objectID, changedPermanentObject: true)
        }

        pendingObjects.append(PendingSpatialObject(label: label, position: pos, extent: extent, footprint: shape.footprint, heightM: shape.heightM))
        appendSpatialDiagnostic(
            word: label,
            score: score,
            elapsedMilliseconds: elapsedMilliseconds,
            position: pos,
            decision: "pending",
            distanceToNearestSameWord: nearestPermanent?.distance,
            extra: diagnosticExtra(
                extent: extent,
                shape: shape,
                estimate: estimate,
                extra: ["reason": "first_close_sighting"]
            )
        )
        return SpatialObjectUpsertResult(objectID: nil, changedPermanentObject: false)
    }

    private func mergeObject(
        at idx: Int,
        with pos: simd_float3,
        extent: simd_float2,
        shape: SpatialShapeEstimate,
        score: Float,
        margin: Float,
        elapsedMilliseconds: Int,
        distance: Float,
        estimate: SpatialPositionEstimate
    ) {
        let wasPhantom = objects[idx].phantom
        updatePositionStats(at: idx, with: pos)
        objects[idx].position = objects[idx].position * 0.8 + pos * 0.2
        objects[idx].extent = refinedExtent(old: objects[idx].extent, new: extent)
        objects[idx].footprint = refinedFootprint(old: objects[idx].footprint, new: shape.footprint)
        objects[idx].heightM = refinedDimension(old: objects[idx].heightM, new: shape.heightM)
        objects[idx].sightings += 1
        objects[idx].lastSeen = Date()
        objects[idx].lastMobileCLIPScore = score
        objects[idx].lastMobileCLIPMargin = margin
        objects[idx].supportPlaneID = supportPlane(for: objects[idx].position)?.id
        if wasPhantom {
            verificationAttempts[objects[idx].id] = 0
            verificationLastAttempt.removeValue(forKey: objects[idx].id)
            phantomRejudgeAllowed.insert(objects[idx].id)
        }
        appendSpatialDiagnostic(
            word: objects[idx].label,
            score: score,
            elapsedMilliseconds: elapsedMilliseconds,
            position: objects[idx].position,
            decision: "merged",
            matchedID: objects[idx].id,
            distanceToNearestSameWord: distance,
            extra: diagnosticExtra(
                object: objects[idx],
                estimate: estimate,
                extra: [
                "sightings": objects[idx].sightings,
                ]
            )
        )
        if wasPhantom {
            appendSpatialDiagnostic(
                word: objects[idx].label,
                score: score,
                elapsedMilliseconds: elapsedMilliseconds,
                position: objects[idx].position,
                decision: "phantom_resighted",
                matchedID: objects[idx].id,
                distanceToNearestSameWord: distance,
                extra: [
                    "sightings": objects[idx].sightings,
                    "strikes": objects[idx].phantomStrikes,
                ]
            )
        }
    }

    private func nearestSameWordObject(label: String, position: simd_float3) -> (index: Int, distance: Float)? {
        objects.enumerated()
            .filter { $0.element.label == label }
            .map { (index: $0.offset, distance: simd_distance($0.element.position, position)) }
            .min { $0.distance < $1.distance }
    }

    private func nearestSameWordPending(label: String, position: simd_float3) -> (index: Int, distance: Float)? {
        pendingObjects.enumerated()
            .filter { $0.element.label == label }
            .map { (index: $0.offset, distance: simd_distance($0.element.position, position)) }
            .min { $0.distance < $1.distance }
    }

    private func purgeStalePendingObjects() {
        let now = Date()
        pendingObjects.removeAll { now.timeIntervalSince($0.lastSeen) > 30 }
    }

    private func initialPositionStats(first: simd_float3, second: simd_float3) -> (count: Int, mean: simd_float3, m2: Float) {
        let mean = (first + second) / 2
        let m2 = simd_length_squared(first - mean) + simd_length_squared(second - mean)
        return (2, mean, m2)
    }

    private func updatePositionStats(at idx: Int, with sample: simd_float3) {
        let nextCount = max(1, objects[idx].positionSampleCount) + 1
        let delta = sample - objects[idx].positionMean
        let nextMean = objects[idx].positionMean + delta / Float(nextCount)
        let delta2 = sample - nextMean
        objects[idx].positionSampleCount = nextCount
        objects[idx].positionMean = nextMean
        objects[idx].positionM2 += simd_dot(delta, delta2)
    }

    private func diagnosticExtra(
        object: SpatialObject,
        estimate: SpatialPositionEstimate,
        extra: [String: Any] = [:]
    ) -> [String: Any] {
        var payload = diagnosticExtra(
            extent: object.extent,
            shape: SpatialShapeEstimate(footprint: object.footprint, heightM: object.heightM),
            estimate: estimate,
            extra: extra
        )
        payload["verified"] = object.verified
        payload["position_spread"] = rounded(object.positionSpread)
        payload["position_confidence"] = object.positionConfidence
        payload["mobileclip_margin"] = rounded(object.lastMobileCLIPMargin)
        payload["mobileclip_score"] = rounded(object.lastMobileCLIPScore)
        if !object.relabeledFrom.isEmpty {
            payload["relabeled_from"] = object.relabeledFrom
        }
        return payload
    }

    private func diagnosticExtra(
        extent: simd_float2,
        shape: SpatialShapeEstimate? = nil,
        estimate: SpatialPositionEstimate,
        extra: [String: Any] = [:]
    ) -> [String: Any] {
        var payload: [String: Any] = [
            "w": rounded(extent.x),
            "h": rounded(extent.y),
            "camera_pos": [
                rounded(estimate.cameraPosition.x),
                rounded(estimate.cameraPosition.y),
                rounded(estimate.cameraPosition.z),
            ],
            "camera_forward": [
                rounded(estimate.cameraForward.x),
                rounded(estimate.cameraForward.y),
                rounded(estimate.cameraForward.z),
            ],
            "used_raycast": estimate.usedRaycast,
        ]
        if let shape {
            payload["height_m"] = rounded(shape.heightM)
            if !shape.footprint.isEmpty {
                payload["footprint_points"] = shape.footprint.count
            }
        }
        if let raycastDistance = estimate.raycastDistance {
            payload["raycast_distance"] = rounded(raycastDistance)
        }
        if let planeID = estimate.planeID {
            payload["plane_id"] = planeID.uuidString
        }
        for (key, value) in extra {
            payload[key] = value
        }
        return payload
    }

    private func appendSpatialDiagnostic(
        word: String,
        score: Float,
        elapsedMilliseconds: Int,
        position: simd_float3?,
        decision: String,
        matchedID: UUID? = nil,
        distanceToNearestSameWord: Float? = nil,
        extra: [String: Any] = [:]
    ) {
        var payload: [String: Any] = [
            "ts": ISO8601DateFormatter().string(from: Date()),
            "word": word,
            "score": rounded(score),
            "ms": elapsedMilliseconds,
            "decision": decision,
        ]
        if let position {
            payload["pos"] = [
                rounded(position.x),
                rounded(position.y),
                rounded(position.z),
            ]
        }
        if let matchedID {
            payload["matched_id"] = matchedID.uuidString
        }
        if let distanceToNearestSameWord {
            payload["dist_to_nearest_same_word"] = rounded(distanceToNearestSameWord)
        }
        for (key, value) in extra {
            payload[key] = value
        }
        guard JSONSerialization.isValidJSONObject(payload),
              let data = try? JSONSerialization.data(withJSONObject: payload) else {
            return
        }
        var line = data
        line.append(0x0A)
        let url = diagnosticsURL
        if !FileManager.default.fileExists(atPath: url.path) {
            FileManager.default.createFile(atPath: url.path, contents: nil)
        }
        guard let handle = try? FileHandle(forWritingTo: url) else { return }
        do {
            try handle.seekToEnd()
            try handle.write(contentsOf: line)
            try handle.close()
        } catch {
            try? handle.close()
        }
    }

    private func rounded(_ value: Float) -> Double {
        Double(round(value * 1000) / 1000)
    }

    private nonisolated static func appendPerceptionSpool(_ body: Data) -> Bool {
        perceptionSpoolQueue.sync {
            let fileManager = FileManager.default
            let base = fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
                ?? fileManager.temporaryDirectory
            let dir = base.appendingPathComponent("SOMA", isDirectory: true)
            let url = dir.appendingPathComponent("perception_spool.ndjson")
            do {
                try fileManager.createDirectory(at: dir, withIntermediateDirectories: true)
                if !fileManager.fileExists(atPath: url.path) {
                    fileManager.createFile(atPath: url.path, contents: nil)
                }
                let handle = try FileHandle(forWritingTo: url)
                defer { try? handle.close() }
                try handle.seekToEnd()
                try handle.write(contentsOf: body)
                try handle.write(contentsOf: Data("\n".utf8))
                return true
            } catch {
                return false
            }
        }
    }

    private func recordSpatialPostOutcome(signature: String, postedAt: Date, spooled: Bool) {
        lastPostedSignature = signature
        lastPostAt = postedAt
        if spooled {
            spatialPostsSpooled += 1
        } else {
            spatialPostsOK += 1
        }
        setNamingStatus(lastNamingStatusCore)
        appendSpatialDiagnostic(
            word: "__post__", score: 0, elapsedMilliseconds: 0,
            position: nil, decision: spooled ? "post_spooled" : "post_ok",
            extra: ["ok_total": spatialPostsOK, "spooled_total": spatialPostsSpooled]
        )
    }

    private func raycastHit(for point: CGPoint, frame: ARFrame) -> (position: simd_float3, planeID: UUID?)? {
        let query = frame.raycastQuery(
            from: point,
            allowing: .estimatedPlane,
            alignment: .any
        )
        guard let hit = session.raycast(query).first else { return nil }
        return (
            simd_float3(
            hit.worldTransform.columns.3.x,
            hit.worldTransform.columns.3.y,
            hit.worldTransform.columns.3.z
            ),
            hit.anchor?.identifier
        )
    }

    private func raycastPosition(for point: CGPoint, frame: ARFrame) -> simd_float3? {
        raycastHit(for: point, frame: frame)?.position
    }

    private func extent(for roi: CGRect?, frame: ARFrame) -> simd_float2 {
        guard let roi else { return .zero }
        let minX = min(max(roi.minX, 0), 1)
        let maxX = min(max(roi.maxX, 0), 1)
        let minY = min(max(roi.minY, 0), 1)
        let maxY = min(max(roi.maxY, 0), 1)
        guard maxX > minX, maxY > minY else { return .zero }

        let midX = (minX + maxX) / 2
        let midY = (minY + maxY) / 2
        let left = raycastPosition(for: CGPoint(x: minX, y: 1 - midY), frame: frame)
        let right = raycastPosition(for: CGPoint(x: maxX, y: 1 - midY), frame: frame)
        let top = raycastPosition(for: CGPoint(x: midX, y: 1 - maxY), frame: frame)
        let bottom = raycastPosition(for: CGPoint(x: midX, y: 1 - minY), frame: frame)

        return simd_float2(
            dimensionBetween(left, right),
            dimensionBetween(top, bottom)
        )
    }

    private func shapeEstimate(
        for maskPolygon: [CGPoint],
        roi: CGRect?,
        frame: ARFrame,
        objectPosition: simd_float3,
        extent: simd_float2,
        planeID: UUID?
    ) -> SpatialShapeEstimate {
        let rawPolygon = maskPolygon.isEmpty ? screenPolygon(forVisionROI: roi) : maskPolygon
        let polygon = simplifyPolygon(rawPolygon, maxPoints: 24, tolerance: 0.015)
        let hits = polygon.compactMap { raycastPosition(for: clampedScreenPoint($0), frame: frame) }
        let plane = planeID.flatMap { planes[$0] } ?? supportPlane(for: objectPosition)
        let origin = plane?.center ?? objectPosition

        let worldFootprint: [simd_float3]
        if hits.count >= 3 {
            worldFootprint = hits
        } else {
            worldFootprint = fallbackFootprintWorldPoints(center: objectPosition, extent: extent)
        }

        let footprint = worldFootprint
            .prefix(24)
            .map { point in
                [
                    Float(round((point.x - origin.x) * 1000) / 1000),
                    Float(round((point.z - origin.z) * 1000) / 1000),
                ]
            }
        let hitYValues = hits.map { $0.y }
        let raycastHeight = hitYValues.isEmpty ? 0 : (hitYValues.max() ?? 0) - (hitYValues.min() ?? 0)
        let height = max(extent.y, raycastHeight.isFinite ? raycastHeight : 0)
        return SpatialShapeEstimate(footprint: footprint, heightM: height.isFinite ? max(0, height) : 0)
    }

    private func screenPolygon(forVisionROI roi: CGRect?) -> [CGPoint] {
        guard let roi else { return [] }
        let minX = min(max(roi.minX, 0), 1)
        let maxX = min(max(roi.maxX, 0), 1)
        let minY = min(max(roi.minY, 0), 1)
        let maxY = min(max(roi.maxY, 0), 1)
        guard maxX > minX, maxY > minY else { return [] }
        return [
            CGPoint(x: minX, y: 1 - minY),
            CGPoint(x: maxX, y: 1 - minY),
            CGPoint(x: maxX, y: 1 - maxY),
            CGPoint(x: minX, y: 1 - maxY),
        ]
    }

    private func fallbackFootprintWorldPoints(center: simd_float3, extent: simd_float2) -> [simd_float3] {
        let width = extent.x.isFinite && extent.x > 0 ? extent.x : 0.25
        let depthCandidate = extent.y.isFinite && extent.y > 0 ? extent.y * 0.45 : width * 0.65
        let depth = min(0.6, max(0.08, depthCandidate))
        let halfW = width / 2
        let halfD = depth / 2
        return [
            simd_float3(center.x - halfW, center.y, center.z - halfD),
            simd_float3(center.x + halfW, center.y, center.z - halfD),
            simd_float3(center.x + halfW, center.y, center.z + halfD),
            simd_float3(center.x - halfW, center.y, center.z + halfD),
        ]
    }

    private func clampedScreenPoint(_ point: CGPoint) -> CGPoint {
        CGPoint(x: min(max(point.x, 0), 1), y: min(max(point.y, 0), 1))
    }

    private func simplifyPolygon(_ points: [CGPoint], maxPoints: Int, tolerance: CGFloat) -> [CGPoint] {
        guard points.count > maxPoints else { return points }
        var simplified = douglasPeucker(points, tolerance: tolerance)
        var nextTolerance = tolerance
        while simplified.count > maxPoints, nextTolerance < 0.25 {
            nextTolerance *= 1.5
            simplified = douglasPeucker(points, tolerance: nextTolerance)
        }
        if simplified.count > maxPoints {
            let step = Double(simplified.count) / Double(maxPoints)
            simplified = (0..<maxPoints).map { simplified[min(simplified.count - 1, Int(Double($0) * step))] }
        }
        return simplified
    }

    private func douglasPeucker(_ points: [CGPoint], tolerance: CGFloat) -> [CGPoint] {
        guard points.count > 2 else { return points }
        let first = points[0]
        let last = points[points.count - 1]
        var maxDistance: CGFloat = 0
        var splitIndex = 0
        for idx in 1..<(points.count - 1) {
            let distance = perpendicularDistance(points[idx], lineStart: first, lineEnd: last)
            if distance > maxDistance {
                maxDistance = distance
                splitIndex = idx
            }
        }
        guard maxDistance > tolerance else { return [first, last] }
        let left = douglasPeucker(Array(points[0...splitIndex]), tolerance: tolerance)
        let right = douglasPeucker(Array(points[splitIndex..<points.count]), tolerance: tolerance)
        return Array(left.dropLast()) + right
    }

    private func perpendicularDistance(_ point: CGPoint, lineStart: CGPoint, lineEnd: CGPoint) -> CGFloat {
        let dx = lineEnd.x - lineStart.x
        let dy = lineEnd.y - lineStart.y
        guard dx != 0 || dy != 0 else {
            return hypot(point.x - lineStart.x, point.y - lineStart.y)
        }
        let numerator = abs(dy * point.x - dx * point.y + lineEnd.x * lineStart.y - lineEnd.y * lineStart.x)
        return numerator / hypot(dx, dy)
    }

    private func dimensionBetween(_ a: simd_float3?, _ b: simd_float3?) -> Float {
        guard let a, let b else { return 0 }
        let distance = simd_distance(a, b)
        return distance.isFinite && distance > 0 ? distance : 0
    }

    private func refinedExtent(old: simd_float2, new: simd_float2) -> simd_float2 {
        simd_float2(
            refinedDimension(old: old.x, new: new.x),
            refinedDimension(old: old.y, new: new.y)
        )
    }

    private func refinedFootprint(old: [[Float]], new: [[Float]]) -> [[Float]] {
        guard !new.isEmpty else { return old }
        guard !old.isEmpty else { return new }
        guard old.count == new.count else { return old }
        return zip(old, new).map { oldPoint, newPoint in
            guard oldPoint.count >= 2, newPoint.count >= 2 else { return oldPoint }
            return [
                oldPoint[0] * 0.85 + newPoint[0] * 0.15,
                oldPoint[1] * 0.85 + newPoint[1] * 0.15,
            ]
        }
    }

    private func refinedDimension(old: Float, new: Float) -> Float {
        if old > 0, new > 0 {
            return old * 0.8 + new * 0.2
        }
        if old > 0 { return old }
        if new > 0 { return new }
        return 0
    }

    private func positionEstimate(for point: CGPoint, frame: ARFrame) -> SpatialPositionEstimate {
        let transform = frame.camera.transform
        let camera = simd_float3(transform.columns.3.x, transform.columns.3.y, transform.columns.3.z)
        let right = simd_normalize(simd_float3(transform.columns.0.x, transform.columns.0.y, transform.columns.0.z))
        let up = simd_normalize(simd_float3(transform.columns.1.x, transform.columns.1.y, transform.columns.1.z))
        let forward = simd_normalize(-simd_float3(transform.columns.2.x, transform.columns.2.y, transform.columns.2.z))

        if let hit = raycastHit(for: point, frame: frame) {
            return SpatialPositionEstimate(
                position: hit.position,
                cameraPosition: camera,
                cameraForward: forward,
                raycastDistance: simd_distance(camera, hit.position),
                planeID: hit.planeID,
                usedRaycast: true
            )
        }

        let lateral = Float(point.x - 0.5) * 2.2
        let distance = Float(1.1 + (1.0 - point.y) * 1.7)
        let vertical = Float(0.5 - point.y) * 0.45
        let position = camera + forward * distance + right * lateral + up * vertical
        return SpatialPositionEstimate(
            position: position,
            cameraPosition: camera,
            cameraForward: forward,
            raycastDistance: nil,
            planeID: supportPlane(for: position)?.id,
            usedRaycast: false
        )
    }

    private func cacheVerificationCrop(
        for objectID: UUID,
        frame: CVImageBuffer,
        roi: CGRect?,
        mobileclipLabel: String,
        score: Float,
        margin: Float
    ) {
        guard let crop = verificationCropImage(from: frame, roi: roi) else { return }
        let now = Date()
        verificationCrops[objectID] = SpatialVerificationCrop(
            image: crop,
            mobileclipLabel: mobileclipLabel,
            score: score,
            margin: margin,
            updatedAt: now
        )
        verificationCrops = verificationCrops.filter { now.timeIntervalSince($0.value.updatedAt) < 180 }
    }

    private static let cropAnalysisContext = CIContext(options: [.workingColorSpace: NSNull()])

    private static func cropLooksInformative(_ image: CIImage) -> Bool {
        let extent = image.extent
        guard !extent.isInfinite, extent.width > 1, extent.height > 1 else { return false }
        let vector = CIVector(x: extent.origin.x, y: extent.origin.y, z: extent.width, w: extent.height)
        guard let filter = CIFilter(
            name: "CIAreaMinMax",
            parameters: [kCIInputImageKey: image, kCIInputExtentKey: vector]
        ), let output = filter.outputImage else {
            return true // cannot analyze — do not block verification
        }
        var pixels = [UInt8](repeating: 0, count: 8)
        cropAnalysisContext.render(
            output,
            toBitmap: &pixels,
            rowBytes: 8,
            bounds: CGRect(x: 0, y: 0, width: 2, height: 1),
            format: .RGBA8,
            colorSpace: nil
        )
        let spread = max(
            Int(pixels[4]) - Int(pixels[0]),
            Int(pixels[5]) - Int(pixels[1]),
            Int(pixels[6]) - Int(pixels[2])
        )
        return spread >= 24
    }

    private func verificationCropImage(from frame: CVImageBuffer, roi: CGRect?) -> CIImage? {
        guard let roi else { return nil }
        let image = CIImage(cvPixelBuffer: frame).oriented(.right)
        let extent = image.extent
        guard extent.width > 1, extent.height > 1 else { return nil }
        let minX = min(max(roi.minX, 0), 1)
        let minY = min(max(roi.minY, 0), 1)
        let maxX = min(max(roi.maxX, 0), 1)
        let maxY = min(max(roi.maxY, 0), 1)
        guard maxX - minX > 0.02, maxY - minY > 0.02 else { return nil }
        let rect = CGRect(
            x: extent.minX + minX * extent.width,
            y: extent.minY + minY * extent.height,
            width: (maxX - minX) * extent.width,
            height: (maxY - minY) * extent.height
        ).intersection(extent)
        guard !rect.isNull, rect.width > 8, rect.height > 8 else { return nil }
        return image
            .cropped(to: rect)
            .transformed(by: CGAffineTransform(translationX: -rect.minX, y: -rect.minY))
    }

    private func maybeStartVerification(for objectID: UUID, reason: String) {
        guard let idx = objects.firstIndex(where: { $0.id == objectID }) else { return }
        let object = objects[idx]
        guard !object.verified else { return }
        if object.phantom && !phantomRejudgeAllowed.contains(objectID) { return }
        guard object.sightings >= 3 || object.lastMobileCLIPMargin < Self.verificationLowMargin else { return }
        guard !verificationInFlight else { return }
        let now = Date()
        guard now.timeIntervalSince(lastVerificationAt) >= Self.verificationCooldown else { return }
        // Per-object backoff: rejected objects retry at growing intervals
        // and give up after 6 attempts this session, so one garbage-crop
        // object cannot starve verification for the whole world.
        let attempts = verificationAttempts[objectID, default: 0]
        if attempts >= 6 {
            if attempts == 6 {
                verificationAttempts[objectID] = 7
                appendSpatialDiagnostic(
                    word: object.label,
                    score: object.lastMobileCLIPScore,
                    elapsedMilliseconds: 0,
                    position: object.position,
                    decision: "verification_exhausted",
                    matchedID: object.id,
                    extra: ["attempts": 6]
                )
            }
            return
        }
        if let lastAttempt = verificationLastAttempt[objectID],
           now.timeIntervalSince(lastAttempt) < Double(60 * max(1, attempts)) {
            return
        }
        guard ProcessInfo.processInfo.thermalState != .critical else {
            appendSpatialDiagnostic(
                word: object.label,
                score: object.lastMobileCLIPScore,
                elapsedMilliseconds: 0,
                position: object.position,
                decision: "verification_skipped",
                matchedID: object.id,
                extra: ["reason": "thermal_critical"]
            )
            return
        }
        guard let crop = verificationCrops[objectID] else { return }
        verificationAttempts[objectID] = attempts + 1
        verificationLastAttempt[objectID] = now
        guard Self.cropLooksInformative(crop.image) else {
            // Black/uniform crops made FastVLM describe "a solid black
            // background" (2026-06-12 diag). Drop it so a fresh crop is
            // cached on the next sighting.
            verificationCrops.removeValue(forKey: objectID)
            appendSpatialDiagnostic(
                word: object.label,
                score: crop.score,
                elapsedMilliseconds: 0,
                position: object.position,
                decision: "verification_skipped",
                matchedID: object.id,
                extra: ["reason": "uniform_crop"]
            )
            return
        }
        verificationInFlight = true
        lastVerificationAt = now
        appendSpatialDiagnostic(
            word: object.label,
            score: crop.score,
            elapsedMilliseconds: 0,
            position: object.position,
            decision: "verification_started",
            matchedID: object.id,
            extra: [
                "reason": reason,
                "mobileclip_margin": rounded(crop.margin),
                "sightings": object.sightings,
            ]
        )
        onVerifyObjectName?(object.id, crop.image, object.label)
    }

    func finishVerification(objectID: UUID, rawOutput: String, elapsedMilliseconds: Int) {
        verificationInFlight = false
        // Always discard the consumed crop: a rejected verification must
        // retry with FRESH pixels, not loop on the same stale crop
        // (2026-06-12: one object burned 30+ FastVLM calls on one crop).
        let consumedCrop = verificationCrops[objectID]
        verificationCrops.removeValue(forKey: objectID)
        guard let idx = objects.firstIndex(where: { $0.id == objectID }) else { return }
        let oldLabel = objects[idx].label
        guard let verifiedLabel = cleanVerifiedSpatialLabel(rawOutput) else {
            if verificationOutputIsPhantomTell(rawOutput), let crop = consumedCrop {
                let previousCropAt = phantomLastStrikeCropAt[objectID]
                let distinctCrop = previousCropAt.map { abs($0.timeIntervalSince(crop.updatedAt)) > 0.001 } ?? true
                if distinctCrop {
                    objects[idx].phantomStrikes += 1
                    phantomLastStrikeCropAt[objectID] = crop.updatedAt
                }
                let strikes = objects[idx].phantomStrikes
                let decision = strikes >= 3 ? "phantom_marked" : "phantom_strike"
                if strikes >= 3 {
                    objects[idx].phantom = true
                    phantomRejudgeAllowed.remove(objectID)
                }
                appendSpatialDiagnostic(
                    word: oldLabel,
                    score: objects[idx].lastMobileCLIPScore,
                    elapsedMilliseconds: elapsedMilliseconds,
                    position: objects[idx].position,
                    decision: decision,
                    matchedID: objects[idx].id,
                    extra: [
                        "raw": String(rawOutput.prefix(160)),
                        "sightings": objects[idx].sightings,
                        "strikes": strikes,
                        "distinct_crop": distinctCrop,
                    ]
                )
                objectCount = objects.count
                setNamingStatus(lastNamingStatusCore)
                scheduleDebouncedSave()
                if strikes >= 3 {
                    regenerateTree()
                    postSpatialSnapshotIfNeeded()
                }
                return
            }
            appendSpatialDiagnostic(
                word: oldLabel,
                score: objects[idx].lastMobileCLIPScore,
                elapsedMilliseconds: elapsedMilliseconds,
                position: objects[idx].position,
                decision: "verification_rejected",
                matchedID: objects[idx].id,
                extra: ["raw": String(rawOutput.prefix(160))]
            )
            return
        }
        let hadPhantomState = objects[idx].phantom || objects[idx].phantomStrikes > 0
        if verifiedLabel != oldLabel {
            if !objects[idx].relabeledFrom.contains(oldLabel) {
                objects[idx].relabeledFrom.append(oldLabel)
            }
            objects[idx].label = verifiedLabel
        }
        objects[idx].verified = true
        objects[idx].phantomStrikes = 0
        objects[idx].phantom = false
        objects[idx].lastSeen = Date()
        phantomLastStrikeCropAt.removeValue(forKey: objectID)
        phantomRejudgeAllowed.remove(objectID)
        appendSpatialDiagnostic(
            word: objects[idx].label,
            score: objects[idx].lastMobileCLIPScore,
            elapsedMilliseconds: elapsedMilliseconds,
            position: objects[idx].position,
            decision: verifiedLabel == oldLabel ? "verified" : "relabeled",
            matchedID: objects[idx].id,
            extra: [
                "verified_label": verifiedLabel,
                "relabeled_from": oldLabel,
                "raw": String(rawOutput.prefix(160)),
                "sightings": objects[idx].sightings,
                "position_spread": rounded(objects[idx].positionSpread),
            ]
        )
        if hadPhantomState {
            appendSpatialDiagnostic(
                word: objects[idx].label,
                score: objects[idx].lastMobileCLIPScore,
                elapsedMilliseconds: elapsedMilliseconds,
                position: objects[idx].position,
                decision: "phantom_cleared",
                matchedID: objects[idx].id,
                extra: [
                    "verified_label": verifiedLabel,
                    "relabeled_from": oldLabel,
                    "raw": String(rawOutput.prefix(160)),
                    "sightings": objects[idx].sightings,
                ]
            )
        }
        objectCount = objects.count
        setNamingStatus(lastNamingStatusCore)
        scheduleDebouncedSave()
        regenerateTree()
        postSpatialSnapshotIfNeeded()
    }

    func failVerification(objectID: UUID, message: String) {
        verificationInFlight = false
        guard let object = objects.first(where: { $0.id == objectID }) else { return }
        appendSpatialDiagnostic(
            word: object.label,
            score: object.lastMobileCLIPScore,
            elapsedMilliseconds: 0,
            position: object.position,
            decision: "verification_failed",
            matchedID: object.id,
            extra: ["reason": String(message.prefix(160))]
        )
    }

    private func parseFastVLMSpatialLabels(_ output: String) -> [SpatialLabelCandidate] {
        var seen = Set<String>()
        var parsed: [SpatialLabelCandidate] = []
        let lines = output.components(separatedBy: .newlines)
        for rawLine in lines {
            let line = rawLine
                .replacingOccurrences(of: #"^\s*[-*•]?\s*\d*\.?\s*"#, with: "", options: .regularExpression)
                .trimmingCharacters(in: .whitespacesAndNewlines)
            guard !line.isEmpty else { continue }

            let parts = line.components(separatedBy: "|")
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { !$0.isEmpty }
            let labelCandidate: String
            let zoneCandidate: String
            if parts.count >= 3, (parts[0].lowercased().contains("word") || parts[0].lowercased().contains("object")) {
                labelCandidate = parts[1]
                zoneCandidate = parts[2]
            } else if parts.count >= 2 {
                labelCandidate = parts[0]
                zoneCandidate = parts[1]
            } else {
                let split = line.components(separatedBy: " - ")
                labelCandidate = split.first ?? line
                zoneCandidate = split.dropFirst().joined(separator: " ")
            }

            guard let label = cleanSpatialLabel(labelCandidate) else { continue }
            let key = label.lowercased()
            guard !seen.contains(key) else { continue }
            seen.insert(key)
            parsed.append(SpatialLabelCandidate(label: label, point: pointForZone(zoneCandidate + " " + line)))
            if parsed.count >= 16 { break }
        }
        if parsed.isEmpty {
            parsed = parseLooseFastVLMWords(output)
        }
        return parsed
    }

    private func parseLooseFastVLMWords(_ output: String) -> [SpatialLabelCandidate] {
        var text = output
            .lowercased()
            .replacingOccurrences(of: "\n", with: ",")
            .replacingOccurrences(of: " and ", with: ",")
            .replacingOccurrences(of: " with ", with: ",")
            .replacingOccurrences(of: " on ", with: ",")
            .replacingOccurrences(of: " near ", with: ",")
            .replacingOccurrences(of: " next to ", with: ",")
            .replacingOccurrences(of: "there is", with: "")
            .replacingOccurrences(of: "there are", with: "")
            .replacingOccurrences(of: "i can see", with: "")
            .replacingOccurrences(of: "visible", with: "")
            .replacingOccurrences(of: "objects:", with: "")
            .replacingOccurrences(of: "words:", with: "")
        text = text.replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)

        var seen = Set<String>()
        var labels: [SpatialLabelCandidate] = []
        for chunk in text.components(separatedBy: ",") {
            guard let label = cleanSpatialLabel(chunk) else { continue }
            let key = label.lowercased()
            guard !seen.contains(key) else { continue }
            seen.insert(key)
            labels.append(SpatialLabelCandidate(label: label, point: pointForZone(chunk)))
            if labels.count >= 16 { break }
        }
        return labels
    }

    private func cleanSpatialLabel(_ label: String) -> String? {
        let text = label
            .lowercased()
            .replacingOccurrences(of: #"^(visible|a|an|the|this|that|some)\s+"#, with: "", options: .regularExpression)
            .replacingOccurrences(of: #"\s+(object|thing|item|area|region)$"#, with: "", options: .regularExpression)
            .replacingOccurrences(of: #"\b(at|in|is|are|maybe|likely|possibly|appears|looks like)\b"#, with: " ", options: .regularExpression)
            .replacingOccurrences(of: #"[^a-z0-9 /\-]+"#, with: " ", options: .regularExpression)
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return canonicalSpatialWord(text, confidence: 0.45)
    }

    private func pointForZone(_ zone: String) -> CGPoint {
        let lower = zone.lowercased()
        let x: CGFloat
        if lower.contains("left") {
            x = 0.22
        } else if lower.contains("right") {
            x = 0.78
        } else {
            x = 0.5
        }
        let y: CGFloat
        if lower.contains("upper") || lower.contains("top") {
            y = 0.25
        } else if lower.contains("lower") || lower.contains("bottom") {
            y = 0.76
        } else {
            y = 0.52
        }
        return CGPoint(x: x, y: y)
    }

    private func supportPlane(for pos: simd_float3) -> SpatialPlane? {
        // The highest horizontal plane under the object within 0.6m vertically
        // and whose footprint contains it (with 0.3m margin).
        planeCandidates()
            .filter { $0.alignment == "horizontal" }
            .filter { plane in
                let dy = pos.y - plane.center.y
                guard dy > -0.15, dy < 0.6 else { return false }
                let dx = abs(pos.x - plane.center.x), dz = abs(pos.z - plane.center.z)
                return dx < plane.extent.x / 2 + 0.3 && dz < plane.extent.y / 2 + 0.3
            }
            .max { $0.center.y < $1.center.y }
    }

    // MARK: words

    private func planeCandidates() -> [SpatialPlane] {
        var candidates = Array(planes.values)
        if let floorProbe {
            candidates.append(floorProbe)
        }
        return candidates
    }

    private func floorCandidate(from candidates: [SpatialPlane]) -> SpatialPlane? {
        if let classified = candidates.first(where: { $0.classification == "floor" }) {
            return classified
        }
        if let estimated = floorProbe {
            return estimated
        }
        return candidates
            .filter { $0.alignment == "horizontal" && $0.classification != "ceiling" }
            .filter { $0.center.y < -0.35 }
            .min { $0.center.y < $1.center.y }
    }

    private func planeDisplayName(_ plane: SpatialPlane) -> String {
        if plane.isEstimated {
            return plane.classification
        }
        return plane.classification == "surface" ? "horizontal surface" : plane.classification
    }

    private func regenerateTree() {
        guard let genesisAt else { return }
        let fmt = DateFormatter(); fmt.dateFormat = "HH:mm:ss"
        var lines: [String] = []
        lines.append("place (genesis \(fmt.string(from: genesisAt)), tracking \(trackingState))")
        lines.append("sensors (plane classification \(ARPlaneAnchor.isClassificationSupported ? "supported" : "unavailable"), \(namingStatus))")

        let candidates = planeCandidates()
        let floor = floorCandidate(from: candidates)
        let floorID = floor?.id
        let surfaces = candidates
            .filter { $0.alignment == "horizontal" && $0.classification != "floor" && $0.classification != "ceiling" && $0.id != floorID }
            .sorted { $0.extent.x * $0.extent.y > $1.extent.x * $1.extent.y }
        let verticals = candidates.filter { $0.alignment == "vertical" }
        let confirmed = objects.filter { $0.sightings >= 1 && !$0.phantom }
        regenerateWords(floor: floor, surfaces: Array(surfaces.prefix(8)), verticals: verticals, objects: confirmed)

        func describe(_ v: simd_float3) -> String {
            let dist = simd_length(simd_float2(v.x, v.z))
            let side = v.x < -0.4 ? "left" : (v.x > 0.4 ? "right" : "ahead")
            return String(format: "%.1fm %@", dist, side)
        }

        if let floor {
            let source = floor.classification == "floor"
                ? "classified"
                : (floor.isEstimated ? "estimated raycast" : "lowest horizontal surface")
            lines.append(String(format: "└ floor (%@, %.1f×%.1fm, %@)", source, floor.extent.x, floor.extent.y, describe(floor.center)))
            let onFloor = confirmed.filter { $0.supportPlaneID == floor.id }
            for obj in onFloor.sorted(by: { $0.sightings > $1.sightings }) {
                lines.append("  ├ \(obj.label) — \(describe(obj.position)) on floor ×\(obj.sightings)")
            }
        } else {
            lines.append("└ floor (not yet found — move sideways over textured floor)")
        }

        for surface in surfaces.prefix(5) {
            let onIt = confirmed.filter { $0.supportPlaneID == surface.id }
            let surfaceName = planeDisplayName(surface)
            lines.append(String(format: "  └ %@ (%.1f×%.1fm, %@)", surfaceName, surface.extent.x, surface.extent.y, describe(surface.center)))
            for obj in onIt.sorted(by: { $0.sightings > $1.sightings }) {
                let rel = obj.position - surface.center
                let side = rel.x < -0.15 ? "left" : (rel.x > 0.15 ? "right" : "center")
                lines.append(String(format: "    ├ %@ — %.1fm %@ of %@ center ×%d", obj.label, simd_length(simd_float2(rel.x, rel.z)), side, surfaceName, obj.sightings))
            }
        }

        let unsupported = confirmed.filter { obj in
            guard let supportPlaneID = obj.supportPlaneID else { return true }
            if supportPlaneID == floorID { return false }
            return !surfaces.prefix(5).contains { $0.id == supportPlaneID }
        }
        if !unsupported.isEmpty {
            lines.append("  └ elsewhere")
            for obj in unsupported.sorted(by: { $0.sightings > $1.sightings }).prefix(8) {
                lines.append("    ├ \(obj.label) — \(describe(obj.position)) ×\(obj.sightings)")
            }
        }
        for v in verticals.filter({ ["door", "window"].contains($0.classification) }).prefix(4) {
            lines.append("  └ \(v.classification) — \(describe(v.center))")
        }
        worldText = lines.joined(separator: "\n")
        postSpatialSnapshotIfNeeded()
    }

    private func regenerateWords(
        floor: SpatialPlane?,
        surfaces: [SpatialPlane],
        verticals: [SpatialPlane],
        objects: [SpatialObject]
    ) {
        var next: [SpatialWord] = []
        if let floor {
            next.append(SpatialWord(
                id: floor.id,
                label: "floor",
                position: floor.center,
                extent: floor.extent,
                kind: "plane",
                strength: floor.isEstimated ? 1 : 2,
                verified: true,
                positionConfidence: floor.isEstimated ? "low" : "high"
            ))
        }
        for surface in surfaces {
            next.append(SpatialWord(
                id: surface.id,
                label: planeWordLabel(surface),
                position: surface.center,
                extent: surface.extent,
                kind: "plane",
                strength: surface.isEstimated ? 1 : 2,
                verified: true,
                positionConfidence: surface.isEstimated ? "low" : "high"
            ))
        }
        for vertical in verticals.filter({ ["door", "window", "wall"].contains($0.classification) }).prefix(8) {
            next.append(SpatialWord(
                id: vertical.id,
                label: planeWordLabel(vertical),
                position: vertical.center,
                extent: vertical.extent,
                kind: "plane",
                strength: 2,
                verified: true,
                positionConfidence: "high"
            ))
        }
        for object in objects.sorted(by: { $0.sightings > $1.sightings }) {
            next.append(SpatialWord(
                id: object.id,
                label: objectWordLabel(object.label),
                position: object.position,
                extent: object.extent,
                kind: "object",
                strength: object.sightings,
                verified: object.verified,
                relabeledFrom: object.relabeledFrom,
                supportPlaneID: object.supportPlaneID,
                footprint: object.footprint,
                heightM: object.heightM,
                positionSpread: object.positionSpread,
                positionConfidence: object.positionConfidence
            ))
        }
        words = next
    }

    private func postSpatialSnapshotIfNeeded() {
        let now = Date()
        let publishWords = words
        guard !publishWords.isEmpty else { return }
        let signature = publishWords
            .map { word in
                let w = round(word.extent.x * 10) / 10
                let h = round(word.extent.y * 10) / 10
                let support = word.supportPlaneID?.uuidString ?? ""
                let fp = word.footprint.count
                let height = round(word.heightM * 10) / 10
                return "\(word.label):\(round(word.position.x * 10) / 10):\(round(word.position.z * 10) / 10):\(w):\(h):\(height):\(fp):\(support):\(word.verified)"
            }
            .sorted()
            .joined(separator: "|")
        guard signature != lastPostedSignature || now.timeIntervalSince(lastPostAt) >= 8 else { return }

        let lines = publishWords.map { word in
            let source = word.kind == "object" && word.verified ? "fastvlm verified spatial object" : "mobileclip spatial \(word.kind)"
            return "OBJECT | \(word.label) | \(source) | spatial word map | likely"
        }
        // NaN/inf in any coordinate makes the whole payload fail
        // JSONSerialization silently — estimated planes can produce them.
        func finite(_ v: Float) -> Double {
            v.isFinite ? Double(round(v * 100) / 100) : 0
        }
        let spatialWords = publishWords.map { word -> [String: Any] in
            [
                "label": word.label,
                "kind": word.kind,
                "x": finite(word.position.x),
                "y": finite(word.position.y),
                "z": finite(word.position.z),
                "w": finite(word.extent.x),
                "h": finite(word.extent.y),
                "strength": word.strength,
                "sightings": word.strength,
                "verified": word.kind != "object" || word.verified,
                "support_plane": word.supportPlaneID.map { $0.uuidString as Any } ?? NSNull(),
                "footprint": word.footprint,
                "heightM": finite(word.heightM),
                "relabeled_from": word.relabeledFrom,
                "position_spread": finite(word.positionSpread),
                "position_confidence": word.positionConfidence,
            ]
        }
        let payload: [String: Any] = [
            "timestamp": ISO8601DateFormatter().string(from: Date()),
            "source_type": "vision",
            "source": "mobileclip_spatial_word",
            "provider": "mobileclip_spatial_word",
            "scene_phase": "spatial_word_map",
            "confidence": 0.75,
            "stability_count": 2,
            "active_entity_labels": publishWords.map(\.label),
            "memory_text": lines.joined(separator: "\n"),
            "metadata": [
                "capture_mode": "spatial_word_map",
                "spatial_words": spatialWords,
                "tracking_state": trackingState,
                "word_source": "mobileclip_plus_fastvlm",
                "scanner_output": String(lastScannerOutput.prefix(700)),
                "build": BuildStamp.sha,
                "verified_words": publishWords.filter { $0.kind != "object" || $0.verified }.count,
                "hypothesis_words": publishWords.filter { $0.kind == "object" && !$0.verified }.count,
            ],
        ]
        guard JSONSerialization.isValidJSONObject(payload),
              let body = try? JSONSerialization.data(withJSONObject: payload) else {
            appendSpatialDiagnostic(
                word: "__post__", score: 0, elapsedMilliseconds: 0,
                position: nil, decision: "post_failed",
                extra: ["reason": "invalid_json_payload", "words": publishWords.count]
            )
            return
        }
        let baseURL = hubURL.isEmpty ? "http://127.0.0.1:8765" : hubURL
        guard let url = URL(string: "\(baseURL)/capture/perception") else {
            if Self.appendPerceptionSpool(body) {
                recordSpatialPostOutcome(signature: signature, postedAt: now, spooled: true)
            } else {
                appendSpatialDiagnostic(
                    word: "__post__", score: 0, elapsedMilliseconds: 0,
                    position: nil, decision: "post_failed",
                    extra: ["reason": "bad_url_and_spool_failed", "hub": baseURL]
                )
            }
            return
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("dev-token", forHTTPHeaderField: "X-SOMA-Token")
        request.httpBody = body
        URLSession.shared.dataTask(with: request) { _, response, error in
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            if error == nil, (200..<300).contains(status) {
                Task { @MainActor in
                    self.recordSpatialPostOutcome(signature: signature, postedAt: now, spooled: false)
                }
                return
            }
            let didSpool = Self.appendPerceptionSpool(body)
            Task { @MainActor in
                if didSpool {
                    self.recordSpatialPostOutcome(signature: signature, postedAt: now, spooled: true)
                } else {
                    self.appendSpatialDiagnostic(
                        word: "__post__", score: 0, elapsedMilliseconds: 0,
                        position: nil, decision: "post_failed",
                        extra: [
                            "reason": "http_\(status)_and_spool_failed",
                            "error": error.map { String(describing: $0) } ?? "none",
                        ]
                    )
                }
            }
        }.resume()
    }

    private func planeWordLabel(_ plane: SpatialPlane) -> String {
        switch plane.classification {
        case "table":
            return "table/desk"
        case "floor?":
            return "floor"
        case "surface":
            return "surface"
        case "vertical surface":
            return "wall"
        default:
            return plane.classification
        }
    }

    private func objectWordLabel(_ label: String) -> String {
        switch label.lowercased() {
        case "cpu tower":
            return "cpu"
        case "desk/table":
            return "desk"
        case "dining table":
            return "table/desk"
        case "tv":
            return "monitor/tv"
        case "cell phone":
            return "phone"
        case "water bottle":
            return "bottle"
        case "scale ruler":
            return "scale"
        default:
            return label
        }
    }
}

private enum SpatialWordScanner {
    private struct Region {
        let roi: CGRect
        let point: CGPoint
        let polygon: [CGPoint]
        let confidence: Float
        let source: String
    }

    private static let defaultProposalCap = 40
    private static let scanTimeBudgetMilliseconds = 600
    private static let minMaskArea: CGFloat = 0.015
    private static let maxMaskArea: CGFloat = 0.70
    private static let proposalDedupeIoU: CGFloat = 0.82
    private static let acceptedDedupeIoU: CGFloat = 0.55

    static func scan(pixelBuffer: CVImageBuffer, proposalCap: Int = defaultProposalCap) async -> SpatialWordScanResult {
        await withCheckedContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                continuation.resume(returning: scanSync(pixelBuffer: pixelBuffer, proposalCap: proposalCap))
            }
        }
    }

    private static func scanSync(pixelBuffer: CVImageBuffer, proposalCap: Int) -> SpatialWordScanResult {
        let started = Date()
        let namer = MobileCLIPNamer.shared
        guard namer.isAvailable else {
            return SpatialWordScanResult(
                labels: [],
                debug: namer.status,
                elapsedMilliseconds: elapsedMilliseconds(since: started),
                proposalCap: proposalCap
            )
        }

        let saliency = saliencyRegions(pixelBuffer: pixelBuffer)
        let dense = densePyramidRegions()
        let regions = dedupeRegions(saliency + dense, maxCount: max(1, proposalCap))
        var labels: [SpatialLabelCandidate] = []
        var debugParts: [String] = []
        var namerMilliseconds: [Int] = []
        var accepted: [(word: String, roi: CGRect)] = []

        let classifyStarted = Date()
        let predictions = namer.classify(frame: pixelBuffer, regionOfInterests: regions.map(\.roi))
        namerMilliseconds.append(max(1, elapsedMilliseconds(since: classifyStarted)))

        for (region, prediction) in zip(regions, predictions) {
            guard let prediction else {
                if debugParts.count < 16 {
                    debugParts.append("\(region.source) \(rectDebug(region.roi)): no embedding")
                }
                continue
            }
            guard prediction.accepted else {
                appendVocabMiss(prediction)
                if debugParts.count < 16 {
                    debugParts.append(
                        "\(region.source) \(rectDebug(region.roi)): best \(prediction.word) \(String(format: "%.2f", prediction.score)) Δ\(String(format: "%.2f", prediction.margin))"
                    )
                }
                continue
            }
            let key = prediction.word.lowercased()
            guard !accepted.contains(where: { $0.word == key && intersectionOverUnion($0.roi, region.roi) > acceptedDedupeIoU }) else {
                if debugParts.count < 16 {
                    debugParts.append("\(prediction.word) overlap duplicate @ \(rectDebug(region.roi))")
                }
                continue
            }
            accepted.append((word: key, roi: region.roi))
            labels.append(SpatialLabelCandidate(
                label: prediction.word,
                point: region.point,
                roi: region.roi,
                maskPolygon: region.polygon,
                score: prediction.score,
                margin: prediction.margin
            ))
            if debugParts.count < 16 {
                debugParts.append(
                    "\(prediction.word) \(String(format: "%.2f", prediction.score)) Δ\(String(format: "%.2f", prediction.margin)) @ \(region.source) \(rectDebug(region.roi))"
                )
            }
            if labels.count >= proposalCap { break }
        }
        if elapsedMilliseconds(since: started) > scanTimeBudgetMilliseconds {
            debugParts.append("budget \(scanTimeBudgetMilliseconds)ms exceeded")
        }

        let elapsed = elapsedMilliseconds(since: started)
        return SpatialWordScanResult(
            labels: labels,
            debug: debugParts.isEmpty
                ? "MobileCLIP no confident words from \(regions.count) regions in \(elapsed)ms"
                : "MobileCLIP dense fallback \(saliency.count)s+\(dense.count)d/\(regions.count) proposals in \(elapsed)ms: \(debugParts.joined(separator: " | "))",
            elapsedMilliseconds: elapsed,
            namerMilliseconds: namerMilliseconds,
            proposalsConsidered: regions.count,
            proposalCap: proposalCap
        )
    }

    private static func saliencyRegions(pixelBuffer: CVImageBuffer) -> [Region] {
        let request = VNGenerateObjectnessBasedSaliencyImageRequest()
        request.preferBackgroundProcessing = false
        let handler = VNImageRequestHandler(
            cvPixelBuffer: pixelBuffer,
            orientation: .right,
            options: [:]
        )
        do {
            try handler.perform([request])
        } catch {
            return []
        }

        let objects = request.results?.first?.salientObjects ?? []
        let regions = objects
            .map { observation -> Region in
                let roi = expanded(observation.boundingBox)
                return Region(
                    roi: roi,
                    point: point(forVisionRect: roi),
                    polygon: polygon(forVisionRect: roi),
                    confidence: observation.confidence,
                    source: "saliency"
                )
            }
            .filter { acceptsMaskArea($0.roi) }
            .sorted {
                let lhsScore = CGFloat($0.confidence) * $0.roi.width * $0.roi.height
                let rhsScore = CGFloat($1.confidence) * $1.roi.width * $1.roi.height
                return lhsScore > rhsScore
            }

        return regions
    }

    private static func densePyramidRegions() -> [Region] {
        var regions: [Region] = []
        for grid in [5, 7] {
            for scale in [CGFloat(1.0), CGFloat(1.6)] {
                for row in 0..<grid {
                    for col in 0..<grid {
                        let cell = CGFloat(1) / CGFloat(grid)
                        let size = min(CGFloat(1), cell * scale)
                        let centerX = (CGFloat(col) + 0.5) * cell
                        let centerY = (CGFloat(row) + 0.5) * cell
                        let roi = CGRect(
                            x: min(max(0, centerX - size / 2), 1 - size),
                            y: min(max(0, centerY - size / 2), 1 - size),
                            width: size,
                            height: size
                        )
                        appendDenseRegion(roi, source: "grid\(grid)x\(grid)-\(String(format: "%.1f", Double(scale)))", into: &regions)
                    }
                }
            }
        }
        return regions
    }

    private static func appendDenseRegion(
        _ roi: CGRect,
        source: String,
        into regions: inout [Region]
    ) {
        let rect = expanded(roi, scale: 1.02)
        guard acceptsMaskArea(rect) else { return }
        regions.append(Region(
            roi: rect,
            point: point(forVisionRect: rect),
            polygon: polygon(forVisionRect: rect),
            confidence: 0,
            source: source
        ))
    }

    private static func dedupeRegions(_ input: [Region], maxCount: Int) -> [Region] {
        var kept: [Region] = []
        let sorted = input.sorted { lhs, rhs in
            if lhs.source == "saliency", rhs.source != "saliency" { return true }
            if rhs.source == "saliency", lhs.source != "saliency" { return false }
            let lhsArea = lhs.roi.width * lhs.roi.height
            let rhsArea = rhs.roi.width * rhs.roi.height
            if lhsArea != rhsArea { return lhsArea > rhsArea }
            return lhs.confidence > rhs.confidence
        }
        for region in sorted {
            guard kept.allSatisfy({ intersectionOverUnion(region.roi, $0.roi) <= proposalDedupeIoU }) else {
                continue
            }
            kept.append(region)
            if kept.count >= maxCount { break }
        }
        return kept
    }

    private static func acceptsMaskArea(_ rect: CGRect) -> Bool {
        let area = rect.width * rect.height
        return area >= minMaskArea && area <= maxMaskArea
    }

    private static func intersectionOverUnion(_ lhs: CGRect, _ rhs: CGRect) -> CGFloat {
        let intersection = lhs.intersection(rhs)
        guard !intersection.isNull else { return 0 }
        let intersectionArea = max(0, intersection.width) * max(0, intersection.height)
        let unionArea = lhs.width * lhs.height + rhs.width * rhs.height - intersectionArea
        guard unionArea > 0 else { return 0 }
        return intersectionArea / unionArea
    }

    private static var vocabMissesURL: URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        let dir = base.appendingPathComponent("SOMA", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent("vocab_misses.ndjson")
    }

    private static func appendVocabMiss(_ prediction: MobileCLIPPrediction) {
        let payload: [String: Any] = [
            "ts": ISO8601DateFormatter().string(from: Date()),
            "best_word": prediction.word,
            "score": Double(round(prediction.score * 1000) / 1000),
            "margin": Double(round(prediction.margin * 1000) / 1000),
        ]
        guard JSONSerialization.isValidJSONObject(payload),
              let data = try? JSONSerialization.data(withJSONObject: payload) else {
            return
        }
        var line = data
        line.append(0x0A)
        let url = vocabMissesURL
        if !FileManager.default.fileExists(atPath: url.path) {
            FileManager.default.createFile(atPath: url.path, contents: nil)
        }
        guard let handle = try? FileHandle(forWritingTo: url) else { return }
        do {
            try handle.seekToEnd()
            try handle.write(contentsOf: line)
            try handle.close()
        } catch {
            try? handle.close()
        }
    }

    private static func expanded(_ rect: CGRect, scale: CGFloat = 1.18) -> CGRect {
        let width = min(1, rect.width * scale)
        let height = min(1, rect.height * scale)
        let x = min(max(0, rect.midX - width / 2), 1 - width)
        let y = min(max(0, rect.midY - height / 2), 1 - height)
        return CGRect(x: x, y: y, width: width, height: height)
    }

    private static func point(forVisionRect rect: CGRect) -> CGPoint {
        CGPoint(x: rect.midX, y: 1 - rect.midY)
    }

    private static func polygon(forVisionRect rect: CGRect) -> [CGPoint] {
        [
            CGPoint(x: rect.minX, y: 1 - rect.minY),
            CGPoint(x: rect.maxX, y: 1 - rect.minY),
            CGPoint(x: rect.maxX, y: 1 - rect.maxY),
            CGPoint(x: rect.minX, y: 1 - rect.maxY),
        ]
    }

    private static func elapsedMilliseconds(since started: Date) -> Int {
        Int(Date().timeIntervalSince(started) * 1000)
    }

    private static func rectDebug(_ rect: CGRect) -> String {
        String(format: "%.2f,%.2f %.2fx%.2f", rect.minX, rect.minY, rect.width, rect.height)
    }
}

private func canonicalSpatialWord(_ raw: String, confidence: Float) -> String? {
    let text = raw
        .lowercased()
        .replacingOccurrences(of: #"[^a-z0-9 /\-]+"#, with: " ", options: .regularExpression)
        .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
        .trimmingCharacters(in: .whitespacesAndNewlines)
    guard text.count >= 2 else { return nil }

    let phraseMappings: [(String, String)] = [
        ("computer keyboard", "keyboard"),
        ("keyboard", "keyboard"),
        ("computer mouse", "mouse"),
        ("mouse", "mouse"),
        ("electric fan", "fan"),
        ("fan", "fan"),
        ("desktop computer", "cpu/tower"),
        ("computer tower", "cpu/tower"),
        ("tower", "cpu/tower"),
        ("central processing unit", "cpu/tower"),
        ("laptop", "laptop"),
        ("notebook computer", "laptop"),
        ("monitor", "monitor"),
        ("screen", "monitor"),
        ("display", "monitor"),
        ("television", "monitor/tv"),
        ("headphone", "headphones"),
        ("headset", "headphones"),
        ("earphone", "headphones"),
        ("speaker", "speaker"),
        ("microphone", "microphone"),
        ("desk", "desk/table"),
        ("table", "desk/table"),
        ("chair", "chair"),
        ("bottle", "bottle"),
        ("cup", "cup"),
        ("mug", "cup"),
        ("phone", "phone"),
        ("cell phone", "phone"),
        ("scale", "scale"),
        ("weighing machine", "scale"),
        ("book", "book"),
        ("notebook", "book"),
        ("remote", "remote"),
        ("cable", "cable"),
        ("cord", "cable"),
        ("wire", "cable"),
    ]
    for (needle, word) in phraseMappings where text.contains(needle) {
        return word
    }

    let blockedNeedles = [
        "indoor", "room", "office", "furniture", "technology", "equipment",
        "device", "machine", "appliance", "instrument", "object", "thing",
        "image", "photo", "picture", "scene", "view", "camera", "person",
        "people", "man", "woman", "hand", "finger", "floor", "wall",
        "surface", "ceiling", "light", "dark", "close up", "pattern",
    ]
    guard !blockedNeedles.contains(where: { text == $0 || text.contains($0) }) else {
        return nil
    }

    let words = text.split(separator: " ").map(String.init)
    guard confidence >= 0.34, words.count <= 3, text.count <= 28 else { return nil }
    return words.joined(separator: " ")
}

// Words FastVLM emits when echoing the prompt or describing nothing —
// never acceptable as an object label (the 'name' relabel incident,
// 2026-06-12: a 110-sighting object got relabeled to the literal word
// "name").
private let verificationMetaWords: Set<String> = [
    "name", "names", "word", "words", "answer", "answers", "label",
    "labels", "item", "items", "main", "solid", "unknown", "none",
    "nothing", "background", "gradient", "blank", "visible",
]

// Phrases that mean the crop itself was garbage (black frame, gradient)
// — extract nothing, let a fresh crop retry later. Deliberately broad:
// "background"/"gradient" anywhere rejects the whole output, because on
// 2026-06-12 prose about empty crops yielded relabels to "background
// itself" (1,417-sighting object) and "area". A missed verification is
// recoverable; a wrong relabel is founder-visible damage.
private let garbageCropTells: [String] = [
    "background", "no discernible", "abstract", "gradient", "grayscale",
    "solid black", "solid-colored", "completely dark", "blurry",
    "pixelated", "blank", "bright spot", "no objects", "empty",
]

private func firstRegexCapture(_ pattern: String, in text: String) -> String? {
    guard let regex = try? NSRegularExpression(pattern: pattern) else { return nil }
    let range = NSRange(text.startIndex..., in: text)
    guard let match = regex.firstMatch(in: text, range: range),
          match.numberOfRanges > 1,
          let captured = Range(match.range(at: 1), in: text) else { return nil }
    return String(text[captured])
}

private func acceptableVerifiedLabel(_ candidate: String) -> String? {
    let text = candidate
        .replacingOccurrences(of: #"[^a-z0-9 /\-]+"#, with: " ", options: .regularExpression)
        .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
        .trimmingCharacters(in: .whitespacesAndNewlines)
    let words = text.split(separator: " ").map(String.init)
    guard words.count >= 1, words.count <= 3, text.count >= 3 else { return nil }
    guard !words.allSatisfy({ verificationMetaWords.contains($0) }) else { return nil }
    guard let canon = canonicalSpatialWord(text, confidence: 0.55) else { return nil }
    guard !verificationMetaWords.contains(canon) else { return nil }
    return canon
}

private func cleanVerifiedSpatialLabel(_ raw: String) -> String? {
    let lowered = raw.lowercased()
    for tell in garbageCropTells where lowered.contains(tell) {
        return nil
    }

    // 1) Direct short answer on the first line (the prompt-obeying case).
    var firstLine = lowered.components(separatedBy: .newlines).first ?? lowered
    firstLine = firstLine
        .replacingOccurrences(of: #"^(answer:|object:|name:)\s*"#, with: "", options: .regularExpression)
        .replacingOccurrences(of: #"^(it is|it's|this is|that is)\s+(a|an|the)?\s*"#, with: "", options: .regularExpression)
        .trimmingCharacters(in: .whitespacesAndNewlines)
    if let comma = firstLine.components(separatedBy: ",").first {
        let direct = comma.trimmingCharacters(in: .whitespacesAndNewlines)
        if direct.split(separator: " ").count <= 3, let label = acceptableVerifiedLabel(direct) {
            return label
        }
    }

    // 2) FastVLM rambled (40/42 verifications on 2026-06-12 were prose
    // like "The main solid object in this image is the keyboard, which…").
    // Prose extraction additionally requires the label to be a known
    // MobileCLIP vocab word: open-vocabulary answers are only trusted
    // when FastVLM obeyed the words-only prompt (the direct path above).
    let prosePatterns = [
        #"main (?:solid )?object(?:[^.]{0,40})? is (?:the |a |an )?([a-z][a-z \-]{2,28}?)(?:[.,;]| which| that| with| in | on |$)"#,
        #"the answer is (?:simply )?(?:the |a |an )?([a-z][a-z \-]{2,28}?)(?:[.,;]|$)"#,
        #"close-up(?: view)? of (?:the |a |an )?([a-z][a-z \-]{2,28}?)(?:[.,;]| and| with| on |$)"#,
    ]
    for pattern in prosePatterns {
        if let captured = firstRegexCapture(pattern, in: lowered),
           let label = acceptableVerifiedLabel(captured),
           verifiedLabelIsInVocab(label, rawCapture: captured) {
            return label
        }
    }
    return nil
}

private func verificationOutputIsPhantomTell(_ raw: String) -> Bool {
    let lowered = raw.lowercased()
    let noObjectTells = garbageCropTells + [
        "cannot see",
        "can't see",
        "not visible",
        "no object",
        "nothing visible",
    ]
    return noObjectTells.contains { lowered.contains($0) }
}

private func verifiedLabelIsInVocab(_ label: String, rawCapture: String) -> Bool {
    let vocab = MobileCLIPNamer.shared.vocabWords
    if vocab.contains(label) { return true }
    return vocab.contains(rawCapture.trimmingCharacters(in: .whitespacesAndNewlines))
}

// MARK: - View

private struct ProjectedSpatialWord: Identifiable {
    let word: SpatialWord
    let point: CGPoint
    let depth: CGFloat
    let scale: CGFloat
    let estimatedBounds: CGRect

    var id: UUID { word.id }
}

private struct ProjectedSpatialCluster: Identifiable {
    let id: String
    var items: [ProjectedSpatialWord]
    var point: CGPoint
    var depth: CGFloat
    var estimatedBounds: CGRect
}

private struct ProjectedSpatialLayout {
    let singles: [ProjectedSpatialWord]
    let clusters: [ProjectedSpatialCluster]
}

struct SpatialWordMapView: View {
    let words: [SpatialWord]
    @State private var zoom: CGFloat = 1
    @State private var pan: CGSize = .zero
    @State private var orbitRadians: CGFloat = 0
    @State private var expandedClusters: Set<String> = []

    var body: some View {
        GeometryReader { proxy in
            let layout = projectedWords(in: proxy.size)
            ZStack {
                Canvas { context, size in
                    drawGrid(context: context, size: size)
                }
                SpatialMapGestureOverlay(
                    zoom: $zoom,
                    pan: $pan,
                    orbitRadians: $orbitRadians,
                    expandedClusters: $expandedClusters
                )
                Text("you")
                    .font(.caption2.monospaced())
                    .foregroundStyle(.secondary)
                    .position(project(simd_float3.zero, in: proxy.size).point)
                ForEach(layout.singles) { item in
                    wordLabel(item, at: item.point)
                }
                ForEach(layout.clusters) { cluster in
                    if expandedClusters.contains(cluster.id) {
                        ForEach(Array(cluster.items.enumerated()), id: \.element.id) { offset, item in
                            wordLabel(item, at: fanPoint(for: offset, count: cluster.items.count, around: cluster.point))
                        }
                    } else {
                        Button {
                            expandedClusters.insert(cluster.id)
                        } label: {
                            Text("\(cluster.items.count) words here")
                                .font(.caption.weight(.semibold).monospaced())
                                .foregroundStyle(.primary)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 5)
                                .background(.thinMaterial, in: Capsule())
                                .overlay {
                                    Capsule().stroke(Color.cyan.opacity(0.5), lineWidth: 1.2)
                                }
                        }
                        .buttonStyle(.plain)
                        .position(cluster.point)
                    }
                }
                if words.isEmpty {
                    Text("recorded words will appear here")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
                VStack {
                    Spacer()
                    HStack {
                        Text("\(words.count) words · \(layout.clusters.count) clusters · zoom \(String(format: "%.1fx", zoom))")
                            .font(.caption2.monospaced())
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 5)
                            .background(.thinMaterial, in: Capsule())
                        Spacer()
                    }
                }
                .padding(10)
            }
            .frame(width: proxy.size.width, height: proxy.size.height)
            .background(Color(uiColor: .systemBackground))
            .clipShape(RoundedRectangle(cornerRadius: 8))
        }
    }

    @ViewBuilder
    private func wordLabel(_ item: ProjectedSpatialWord, at point: CGPoint) -> some View {
        Group {
            if item.word.kind == "object" && !item.word.verified {
                Text(item.word.label)
                    .font(labelFont(for: item.word))
                    .italic()
            } else {
                Text(item.word.label)
                    .font(labelFont(for: item.word))
            }
        }
            .scaleEffect(item.scale)
            .foregroundStyle(labelColor(for: item.word))
            .padding(.horizontal, 6)
            .padding(.vertical, 3)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 6))
            .overlay {
                RoundedRectangle(cornerRadius: 6)
                    .stroke(
                        borderColor(for: item.word),
                        style: StrokeStyle(
                            lineWidth: item.word.kind == "object" && item.word.verified ? 1.7 : 1,
                            dash: item.word.kind == "object" && !item.word.verified ? [3, 3] : []
                        )
                    )
            }
            .opacity(opacity(for: item.word, depth: item.depth))
            .position(point)
    }

    private func labelFont(for word: SpatialWord) -> Font {
        let weight: Font.Weight = word.kind == "object" && word.verified ? .bold : .medium
        return Font.system(size: fontSize(for: word), weight: weight, design: .rounded)
    }

    private func labelColor(for word: SpatialWord) -> Color {
        if word.kind != "object" { return .secondary }
        return word.verified ? .primary : .secondary
    }

    private func borderColor(for word: SpatialWord) -> Color {
        if word.kind != "object" { return Color.secondary.opacity(0.25) }
        return word.verified ? Color.cyan.opacity(0.72) : Color.secondary.opacity(0.42)
    }

    private func fanPoint(for offset: Int, count: Int, around center: CGPoint) -> CGPoint {
        guard count > 1 else { return center }
        let angle = (CGFloat(offset) / CGFloat(count)) * CGFloat.pi * 2
        let radius = CGFloat(34 + min(42, count * 4))
        return CGPoint(x: center.x + cos(angle) * radius, y: center.y + sin(angle) * radius)
    }

    private func fontSize(for word: SpatialWord) -> CGFloat {
        guard word.kind == "object" else { return 14 }
        let extent = CGFloat(max(word.extent.x, word.extent.y))
        guard extent > 0 else { return 18 }
        return min(30, max(16, 16 + extent * 12))
    }

    private func drawGrid(context: GraphicsContext, size: CGSize) {
        let range = mapRange()
        let step: CGFloat = 0.5
        var grid = Path()
        var metric = -range
        while metric <= range {
            let left = projectGround(right: -range, forward: metric, in: size)
            let right = projectGround(right: range, forward: metric, in: size)
            grid.move(to: left)
            grid.addLine(to: right)

            let near = projectGround(right: metric, forward: -range, in: size)
            let far = projectGround(right: metric, forward: range, in: size)
            grid.move(to: near)
            grid.addLine(to: far)
            metric += step
        }
        context.stroke(grid, with: .color(.secondary.opacity(0.08)), lineWidth: 1)

        var axes = Path()
        axes.move(to: projectGround(right: -range, forward: 0, in: size))
        axes.addLine(to: projectGround(right: range, forward: 0, in: size))
        axes.move(to: projectGround(right: 0, forward: -range, in: size))
        axes.addLine(to: projectGround(right: 0, forward: range, in: size))
        axes.move(to: project(simd_float3.zero, in: size).point)
        axes.addLine(to: project(simd_float3(0, 1, 0), in: size).point)
        context.stroke(axes, with: .color(.secondary.opacity(0.22)), lineWidth: 1.2)

        let origin = project(simd_float3.zero, in: size).point
        context.fill(Path(ellipseIn: CGRect(x: origin.x - 4, y: origin.y - 4, width: 8, height: 8)), with: .color(.cyan.opacity(0.8)))
    }

    private func projectedWords(in size: CGSize) -> ProjectedSpatialLayout {
        let candidates = words.map { word -> ProjectedSpatialWord in
            let projected = project(word.position, in: size)
            let labelSize = estimatedLabelSize(for: word, scale: projected.scale)
            let bounds = CGRect(
                x: projected.point.x - labelSize.width / 2,
                y: projected.point.y - labelSize.height / 2,
                width: labelSize.width,
                height: labelSize.height
            )
            return ProjectedSpatialWord(
                word: word,
                point: projected.point,
                depth: projected.depth,
                scale: projected.scale,
                estimatedBounds: bounds
            )
        }

        var clusters: [ProjectedSpatialCluster] = []
        for candidate in candidates.sorted(by: { priority(for: $0) > priority(for: $1) }) {
            let expanded = candidate.estimatedBounds.insetBy(dx: -7, dy: -5)
            if let idx = clusters.firstIndex(where: { $0.estimatedBounds.insetBy(dx: -7, dy: -5).intersects(expanded) }) {
                clusters[idx] = makeCluster(items: clusters[idx].items + [candidate])
            } else {
                clusters.append(makeCluster(items: [candidate]))
            }
        }

        let singles = clusters
            .filter { $0.items.count == 1 }
            .compactMap { $0.items.first }
            .sorted { $0.depth > $1.depth }
        let grouped = clusters
            .filter { $0.items.count > 1 }
            .sorted { $0.depth > $1.depth }
        return ProjectedSpatialLayout(singles: singles, clusters: grouped)
    }

    private func makeCluster(items: [ProjectedSpatialWord]) -> ProjectedSpatialCluster {
        let bounds = items.dropFirst().reduce(items[0].estimatedBounds) { partial, item in
            partial.union(item.estimatedBounds)
        }
        let id = items.map { $0.id.uuidString }.sorted().joined(separator: ".")
        let depth = items.map(\.depth).reduce(0, +) / CGFloat(max(1, items.count))
        return ProjectedSpatialCluster(
            id: id,
            items: items.sorted { priority(for: $0) > priority(for: $1) },
            point: CGPoint(x: bounds.midX, y: bounds.midY),
            depth: depth,
            estimatedBounds: bounds
        )
    }

    private func opacity(for word: SpatialWord, depth: CGFloat) -> Double {
        let base = word.kind == "object" && !word.verified ? 0.52 : (word.strength >= 3 ? 1.0 : 0.72)
        let depthFade = max(0.58, min(1.0, 1.06 - abs(depth) * 0.05))
        return base * depthFade
    }

    private func mapOrigin(in size: CGSize) -> CGPoint {
        CGPoint(x: size.width / 2 + pan.width, y: size.height * 0.66 + pan.height)
    }

    private func mapRange() -> CGFloat {
        max(
            1.2,
            CGFloat(words.map { max(abs($0.position.x), abs($0.position.y), abs($0.position.z)) }.max() ?? 1.2)
        )
    }

    private func mapScale(in size: CGSize) -> CGFloat {
        min(size.width, size.height) * 0.4 * zoom / mapRange()
    }

    private func projectGround(right: CGFloat, forward: CGFloat, in size: CGSize) -> CGPoint {
        project(simd_float3(Float(right), 0, Float(-forward)), in: size).point
    }

    private func project(_ position: simd_float3, in size: CGSize) -> (point: CGPoint, depth: CGFloat, scale: CGFloat) {
        let origin = mapOrigin(in: size)
        let scale = mapScale(in: size)
        let rawRight = CGFloat(position.x)
        let rawZ = CGFloat(position.z)
        let right = rawRight * cos(orbitRadians) - rawZ * sin(orbitRadians)
        let forward = -(rawRight * sin(orbitRadians) + rawZ * cos(orbitRadians))
        let up = CGFloat(position.y)
        let labelScale = max(0.86, min(1.08, 1.0 - forward * 0.03))
        let point = CGPoint(
            x: origin.x + (right - forward * 0.34) * scale,
            y: origin.y + (-forward * 0.72 - up * 1.02) * scale
        )
        return (point: point, depth: forward, scale: labelScale)
    }

    private func estimatedLabelSize(for word: SpatialWord, scale: CGFloat) -> CGSize {
        let font = fontSize(for: word) * scale
        let width = min(220, max(56, CGFloat(word.label.count) * font * 0.58 + 18))
        let height = max(30, font * 1.55)
        return CGSize(width: width, height: height)
    }

    private func priority(for item: ProjectedSpatialWord) -> CGFloat {
        let kindWeight: CGFloat = item.word.kind == "object" ? 10_000 : 2_000
        let strengthWeight = CGFloat(min(item.word.strength, 12)) * 140
        let extentWeight = CGFloat(max(item.word.extent.x, item.word.extent.y)) * 260
        let distancePenalty = abs(item.depth) * 22
        return kindWeight + strengthWeight + extentWeight - distancePenalty
    }
}

private struct SpatialMapGestureOverlay: UIViewRepresentable {
    @Binding var zoom: CGFloat
    @Binding var pan: CGSize
    @Binding var orbitRadians: CGFloat
    @Binding var expandedClusters: Set<String>

    func makeUIView(context: Context) -> UIView {
        let view = UIView()
        view.backgroundColor = .clear
        view.isMultipleTouchEnabled = true

        let orbit = UIPanGestureRecognizer(target: context.coordinator, action: #selector(Coordinator.handleOrbit(_:)))
        orbit.minimumNumberOfTouches = 1
        orbit.maximumNumberOfTouches = 1
        orbit.delegate = context.coordinator

        let twoFingerPan = UIPanGestureRecognizer(target: context.coordinator, action: #selector(Coordinator.handlePan(_:)))
        twoFingerPan.minimumNumberOfTouches = 2
        twoFingerPan.maximumNumberOfTouches = 2
        twoFingerPan.delegate = context.coordinator

        let pinch = UIPinchGestureRecognizer(target: context.coordinator, action: #selector(Coordinator.handlePinch(_:)))
        pinch.delegate = context.coordinator

        let doubleTap = UITapGestureRecognizer(target: context.coordinator, action: #selector(Coordinator.handleDoubleTap(_:)))
        doubleTap.numberOfTapsRequired = 2

        view.addGestureRecognizer(orbit)
        view.addGestureRecognizer(twoFingerPan)
        view.addGestureRecognizer(pinch)
        view.addGestureRecognizer(doubleTap)
        return view
    }

    func updateUIView(_ uiView: UIView, context: Context) {}

    func makeCoordinator() -> Coordinator {
        Coordinator(zoom: $zoom, pan: $pan, orbitRadians: $orbitRadians, expandedClusters: $expandedClusters)
    }

    final class Coordinator: NSObject, UIGestureRecognizerDelegate {
        @Binding var zoom: CGFloat
        @Binding var pan: CGSize
        @Binding var orbitRadians: CGFloat
        @Binding var expandedClusters: Set<String>

        init(
            zoom: Binding<CGFloat>,
            pan: Binding<CGSize>,
            orbitRadians: Binding<CGFloat>,
            expandedClusters: Binding<Set<String>>
        ) {
            _zoom = zoom
            _pan = pan
            _orbitRadians = orbitRadians
            _expandedClusters = expandedClusters
        }

        @objc func handleOrbit(_ recognizer: UIPanGestureRecognizer) {
            let translation = recognizer.translation(in: recognizer.view)
            orbitRadians += translation.x * 0.006
            recognizer.setTranslation(.zero, in: recognizer.view)
        }

        @objc func handlePan(_ recognizer: UIPanGestureRecognizer) {
            let translation = recognizer.translation(in: recognizer.view)
            pan.width += translation.x
            pan.height += translation.y
            recognizer.setTranslation(.zero, in: recognizer.view)
        }

        @objc func handlePinch(_ recognizer: UIPinchGestureRecognizer) {
            zoom = min(4.0, max(0.35, zoom * recognizer.scale))
            recognizer.scale = 1
        }

        @objc func handleDoubleTap(_ recognizer: UITapGestureRecognizer) {
            zoom = 1
            pan = .zero
            orbitRadians = 0
            expandedClusters = []
        }

        func gestureRecognizer(_ gestureRecognizer: UIGestureRecognizer, shouldRecognizeSimultaneouslyWith otherGestureRecognizer: UIGestureRecognizer) -> Bool {
            true
        }
    }
}

struct SpatialWorldView: View {
    @StateObject private var engine = SpatialWorldEngine()
    @State private var verifierModel = FastVLMModel()
    @State private var showScannerDebug = false
    @Environment(\.dismiss) private var dismiss
    @Environment(\.scenePhase) private var scenePhase
    var hubURL: String = ""
    var onClose: () -> Void = {}

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("SPATIAL WORD MAP")
                        .font(.caption.weight(.bold)).tracking(2)
                    Text("words \(engine.words.count)")
                        .font(.subheadline.monospaced())
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button("Done") { onClose(); dismiss() }
                    .font(.headline)
            }

            VStack(alignment: .leading, spacing: 8) {
                Text(readableStatus(engine.namingStatus))
                    .font(.caption.monospaced())
                    .foregroundStyle(.secondary)
                    .lineSpacing(3)
                    .fixedSize(horizontal: false, vertical: true)

                Button(showScannerDebug ? "Hide Debug" : "Show Debug") {
                    showScannerDebug.toggle()
                }
                .font(.caption.weight(.semibold))
            }
            .padding(10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))

            SpatialWordMapView(words: engine.words)
                .frame(maxWidth: .infinity, maxHeight: .infinity)

            if showScannerDebug {
                VStack(alignment: .leading, spacing: 6) {
                    Text("MobileCLIP word scanner: concrete object nouns only, placed relative to the genesis frame.")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    if !engine.lastScannerOutput.isEmpty {
                        ScrollView {
                            Text("scanner: \(engine.lastScannerOutput)")
                                .font(.caption2.monospaced())
                                .foregroundStyle(.secondary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .frame(maxHeight: 120)
                    }
                }
            }
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(Color(uiColor: .systemBackground).ignoresSafeArea())
        .onAppear {
            engine.hubURL = hubURL
            engine.onFrameForNaming = { frame, proposalCap in
                Task {
                    await runNativeWordScan(frame, proposalCap: proposalCap)
                }
            }
            engine.onVerifyObjectName = { objectID, crop, _ in
                Task {
                    await verifyObjectName(objectID: objectID, crop: crop)
                }
            }
            engine.start()
        }
        .onDisappear {
            engine.onFrameForNaming = nil
            engine.onVerifyObjectName = nil
            engine.stop()
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .inactive || phase == .background {
                engine.saveBeforeSuspension(reason: "scene_\(phase)")
            }
        }
    }

    private func runNativeWordScan(_ frame: CVImageBuffer, proposalCap: Int) async {
        let result = await SpatialWordScanner.scan(pixelBuffer: frame, proposalCap: proposalCap)
        engine.finishWordScan(result)
    }

    private func verifyObjectName(objectID: UUID, crop: CIImage) async {
        let started = Date()
        let prompt = """
        One or two lowercase words: name the main solid object in this image.
        Answer with only the word or words. No sentence. No punctuation.
        """
        let userInput = UserInput(
            prompt: .text(prompt),
            images: [.ciImage(crop)]
        )
        verifierModel.output = ""
        let task = await verifierModel.generate(userInput)
        _ = await task.result
        let elapsed = Int(Date().timeIntervalSince(started) * 1000)
        let raw = verifierModel.output
        if raw.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            engine.failVerification(objectID: objectID, message: "empty_fastvlm_output")
        } else {
            engine.finishVerification(objectID: objectID, rawOutput: raw, elapsedMilliseconds: elapsed)
        }
    }

    private func readableStatus(_ value: String) -> String {
        value.replacingOccurrences(of: " · ", with: "\n")
    }
}
#else
struct SpatialWorldView: View {
    var hubURL: String = ""
    var onClose: () -> Void = {}

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("SPATIAL — iPhone ARKit only")
                .font(.caption.weight(.bold)).tracking(2)
            Text("Genesis-frame spatial mode needs iPhone camera and motion tracking.")
                .foregroundStyle(.secondary)
            Button("Done") { onClose() }
        }
        .padding()
    }
}
#endif
