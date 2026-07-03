//
// For licensing see accompanying LICENSE file.
// Copyright (C) 2025 Apple Inc. All Rights Reserved.
//

import AVFoundation
import CoreImage
import Foundation
import MLXLMCommon
import SwiftUI
import Video
import Vision

// support swift 6
extension CVImageBuffer: @unchecked @retroactive Sendable {}
extension CMSampleBuffer: @unchecked @retroactive Sendable {}

// Continuous mode is FastVLM-FIRST: the VLM is the understanding channel that names
// real objects ("Nutella jar", "Pringles can"). The generic detectors (YOLO-COCO 80
// classes, VNClassifyImageRequest) only know coarse categories, so branded goods get
// forced into nonsense ("sports ball", "surfboard") that poisons memory — they are now
// OFF as memory writers. OCR + people detection stay (they carry real signal).
let VISION_FRAME_DELAY = Duration.milliseconds(180)  // REVAMP: was 650; cycle the capture loop ~5x faster for dense frame streaming
let ENABLE_STABLE_VLM_REFRESH = true
let ENABLE_TEXT_OCR_MEMORY = true
let ENABLE_OCR_STILL_PASS = false
let ENABLE_IMAGE_CLASSIFICATION_MEMORY = false
let ENABLE_DETECTOR_OBJECT_MEMORY = false  // YOLO-COCO labels (jars→"sports ball") poison memory; VLM is the object channel
// Step 1 track-anchor: emit ONE observation per tracked object carrying a stable track_id (the
// coordinate-free binder anchor). Separate `detector` helper channel — additive, does not touch the
// existing frame-level VLM/OCR posts. COCO-class labels only (bottle/cup/chair/laptop/person…).
let ENABLE_TRACK_ANCHOR_EMISSION = true
// KILL SWITCH (2026-07-02): per-track crop VLM enrichment (M5) runs a full model.generate on the
// SHARED VLM actor for every tracked object — it contends with the capture loop and can freeze
// the app on device. OFF for the demo; the app streams capture + answers via the hub without it.
let ENABLE_TRACK_CROP_ENRICHMENT = false
let ENABLE_LOCAL_DETECTOR_MEMORY = true
// L1 (ops/CANONICAL_SPEC.md v3): raw media never leaves the phone. Flip only for
// bench debugging with a dev hub; product builds ship false.
let DEBUG_FRAMES_BUILD_ALLOWED = false
let STABLE_VLM_REFRESH_SECONDS: TimeInterval = 4
let ENABLE_PERSON_VLM_ENRICHMENT = true
let PERSON_VLM_ENRICHMENT_COOLDOWN: TimeInterval = 30
let MEMORY_COMMIT_DEDUP_SECONDS: TimeInterval = 10
let CONTEXT_SNAPSHOT_SECONDS: TimeInterval = 8
let CONTEXT_DIGEST_SECONDS: TimeInterval = 20
let CONTEXT_ACTIVE_SECONDS: TimeInterval = 90
let CONTEXT_STALE_SECONDS: TimeInterval = 1_800

enum TraceDefaults {
    /// Default Mac brain hub address on the LAN. Prefilled so a first-time
    /// user can Ask without hand-typing an IP; still editable in Hub Setup.
    static let hubURL = "http://172.20.10.6:8765"
}

struct TraceContextFact: Identifiable {
    let id: String
    var text: String
    var firstSeen: Date
    var lastSeen: Date
    var observations: Int
    var source: String
}

struct TraceTextHit {
    let text: String
    let confidence: Float
    let box: CGRect
}

struct TraceTextRecognitionResult {
    let observations: [VNRecognizedTextObservation]
    let orientationsWithHits: [String]
}

struct TraceClassificationHit {
    let label: String
    let confidence: Float
}

struct TracePerceptionRecord {
    let memory: String
    let activeLabels: [String]
    let anchorLabel: String?
    let anchorBox: CGRect?
}

struct ContentView: View {
    // Spatial mode: ARKit owns the camera (world tracking + anchors). Default OFF
    // (proven AVCaptureSession path). Toggle in Hub Setup. iOS allows only one
    // camera session, so this picks which one runs.
    @AppStorage("spatialMode") private var spatialMode = false
    @State private var camera = CameraController()
    @ObservedObject private var arkitEngine = TraceARKitEngine.shared
    @State private var model = FastVLMModel()
    @StateObject private var audioContext = TraceAudioContextEngine()
    @StateObject private var locationContext = TraceLocationContextEngine()
    @StateObject private var detectorBridge = TraceDetectorBridge()

    /// stream of frames -> VideoFrameView, see distributeVideoFrames
    @State private var framesToDisplay: AsyncStream<CVImageBuffer>?

    @State private var prompt = """
        You are Trace's wearable first-person perception engine.
        Convert the current camera frame into durable text memory.
        Use only this ontology:
        OBJECT | visible entity or body/object attribute | concrete attributes | relation/location if visible | certainty
        EVENT | object/person involved | action/change/state | relation/location if visible | certainty
        """
    @State private var promptSuffix = """
        No prose captions. No categories outside OBJECT and EVENT. Output 2-6 lines only. If uncertain, say uncertain instead of guessing.
        """
    @State private var memoryRecords: [String] = []
    @State private var contextFacts: [String: TraceContextFact] = [:]
    @State private var recentMemorySignatures: [String: Date] = [:]
    @State private var visionStatus = "Native Vision waiting for camera frames"
    @State private var currentScenePhase = "settling"
    @State private var currentMotionScore: Double?
    @State private var lastContextSnapshotAt = Date.distantPast
    @State private var lastContextDigestAt = Date.distantPast
    @State private var lastContextDigestSignature = ""
    @State private var lastSemanticRefreshAt = Date.distantPast
    @State private var lastPersonEnrichmentAt = Date.distantPast
    // M5 per-track crop enrichment: each confirmed track gets ONE zoomed VLM pass (colour/
    // material/brand off the crop), throttled so the GPU-serial model is never contended.
    @State private var enrichedTrackKeys: Set<String> = []
    @State private var lastTrackEnrichmentAt = Date.distantPast
    @State private var trackEnrichmentRunning = false
    @State private var lastRawOcrCount = 0
    @State private var lastAcceptedOcrCount = 0
    @State private var lastObjectCount = 0
    @State private var lastFaceCount = 0
    @State private var lastOcrStillAt = Date.distantPast
    // L1 (ops/CANONICAL_SPEC.md v3): not one video frame leaves the phone — ever.
    // This debug path JPEG-encoded + POSTed every keyframe (up to 8/s) to a hub
    // endpoint that 404s it (pure waste, measured as capture lag 2026-07-03).
    // Default is OFF and stays OFF; the toggle survives for bench debugging only.
    @State private var lastDebugFrameAt = Date.distantPast
    @AppStorage("traceDebugFrames") private var debugFramesEnabled = false
    @AppStorage(GroundTruthRecorder.toggleKey) private var gtRecordingEnabled = false
    // Ask Trace — queries the Mac brain (over the LAN) about the LIVE perception stream.
    @State private var showAsk = false
    @State private var askText = ""
    @State private var askAnswer = ""
    @State private var askCitations: [String] = []
    @State private var askSource = ""
    @State private var askRefused = false
    @State private var isAsking = false
    @State private var askError = ""
    // Plain-words connection state to the Mac brain ("Brain connected" / not).
    @State private var brainReachable: Bool? = nil
    @State private var lastBodyCount = 0
    @State private var lastAcceptedOcrPreview = ""
    @State private var lastVisionInferenceAt: Date?
    @State private var lastVisionNoRecordAt: Date?
    @State private var isVideoRecording = VideoRecorder.shared.isRecording
    @State private var recordingStatusText = ""

    @State private var isShowingInfo: Bool = false
    @State private var isShowingHubSetup: Bool = false
    // Prefilled so a first-time user never has to type an IP. Still editable in Hub Setup.
    @AppStorage("traceHubURL") private var traceHubURL: String = TraceDefaults.hubURL
    @State private var isMemoryPaused = false
    // First-launch onboarding flag (shown once, then never again).
    @AppStorage("traceHasOnboarded") private var hasOnboarded: Bool = false

    @State private var selectedCameraType: CameraType = .continuous
    @State private var isEditingPrompt: Bool = false

    var toolbarItemPlacement: ToolbarItemPlacement {
        var placement: ToolbarItemPlacement = .navigation
        #if os(iOS)
        placement = .topBarLeading
        #endif
        return placement
    }
    
    var statusTextColor : Color {
        return model.evaluationState == .processingPrompt ? .black : .white
    }
    
    var statusBackgroundColor : Color {
        switch model.evaluationState {
        case .idle:
            return .gray
        case .generatingResponse:
            return .green
        case .processingPrompt:
            return .yellow
        }
    }

    var body: some View {
        NavigationStack {
            configuredLiveScreen
        }
    }

    @ViewBuilder private var liveScreenBase: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            if let framesToDisplay {
                VideoFrameView(
                    frames: framesToDisplay,
                    cameraType: .continuous,
                    action: { _ in }
                )
                .aspectRatio(4/3, contentMode: .fit)
                .frame(maxWidth: .infinity)
            } else {
                ProgressView()
                    .tint(.white)
            }

            VStack(spacing: 0) {
                liveHeader
                Spacer(minLength: 0)
                liveMemoryOverlay
                askBar
            }
            .padding(.horizontal, 12)

            if !model.modelInfo.isEmpty && model.modelInfo != "Loaded" {
                loadingStatusOverlay
            }
        }
    }

    private var configuredLiveScreen: some View {
        presentedLiveScreen
    }

    private var runtimeConfiguredLiveScreen: some View {
        liveScreenBase
            .task { await model.load() }
            .task { await startLiveRuntime() }
            .task { await monitorBrainStatus() }
            .task { await startFrameDistribution() }
    }

    private var observedLiveScreen: some View {
        runtimeConfiguredLiveScreen
            .onChange(of: detectorBridge.lastMemoryText) { _, memoryText in
                handleDetectorMemoryChange(memoryText)
            }
            .onChange(of: detectorBridge.status) { _, status in
                appendNativeStatusLog(status: "detector_status", extra: [
                    "detector_status": status,
                ])
            }
            .onChange(of: audioContext.lastCommittedTranscript) { _, transcript in
                handleAudioTranscriptChange(transcript)
            }
            .onChange(of: audioContext.status) { _, status in
                appendNativeStatusLog(status: "audio_status", extra: [
                    "audio_status": status,
                ])
            }
            .onChange(of: locationContext.status) { _, status in
                appendNativeStatusLog(status: "location_status", extra: [
                    "location_status": status,
                    "location_hint": locationContext.locationMemoryHint,
                ])
            }
            .onChange(of: locationContext.locationMemoryHint) { _, hint in
                appendNativeStatusLog(status: "location_hint_updated", extra: [
                    "location_hint": hint,
                ])
            }
            .onChange(of: traceHubURL) { _, url in
                VideoRecorder.shared.configure(hubURL: url)
            }
            #if !os(macOS)
            .onAppear {
                UIApplication.shared.isIdleTimerDisabled = true
                // One-shot, read-only depth-capability probe (no camera-session change).
                Task { @MainActor in
                    self.postPerceptionPacketToHub([
                        "memory_text": DepthProbe.report(),
                        "source": "depth_probe",
                        "metadata": ["kind": "depth_probe"],
                    ])
                }
            }
            .onDisappear {
                UIApplication.shared.isIdleTimerDisabled = false
            }
            #endif
    }

    private var presentedLiveScreen: some View {
        observedLiveScreen
            .navigationTitle("Trace")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button { isShowingInfo.toggle() } label: {
                        Image(systemName: "info.circle")
                    }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button { isShowingHubSetup.toggle() } label: {
                        Image(systemName: traceHubURL.isEmpty ? "wifi.exclamationmark" : "brain.head.profile")
                            .foregroundStyle(traceHubURL.isEmpty ? Color.orange : Color.green)
                    }
                }
            }
            .sheet(isPresented: $isShowingInfo) {
                InfoView()
            }
            .sheet(isPresented: $isShowingHubSetup) {
                TraceHubSetupView(hubURL: $traceHubURL)
            }
            .sheet(isPresented: $showAsk) {
                askSheet
            }
            .fullScreenCover(isPresented: .constant(!hasOnboarded)) {
                OnboardingView { hasOnboarded = true }
            }
    }

    @ViewBuilder private var loadingStatusOverlay: some View {
        VStack {
            HStack(spacing: 8) {
                ProgressView().tint(.white)
                Text(model.modelInfo)
                    .font(.caption.bold())
                    .foregroundStyle(.white)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .background(.black.opacity(0.75), in: Capsule())
            Spacer()
        }
        .padding(.top, 70)
    }


    // ── LEAN LIVE POV UI ─────────────────────────────────────────────────── //
    @State private var rawMediaCount: Int = 0

    /// Honest audit: count raw media anywhere in the app container. The badge
    /// reflects THIS live scan — never a hardcoded value. (P0 honesty sprint.)
    private func refreshRawMediaCount() {
        let fm = FileManager.default
        let exts: Set<String> = ["mov", "mp4", "m4v", "heic", "heif", "jpg", "jpeg", "png", "wav", "m4a", "aac", "caf"]
        var count = 0
        let roots: [URL?] = [fm.urls(for: .documentDirectory, in: .userDomainMask).first,
                             URL(fileURLWithPath: NSTemporaryDirectory())]
        for case let root? in roots {
            guard let en = fm.enumerator(at: root, includingPropertiesForKeys: nil) else { continue }
            for case let u as URL in en where exts.contains(u.pathExtension.lowercased()) { count += 1 }
        }
        rawMediaCount = count
    }

    @ViewBuilder var liveHeader: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(spacing: 8) {
                Circle().fill(statusBackgroundColor).frame(width: 9, height: 9)
                Text("Watching")
                    .font(.caption.bold())
                Spacer()
                Button(action: toggleVideoRecording) {
                    HStack(spacing: 6) {
                        Image(systemName: isVideoRecording ? "stop.fill" : "record.circle.fill")
                            .font(.caption.bold())
                        Text(isVideoRecording ? "Stop" : "Record")
                            .font(.caption.bold())
                    }
                    .foregroundStyle(.white)
                    .padding(.vertical, 6)
                    .padding(.horizontal, 10)
                    .background(isVideoRecording ? Color.red : Color.white.opacity(0.18), in: Capsule())
                }
                .buttonStyle(.plain)
                Image(systemName: "sparkles")
                    .font(.caption2)
                Text(memoryRecords.count == 1 ? "1 memory" : "\(memoryRecords.count) memories")
                    .font(.caption.bold())
            }

            if !recordingStatusText.isEmpty {
                Text(recordingStatusText)
                    .font(.caption2)
                    .foregroundStyle(isVideoRecording ? Color.red.opacity(0.95) : Color.white.opacity(0.72))
                    .lineLimit(2)
            }

            // VISIBLE ARKit status — was previously invisible, so two real recordings got stuck
            // in "Limited: relocalizing" with no on-screen sign of it. Watch for this to say
            // "Normal" (green) before recording; tap Reset if it stays Limited/idle.
            if spatialMode {
                HStack(spacing: 6) {
                    Circle()
                        .fill(arkitEngine.trackingStatus == "Tracking" ? Color.green : Color.orange)
                        .frame(width: 7, height: 7)
                    Text("ARKit: \(arkitEngine.trackingStatus)")
                        .font(.caption2)
                        .foregroundStyle(.white.opacity(0.85))
                    Button {
                        arkitEngine.forceFreshStart()
                    } label: {
                        Text("Reset")
                            .font(.caption2.bold())
                            .foregroundStyle(.white)
                            .padding(.horizontal, 6).padding(.vertical, 2)
                            .background(.white.opacity(0.18), in: Capsule())
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .foregroundStyle(.white)
        .padding(.vertical, 7).padding(.horizontal, 12)
        .background(.black.opacity(0.55), in: Capsule())
        .padding(.top, 6)
        .task {
            refreshRawMediaCount()
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 2_000_000_000)
                refreshRawMediaCount()
            }
        }
    }

    /// Plain-words connection state to the Mac brain, shown above the Ask button.
    @ViewBuilder var brainStatusPill: some View {
        let connected = brainReachable == true
        let unknown = brainReachable == nil
        HStack(spacing: 6) {
            Image(systemName: "brain.head.profile")
                .font(.caption2)
            Text(unknown ? "Checking brain…" : (connected ? "Brain connected" : "Brain not connected"))
                .font(.caption2.weight(.semibold))
        }
        .foregroundStyle(unknown ? .white.opacity(0.7) : (connected ? .green : .orange))
        .padding(.vertical, 5).padding(.horizontal, 10)
        .background(.black.opacity(0.5), in: Capsule())
    }

    @ViewBuilder var liveMemoryOverlay: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: "sparkles")
                    .font(.caption2)
                Text("Remembering")
                    .font(.caption.bold())
                Spacer()
                if !memoryRecords.isEmpty {
                    Text("live")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.green)
                }
            }
            .foregroundStyle(.white.opacity(0.85))

            if memoryRecords.isEmpty {
                Text("Point your camera at the world — signs, faces, objects and what's said turn into memory here.")
                    .font(.callout)
                    .foregroundStyle(.white.opacity(0.7))
                    .frame(maxWidth: .infinity, alignment: .leading)
            } else {
                let cards = memoryCards(from: memoryRecords, limit: 6)
                VStack(alignment: .leading, spacing: 7) {
                    ForEach(Array(cards.enumerated()), id: \.element.id) { index, card in
                        memoryCardRow(card)
                            // Newest on top is fully opaque; older entries fade gently.
                            .opacity(max(0.45, 1.0 - Double(index) * 0.11))
                    }
                }
                .animation(.easeOut(duration: 0.25), value: cards.map(\.id))
            }
        }
        .padding(12)
        .background(.black.opacity(0.55), in: RoundedRectangle(cornerRadius: 16))
    }

    @ViewBuilder func memoryCardRow(_ card: MemoryCard) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Text(card.icon)
                .font(.title3)
                .frame(width: 26, alignment: .center)
            VStack(alignment: .leading, spacing: 1) {
                Text(card.title)
                    .font(.callout.weight(.semibold))
                    .foregroundStyle(.white)
                    .lineLimit(2)
                if let detail = card.detail, !detail.isEmpty {
                    Text(detail)
                        .font(.caption)
                        .foregroundStyle(.white.opacity(0.7))
                        .lineLimit(1)
                }
            }
            Spacer(minLength: 0)
            Text(card.relativeTime)
                .font(.caption2)
                .foregroundStyle(.white.opacity(0.5))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder var askBar: some View {
        VStack(spacing: 8) {
            HStack {
                Spacer()
                brainStatusPill
            }
            Button { showAsk = true } label: {
                HStack(spacing: 10) {
                    Image(systemName: "sparkles")
                        .font(.title3)
                    VStack(alignment: .leading, spacing: 1) {
                        Text("Ask Trace")
                            .font(.headline)
                        Text("about anything you saw")
                            .font(.caption)
                            .foregroundStyle(.white.opacity(0.8))
                    }
                    Spacer()
                    Image(systemName: "chevron.up")
                        .font(.subheadline.bold())
                }
                .foregroundStyle(.white)
                .padding(.vertical, 14).padding(.horizontal, 18)
                .background(Color.accentColor, in: RoundedRectangle(cornerRadius: 16))
                .shadow(color: .black.opacity(0.3), radius: 8, y: 2)
            }
        }
        .padding(.vertical, 10)
    }

    @ViewBuilder var askSheet: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 14) {
                if traceHubURL.isEmpty {
                    Text("Set the brain address first (tap the brain icon in the toolbar) — e.g. http://<mac-ip>:8765")
                        .font(.footnote).foregroundStyle(.orange)
                }
                HStack {
                    TextField("Ask about what Trace saw…", text: $askText, axis: .vertical)
                        .textFieldStyle(.roundedBorder)
                        .onSubmit { performAsk() }
                    Button { performAsk() } label: {
                        Image(systemName: "arrow.up.circle.fill").font(.title2)
                    }.disabled(askText.trimmingCharacters(in: .whitespaces).isEmpty || isAsking)
                }
                HStack {
                    ForEach(["What did I see?", "Any people?", "What did the text say?"], id: \.self) { q in
                        Button(q) { askText = q; performAsk() }
                            .font(.caption).buttonStyle(.bordered)
                    }
                }
                if isAsking {
                    HStack { ProgressView(); Text("Trace is thinking… (the brain can take a while)").foregroundStyle(.secondary) }
                }
                if !askError.isEmpty {
                    Text(askError).font(.footnote).foregroundStyle(.red)
                }
                if !askAnswer.isEmpty {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 10) {
                            HStack(spacing: 6) {
                                Image(systemName: askRefused ? "checkmark.shield" : "checkmark.seal.fill")
                                    .foregroundStyle(askRefused ? .orange : .green)
                                Text(askRefused ? "Honest: not in memory" : "Answered")
                                    .font(.caption.bold())
                                if !askSource.isEmpty {
                                    Text("· \(askSource)").font(.caption2).foregroundStyle(.secondary)
                                }
                            }
                            Text(askAnswer).font(.body).textSelection(.enabled)
                            if !askCitations.isEmpty {
                                Text("from memory at: " + askCitations.joined(separator: ", "))
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
                Spacer()
            }
            .padding()
            .navigationTitle("Ask Trace")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Done") { showAsk = false } } }
        }
    }

    func cleanFeedLine(_ s: String) -> String {
        let parts = s.split(separator: "\n", maxSplits: 1)
        let body = parts.count > 1 ? String(parts[1]) : s
        return body
            .replacingOccurrences(of: " | likely", with: "")
            .replacingOccurrences(of: " | uncertain", with: "")
            .replacingOccurrences(of: "OBJECT | ", with: "")
            .replacingOccurrences(of: "EVENT | ", with: "")
    }

    /// A glanceable, human card built from a raw memory record. The raw
    /// pipe-delimited record (KIND | subject | attributes | relation | certainty)
    /// stays untouched in `memoryRecords`; this is purely the user-facing view.
    struct MemoryCard: Identifiable, Equatable {
        let id: String
        let icon: String
        let title: String
        let detail: String?
        let relativeTime: String
    }

    /// Turn the latest raw records into clean cards (newest first). One card per
    /// record; the first meaningful OBJECT/EVENT line in the record drives it.
    func memoryCards(from records: [String], limit: Int) -> [MemoryCard] {
        var cards: [MemoryCard] = []
        var seenTitles = Set<String>()
        for (offset, rec) in records.enumerated() {
            let parts = rec.split(separator: "\n", maxSplits: 1)
            let timeStamp = parts.count > 1 ? String(parts[0]) : ""
            let body = parts.count > 1 ? String(parts[1]) : rec
            guard let line = primaryMemoryLine(in: body),
                  let card = makeMemoryCard(line: line, timeStamp: timeStamp, index: offset) else {
                continue
            }
            // Avoid back-to-back duplicate-looking cards in the user view.
            let dedupKey = card.icon + card.title
            if seenTitles.contains(dedupKey) { continue }
            seenTitles.insert(dedupKey)
            cards.append(card)
            if cards.count >= limit { break }
        }
        return cards
    }

    /// Prefer the first OBJECT/EVENT line; fall back to the first non-empty line.
    private func primaryMemoryLine(in body: String) -> String? {
        let lines = body.components(separatedBy: .newlines)
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
        let typed = lines.first { $0.hasPrefix("OBJECT |") || $0.hasPrefix("EVENT |") }
        return typed ?? lines.first
    }

    private func makeMemoryCard(line: String, timeStamp: String, index: Int) -> MemoryCard? {
        let fields = line.components(separatedBy: "|").map { $0.trimmingCharacters(in: .whitespaces) }
        let kind = fields.first?.uppercased() ?? ""
        let subject = fields.count > 1 ? fields[1] : ""
        let attributes = fields.count > 2 ? fields[2] : ""
        let relation = fields.count > 3 ? fields[3] : ""
        let lowSubject = subject.lowercased()
        let lowAttr = attributes.lowercased()

        // Quoted text captured by OCR or speech, e.g. OCR text: "..." / transcript: "..."
        let quoted = firstQuoted(in: line)

        // 1) Speech / things said.
        if lowSubject.contains("speech") || lowAttr.contains("transcript") {
            let said = quoted ?? attributes
            return MemoryCard(id: "\(index)", icon: "🗣️",
                              title: said.isEmpty ? "Someone spoke nearby" : "Heard: “\(trimForCard(said))”",
                              detail: said.isEmpty ? nil : "spoken nearby",
                              relativeTime: relativeTimeLabel(from: timeStamp))
        }

        // 2) Text on signs / screens / surfaces.
        let textSurface = lowSubject.contains("sign") || lowSubject.contains("screen")
            || lowSubject.contains("text") || lowSubject.contains("display")
            || lowAttr.contains("ocr") || quoted != nil && (kind == "OBJECT")
        if textSurface, let read = quoted, !read.isEmpty {
            let label = signLabel(for: lowSubject)
            return MemoryCard(id: "\(index)", icon: signIcon(for: lowSubject),
                              title: "\(label): “\(trimForCard(read))”",
                              detail: nil,
                              relativeTime: relativeTimeLabel(from: timeStamp))
        }

        // 3) People.
        if lowSubject.contains("person") || lowSubject.contains("people") || lowSubject.contains("face") {
            let title: String
            if lowSubject.contains("people") {
                title = "A few people nearby"
            } else if lowSubject.contains("background") {
                title = "Another person nearby"
            } else {
                title = "A person nearby"
            }
            let detail = humanPhrase(attributes.isEmpty ? relation : attributes)
            return MemoryCard(id: "\(index)", icon: "🚶",
                              title: title,
                              detail: detail,
                              relativeTime: relativeTimeLabel(from: timeStamp))
        }

        // 4) Events (something happening).
        if kind == "EVENT" {
            let action = humanPhrase(attributes.isEmpty ? subject : "\(subject) \(attributes)")
            return MemoryCard(id: "\(index)", icon: "✨",
                              title: action.isEmpty ? "Something happening" : capitalizeFirst(action),
                              detail: nil,
                              relativeTime: relativeTimeLabel(from: timeStamp))
        }

        // 5) Generic objects.
        let name = humanPhrase(subject.replacingOccurrences(of: "visible ", with: ""))
        guard !name.isEmpty else { return nil }
        let detail = humanPhrase(attributes)
        return MemoryCard(id: "\(index)", icon: objectIcon(for: lowSubject + " " + lowAttr),
                          title: capitalizeFirst(name),
                          detail: detail == name ? nil : detail,
                          relativeTime: relativeTimeLabel(from: timeStamp))
    }

    /// Extract the first double-quoted span (the verbatim text Trace read/heard).
    private func firstQuoted(in line: String) -> String? {
        guard let start = line.firstIndex(of: "\"") else { return nil }
        let after = line.index(after: start)
        guard after < line.endIndex, let end = line[after...].firstIndex(of: "\"") else { return nil }
        let inner = String(line[after..<end]).trimmingCharacters(in: .whitespaces)
        return inner.isEmpty ? nil : inner
    }

    private func trimForCard(_ s: String, max: Int = 70) -> String {
        let collapsed = s.replacingOccurrences(of: "\n", with: " ")
            .trimmingCharacters(in: .whitespaces)
        if collapsed.count <= max { return collapsed }
        return String(collapsed.prefix(max)).trimmingCharacters(in: .whitespaces) + "…"
    }

    /// Strip the internal certainty / pipeline words so the user sees plain language.
    private func humanPhrase(_ s: String) -> String {
        var out = s
        for noise in ["detector stream", "visible frame", "detected while camera moving",
                      "high-resolution still pass", "provisional ", "full-res ", "OCR text:",
                      "provisional OCR text:", "; detected", " detected"] {
            out = out.replacingOccurrences(of: noise, with: "")
        }
        out = out.replacingOccurrences(of: "likely", with: "")
            .replacingOccurrences(of: "uncertain", with: "")
            .replacingOccurrences(of: "  ", with: " ")
        // Drop dangling separators left behind.
        out = out.trimmingCharacters(in: CharacterSet(charactersIn: " ;,|-"))
        return out
    }

    private func capitalizeFirst(_ s: String) -> String {
        guard let first = s.first else { return s }
        return first.uppercased() + s.dropFirst()
    }

    private func signLabel(for subject: String) -> String {
        if subject.contains("transit") { return "Sign" }
        if subject.contains("screen") || subject.contains("display") { return "Screen" }
        return "Sign"
    }

    private func signIcon(for subject: String) -> String {
        if subject.contains("screen") || subject.contains("display") { return "📱" }
        return "🪧"
    }

    private func objectIcon(for text: String) -> String {
        if text.contains("headphone") || text.contains("earphone") || text.contains("earbud") { return "🎧" }
        if text.contains("glass") || text.contains("eyewear") || text.contains("sunglass") { return "🕶️" }
        if text.contains("phone") || text.contains("cell") { return "📱" }
        if text.contains("laptop") || text.contains("computer") || text.contains("screen") { return "💻" }
        if text.contains("hat") || text.contains("headwear") || text.contains("cap") { return "🧢" }
        if text.contains("shirt") || text.contains("clothing") || text.contains("jacket") { return "👕" }
        if text.contains("bag") || text.contains("backpack") { return "🎒" }
        if text.contains("car") || text.contains("vehicle") || text.contains("bus") { return "🚗" }
        if text.contains("cup") || text.contains("bottle") || text.contains("drink") { return "🥤" }
        if text.contains("book") { return "📖" }
        if text.contains("tree") || text.contains("plant") { return "🌳" }
        return "🔎"
    }

    /// Convert the stored wall-clock timestamp (e.g. "2:14:08 PM") into a relative
    /// label like "just now" / "12s ago" / "3m ago".
    private func relativeTimeLabel(from timeStamp: String) -> String {
        guard !timeStamp.isEmpty else { return "just now" }
        let formatter = DateFormatter()
        formatter.timeStyle = .medium
        formatter.dateStyle = .none
        guard let parsed = formatter.date(from: timeStamp) else { return "just now" }
        let now = Date()
        // The stored time omits the date; rebuild it on today's calendar.
        let cal = Calendar.current
        let comps = cal.dateComponents([.hour, .minute, .second], from: parsed)
        var todayComps = cal.dateComponents([.year, .month, .day], from: now)
        todayComps.hour = comps.hour
        todayComps.minute = comps.minute
        todayComps.second = comps.second
        guard let stamp = cal.date(from: todayComps) else { return "just now" }
        let delta = now.timeIntervalSince(stamp)
        if delta < 5 { return "just now" }
        if delta < 60 { return "\(Int(delta))s ago" }
        if delta < 3600 { return "\(Int(delta / 60))m ago" }
        return "\(Int(delta / 3600))h ago"
    }

    /// Probe the Mac brain so we can show a plain-words "connected" state.
    func refreshBrainStatus() {
        let base = traceHubURL.isEmpty ? TraceDefaults.hubURL : traceHubURL
        Task {
            let ok = await BrainClient.isHealthy(base: base)
            await MainActor.run { brainReachable = ok }
        }
    }

    func startLiveRuntime() async {
        appendNativeStatusLog(status: "local_runtime_status", extra: TraceLocalRuntime.statusPayload())
        VideoRecorder.shared.configure(hubURL: traceHubURL)
        if spatialMode {
            appendNativeStatusLog(status: "arkit_camera_start_requested")
            TraceARKitEngine.shared.start()
        } else {
            appendNativeStatusLog(status: "camera_start_requested")
            camera.start()
        }
        locationContext.start()
        audioContext.start()
        if ENABLE_LOCAL_DETECTOR_MEMORY {
            detectorBridge.start()
        } else {
            detectorBridge.status = "Detector disabled; FastVLM spatial naming active"
        }
    }

    func monitorBrainStatus() async {
        refreshBrainStatus()
        while !Task.isCancelled {
            try? await Task.sleep(nanoseconds: 8_000_000_000)
            refreshBrainStatus()
        }
    }

    func startFrameDistribution() async {
        if Task.isCancelled {
            return
        }
        appendNativeStatusLog(status: "distribute_video_frames_task_started")
        await distributeVideoFrames()
    }

    func handleDetectorMemoryChange(_ memoryText: String) {
        let cleaned = memoryText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty, !isMemoryPaused else { return }
        let memory = cleaned
            .components(separatedBy: .newlines)
            .map { line in
                line.replacingOccurrences(of: "| detector stream |", with: "| detector stream; \(locationContext.locationMemoryHint) |")
            }
            .joined(separator: "\n")
        commitMemoryRecord(memory, raw: cleaned, source: "native_detector")
    }

    func handleAudioTranscriptChange(_ transcript: String) {
        let cleaned = transcript.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty, !isMemoryPaused else { return }
        let memory = "EVENT | nearby speech | transcript: \"\(cleaned)\" | \(locationContext.locationMemoryHint) | likely"
        commitMemoryRecord(memory, raw: cleaned, source: "native_speech")
    }

    func toggleVideoRecording() {
        if isVideoRecording {
            recordingStatusText = "Finishing capture..."
            VideoRecorder.shared.stopRecording(upload: true) { url, frames in
                DispatchQueue.main.async {
                    isVideoRecording = false
                    if let url {
                        recordingStatusText = "Saved \(url.lastPathComponent) (\(frames) frames) in Files > On My iPhone > FastVLM App > TraceCaptures"
                    } else {
                        recordingStatusText = "No video was saved from this take."
                    }
                }
            }
            return
        }

        VideoRecorder.shared.startRecording(hubURL: traceHubURL)
        isVideoRecording = true
        recordingStatusText = "Recording full camera video now. Tap Stop to save the .mov."
    }

    func performAsk() {
        let q = askText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !q.isEmpty else { return }
        let base = traceHubURL.isEmpty ? "http://127.0.0.1:8765" : traceHubURL
        isAsking = true; askError = ""; askAnswer = ""; askCitations = []; askSource = ""
        Task {
            do {
                let r = try await BrainClient.ask(base: base, question: q, allowFrontier: false)
                await MainActor.run {
                    askAnswer = r.answer
                    askRefused = r.refused ?? false
                    askSource = r.source ?? ""
                    askCitations = (r.citations ?? []).compactMap { $0.label }
                    isAsking = false
                }
            } catch {
                await MainActor.run {
                    askError = "Couldn't reach Trace's brain at \(base). \(error.localizedDescription)"
                    isAsking = false
                }
            }
        }
    }

    @ViewBuilder var cameraSection: some View {
                Section {
                    VStack(alignment: .leading, spacing: 10.0) {
                        Picker("Camera Type", selection: $selectedCameraType) {
                            ForEach(CameraType.allCases, id: \.self) { cameraType in
                                Text(cameraType.rawValue.capitalized).tag(cameraType)
                            }
                        }
                        // Prevent macOS from adding a text label for the picker
                        .labelsHidden()
                        .pickerStyle(.segmented)
                        .onChange(of: selectedCameraType) { _, _ in
                            // Cancel any in-flight requests when switching modes
                            model.cancel()
                        }

                        if let framesToDisplay {
                            VideoFrameView(
                                frames: framesToDisplay,
                                cameraType: selectedCameraType,
                                action: { frame in
                                    processSingleFrame(frame)
                                })
                                // Because we're using the AVCaptureSession preset
                                // `.vga640x480`, we can assume this aspect ratio
                                .aspectRatio(4/3, contentMode: .fit)
                                #if os(macOS)
                                .frame(maxWidth: 750)
                                #endif
                                .overlay(alignment: .top) {
                                    if !model.promptTime.isEmpty {
                                        Text("TTFT \(model.promptTime)")
                                            .font(.caption)
                                            .foregroundStyle(.white)
                                            .monospaced()
                                            .padding(.vertical, 4.0)
                                            .padding(.horizontal, 6.0)
                                            .background(alignment: .center) {
                                                RoundedRectangle(cornerRadius: 8)
                                                    .fill(Color.black.opacity(0.6))
                                            }
                                            .padding(.top)
                                    }
                                }
                                #if !os(macOS)
                                .overlay(alignment: .topTrailing) {
                                    CameraControlsView(
                                        backCamera: $camera.backCamera,
                                        device: $camera.device,
                                        devices: $camera.devices)
                                    .padding()
                                }
                                #endif
                                .overlay(alignment: .bottom) {
                                    if selectedCameraType == .continuous {
                                        Group {
                                            if model.evaluationState == .processingPrompt {
                                                HStack {
                                                    ProgressView()
                                                        .tint(self.statusTextColor)
                                                        .controlSize(.small)

                                                    Text(model.evaluationState.rawValue)
                                                }
                                            } else if model.evaluationState == .idle {
                                                HStack(spacing: 6.0) {
                                                    Image(systemName: "clock.fill")
                                                        .font(.caption)

                                                    Text(model.evaluationState.rawValue)
                                                }
                                            }
                                            else {
                                                // I'm manually tweaking the spacing to
                                                // better match the spacing with ProgressView
                                                HStack(spacing: 6.0) {
                                                    Image(systemName: "lightbulb.fill")
                                                        .font(.caption)

                                                    Text(model.evaluationState.rawValue)
                                                }
                                            }
                                        }
                                        .foregroundStyle(self.statusTextColor)
                                        .font(.caption)
                                        .bold()
                                        .padding(.vertical, 6.0)
                                        .padding(.horizontal, 8.0)
                                        .background(self.statusBackgroundColor)
                                        .clipShape(.capsule)
                                        .padding(.bottom)
                                    }
                                }
                                #if os(macOS)
                                .frame(maxWidth: .infinity)
                                .frame(minWidth: 500)
                                .frame(minHeight: 375)
                                #endif
                        }
                    }
                }
                .listRowInsets(EdgeInsets())
                .listRowBackground(Color.clear)
                .listRowSeparator(.hidden)
    }

    @ViewBuilder var memoryControlsSection: some View {
                Section {
                    HStack {
                        Button(isMemoryPaused ? "Resume Memory" : "Pause Memory") {
                            isMemoryPaused.toggle()
                            appendNativeStatusLog(status: isMemoryPaused ? "memory_paused" : "memory_resumed")
                        }
                        Button("Clear Text Memory") {
                            clearTextMemory(deleteLogFile: false)
                        }
                        Button("Delete Text Log") {
                            clearTextMemory(deleteLogFile: true)
                        }
                    }
                    Text(isMemoryPaused ? "Memory paused: camera preview may remain live, but no object/event text is committed." : "Memory active: live signals become text-only OBJECT/EVENT records.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } header: {
                    Text("Memory Controls")
                        #if os(macOS)
                        .font(.headline)
                        .padding(.bottom, 2.0)
                        #endif
                }
    }

    @ViewBuilder var contextSection: some View {
                Section {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(detectorBridge.status)
                            .foregroundStyle(.secondary)
                        Text(audioContext.status)
                            .foregroundStyle(.secondary)
                        if !audioContext.liveTranscript.isEmpty {
                            Text(audioContext.liveTranscript)
                                .textSelection(.enabled)
                        }
                        Text(locationContext.status)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(locationContext.locationMemoryHint)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .textSelection(.enabled)
                    }
                } header: {
                    Text("Audio / Location Context")
                        #if os(macOS)
                        .font(.headline)
                        .padding(.bottom, 2.0)
                        #endif
                }
    }

    @ViewBuilder var objectEventMemorySection: some View {
                Section {
                    if model.output.isEmpty && model.running {
                        ProgressView()
                            .controlSize(.large)
                            .frame(maxWidth: .infinity)
                    } else {
                        ScrollView {
                            VStack(alignment: .leading, spacing: 14) {
                                if !model.output.isEmpty {
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text("Current frame")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                        Text(model.output)
                                            .foregroundStyle(isEditingPrompt ? .secondary : .primary)
                                            .textSelection(.enabled)
                                            #if os(macOS)
                                            .font(.headline)
                                            .fontWeight(.regular)
                                            #endif
                                    }
                                }

                                Divider()

                                Text(visionStatus)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                Text("Scene: \(currentScenePhase)\(currentMotionScore.map { " · motion \(String(format: "%.3f", $0))" } ?? "")")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                Text("Vision debug: objects \(lastObjectCount) · faces \(lastFaceCount) · bodies \(lastBodyCount) · OCR off")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                if ENABLE_TEXT_OCR_MEMORY && !lastAcceptedOcrPreview.isEmpty {
                                    Text("Last readable text: \(lastAcceptedOcrPreview)")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                        .textSelection(.enabled)
                                } else if ENABLE_TEXT_OCR_MEMORY, let lastVisionNoRecordAt {
                                    Text("No readable text detected \(relativeAgeText(since: lastVisionNoRecordAt)).")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                if let lastVisionInferenceAt {
                                    Text("Last committed vision memory \(relativeAgeText(since: lastVisionInferenceAt)).")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }

                                if !contextFacts.isEmpty {
                                    VStack(alignment: .leading, spacing: 6) {
                                        Text("Built Context")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                        ForEach(
                                            activeContextFacts(limit: 14),
                                            id: \.id
                                        ) { fact in
                                            Text(factDisplayLine(fact))
                                                .font(.caption)
                                                .textSelection(.enabled)
                                                .frame(maxWidth: .infinity, alignment: .leading)
                                        }
                                    }
                                    Divider()
                                }

                                if memoryRecords.isEmpty {
                                    Text("Waiting for object/event memory records...")
                                        .foregroundStyle(.secondary)
                                } else {
                                    ForEach(memoryRecords, id: \.self) { record in
                                        Text(record)
                                            .textSelection(.enabled)
                                            .frame(maxWidth: .infinity, alignment: .leading)
                                        Divider()
                                    }
                                }
                            }
                        }
                        .frame(minHeight: 50.0, maxHeight: 220.0)
                    }
                } header: {
                    Text("Object/Event Memory")
                        #if os(macOS)
                        .font(.headline)
                        .padding(.bottom, 2.0)
                        #endif
                }
    }
    var promptSummary: some View {
        Section("Prompt") {
            VStack(alignment: .leading, spacing: 4.0) {
                let trimmedPrompt = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
                if !trimmedPrompt.isEmpty {
                    Text(trimmedPrompt)
                        .foregroundStyle(.secondary)
                }

                let trimmedSuffix = promptSuffix.trimmingCharacters(in: .whitespacesAndNewlines)
                if !trimmedSuffix.isEmpty {
                    Text(trimmedSuffix)
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                }
            }
        }
    }

    var promptForm: some View {
        Group {
            #if os(iOS)
            Section("Prompt") {
                TextEditor(text: $prompt)
                    .frame(minHeight: 38)
            }

            Section("Prompt Suffix") {
                TextEditor(text: $promptSuffix)
                    .frame(minHeight: 38)
            }
            #elseif os(macOS)
            Section {
                HStack(alignment: .top) {
                    VStack(alignment: .leading) {
                        Text("Prompt")
                            .font(.headline)

                        TextEditor(text: $prompt)
                            .frame(height: 38)
                            .padding(.horizontal, 8.0)
                            .padding(.vertical, 10.0)
                            .background(Color(.textBackgroundColor))
                            .cornerRadius(10.0)
                    }

                    VStack(alignment: .leading) {
                        Text("Prompt Suffix")
                            .font(.headline)

                        TextEditor(text: $promptSuffix)
                            .frame(height: 38)
                            .padding(.horizontal, 8.0)
                            .padding(.vertical, 10.0)
                            .background(Color(.textBackgroundColor))
                            .cornerRadius(10.0)
                    }
                }
            }
            .padding(.vertical)
            #endif
        }
    }

    var promptSections: some View {
        Group {
            #if os(iOS)
            if isEditingPrompt {
                promptForm
            }
            else {
                promptSummary
            }
            #elseif os(macOS)
            promptForm
            #endif
        }
    }

    func analyzeVideoFrames(_ frames: AsyncStream<CVImageBuffer>) async {
        var frameIndex = 0
        var previousFingerprint: [UInt8]?
        var stableFrameCount = 0
        for await frame in frames {
            frameIndex += 1
            let motion = frameMotion(frame, previousFingerprint: previousFingerprint)
            previousFingerprint = motion.fingerprint
            if let score = motion.score {
                stableFrameCount = score < 0.08 ? stableFrameCount + 1 : 0
            }
            let scenePhase = scenePhase(stableFrameCount: stableFrameCount, motionScore: motion.score)
            await MainActor.run {
                currentScenePhase = scenePhase
                currentMotionScore = motion.score
            }
            // sendDebugFrame MOVED OUT of this VLM loop into streamFramesToMac (dense, decoupled):
            // uploading here bound frame streaming to slow VLM inference (~1 frame/min). Now a
            // dedicated consumer streams frames+depth+pose at the FrameSupplier cadence (~5-8/s).
            if frameIndex == 1 || frameIndex % 30 == 0 {
                appendNativeStatusLog(status: "analysis_frame_received", extra: [
                    "frame_index": frameIndex,
                    "width": CVPixelBufferGetWidth(frame),
                    "height": CVPixelBufferGetHeight(frame),
                    "motion_score": motion.score ?? -1,
                    "scene_phase": scenePhase,
                    "stable_frames": stableFrameCount,
                ])
            }
            let paused = await MainActor.run { isMemoryPaused }
            if paused {
                if frameIndex == 1 || frameIndex % 30 == 0 {
                    appendNativeStatusLog(status: "analysis_skipped_memory_paused", extra: [
                        "frame_index": frameIndex,
                        "scene_phase": scenePhase,
                    ])
                }
                do {
                    try await Task.sleep(for: VISION_FRAME_DELAY)
                } catch { return }
                continue
            }
            let locationHint = await MainActor.run { locationContext.locationMemoryHint }
            let localRecord = localVisionRecord(frame, scenePhase: scenePhase, frameIndex: frameIndex, locationHint: locationHint)
            await MainActor.run {
                #if os(iOS)
                if let arFrame = TraceARKitEngine.shared.session.currentFrame,
                   let anchorLabel = localRecord.anchorLabel,
                   let anchorBox = localRecord.anchorBox {
                    TraceARKitEngine.shared.placeOrUpdateAnchor(label: anchorLabel, normalizedBox: anchorBox, in: arFrame)
                }
                #endif
                if ENABLE_LOCAL_DETECTOR_MEMORY {
                    detectorBridge.submit(frame: frame)
                }
            }
            if !localRecord.memory.isEmpty {
                await MainActor.run {
                    visionStatus = "Native Vision \(scenePhase): building object/event context"
                    lastVisionInferenceAt = Date()
                    commitMemoryRecord(
                        localRecord.memory,
                        raw: "native_vision",
                        source: "native_vision",
                        activeLabels: localRecord.activeLabels
                    )
                }
            } else {
                await MainActor.run {
                    visionStatus = "Native Vision \(scenePhase): no stable text/person object"
                }
                if frameIndex % 30 == 0 {
                    appendNativeStatusLog(status: "native_vision_no_record", extra: [
                        "frame_index": frameIndex,
                    ])
                    if scenePhase == "stable" {
                        await MainActor.run {
                            lastVisionNoRecordAt = Date()
                            postSceneStateToHub(scenePhase: scenePhase, motionScore: motion.score, locationHint: locationHint)
                        }
                    }
                }
            }

            let snapshotDue = Date().timeIntervalSince(lastContextSnapshotAt) >= CONTEXT_SNAPSHOT_SECONDS
            if snapshotDue {
                await MainActor.run {
                    appendContextSnapshot(reason: "periodic", scenePhase: scenePhase, motionScore: motion.score)
                    lastContextSnapshotAt = Date()
                }
            }

            let digestDue = Date().timeIntervalSince(lastContextDigestAt) >= CONTEXT_DIGEST_SECONDS
            if digestDue {
                await MainActor.run {
                    appendContextDigest(reason: "periodic", scenePhase: scenePhase, motionScore: motion.score, locationHint: locationHint)
                }
            }

            let semanticDue = await MainActor.run {
                ENABLE_STABLE_VLM_REFRESH
                    && scenePhase != "moving"   // run on stable OR settling — catch brief glimpses, not just dead-still
                    && !model.running
                    && Date().timeIntervalSince(lastSemanticRefreshAt) >= STABLE_VLM_REFRESH_SECONDS
            }
            if semanticDue {
                await MainActor.run {
                    lastSemanticRefreshAt = Date()
                    visionStatus = "Stable scene: running semantic object/event refresh"
                    appendNativeStatusLog(status: "semantic_refresh_started", extra: [
                        "frame_index": frameIndex,
                        "scene_phase": scenePhase,
                    ])
                }
                await runSemanticMemoryRefresh(frame, scenePhase: scenePhase)
            }

            // Salience-ladder gate (EnrichmentScheduler.swift): replaces the
            // fixed cooldown. Dwell+novelty+stability must clear the threshold
            // AND the thermal-scaled hourly budget must grant a token; repeat
            // passes climb overview -> attributes -> minutiae.
            // Capture v2: dwell-triggered FULL-RES still → accurate OCR.
            // Walk-1: stream-buffer OCR was garbage even when the founder
            // dwelled on a poster — the still path is the fix.
            let ocrStillDue = await MainActor.run {
                ENABLE_OCR_STILL_PASS
                    && scenePhase == "stable"
                    && lastAcceptedOcrCount >= 2
                    && Date().timeIntervalSince(lastOcrStillAt) >= 20
            }
            if ocrStillDue {
                await MainActor.run { lastOcrStillAt = Date() }
                // Spatial mode: ARKit owns the camera, AVCapturePhoto is dead —
                // take the still from the running ARSession instead.
                let useARKitStill = await MainActor.run { spatialMode }
                let still: CGImage?
                if useARKitStill {
                    still = await MainActor.run { TraceARKitEngine.shared.captureStillCGImage() }
                } else {
                    still = await camera.captureStill()
                }
                if let still {
                    let text = accurateOCR(cgImage: still)
                    let cleaned = text.trimmingCharacters(in: .whitespacesAndNewlines)
                    if cleaned.count >= 12 {
                        await MainActor.run {
                            commitMemoryRecord(
                                "OBJECT | text surface | full-res OCR: \"\(cleaned.prefix(420))\" | high-resolution still pass | likely",
                                raw: cleaned,
                                source: "ocr_still"
                            )
                            appendNativeStatusLog(status: "ocr_still_committed", extra: [
                                "chars": cleaned.count,
                                "still_width": still.width,
                            ])
                        }
                    } else {
                        await MainActor.run {
                            appendNativeStatusLog(status: "ocr_still_empty", extra: ["chars": cleaned.count])
                        }
                    }
                }
            }

            let personDecision: EnrichmentDecision? = await MainActor.run {
                guard ENABLE_PERSON_VLM_ENRICHMENT,
                      lastFaceCount > 0,
                      scenePhase == "stable",
                      !model.running else { return nil }
                return EnrichmentGovernor.shared.tick(
                    label: "person", motion: currentMotionScore
                )
            }
            if let decision = personDecision {
                await MainActor.run {
                    lastPersonEnrichmentAt = Date()
                    visionStatus = "Person salience \(String(format: "%.2f", decision.salience)): \(decision.detailFocus) pass (L\(decision.level))"
                    appendNativeStatusLog(status: "person_enrichment_started", extra: [
                        "frame_index": frameIndex,
                        "face_count": lastFaceCount,
                        "level": decision.level,
                        "detail_focus": decision.detailFocus,
                        "salience": decision.salience,
                        "scheduler": EnrichmentGovernor.shared.statsDescription,
                    ])
                }
                // Run person enrichment in a detached task with a 12-second hard timeout.
                // Without a timeout, a complex frame (e.g. a laptop screen with a face)
                // can hang model.generate() indefinitely and freeze the entire analysis loop.
                let enrichTask = Task.detached {
                    await self.runPersonEnrichment(frame, focus: decision.detailFocus)
                }
                let timeoutTask = Task {
                    try? await Task.sleep(for: .seconds(12))
                    enrichTask.cancel()
                    await MainActor.run {
                        self.appendNativeStatusLog(status: "person_enrichment_timeout", extra: [
                            "frame_index": frameIndex,
                        ])
                    }
                }
                _ = await enrichTask.result
                timeoutTask.cancel()
            }

            do {
                try await Task.sleep(for: VISION_FRAME_DELAY)
            } catch { return }
        }
    }

    func distributeVideoFrames() async {
        // attach a stream to the camera -- this code will read this
        let frames = AsyncStream<CMSampleBuffer>(bufferingPolicy: .bufferingNewest(1)) {
            if spatialMode {
                TraceARKitEngine.shared.attach(continuation: $0)
            } else {
                camera.attach(continuation: $0)
            }
        }

        let (framesToDisplay, framesToDisplayContinuation) = AsyncStream.makeStream(
            of: CVImageBuffer.self,
            bufferingPolicy: .bufferingNewest(1)
        )
        self.framesToDisplay = framesToDisplay

        // Only create analysis stream if in continuous mode
        let (framesToAnalyze, framesToAnalyzeContinuation) = AsyncStream.makeStream(
            of: CVImageBuffer.self,
            bufferingPolicy: .bufferingNewest(1)
        )

        // DENSE CAPTURE: a dedicated frame->Mac stream, independent of the slow VLM loop.
        // Buffer a few so a transient depth/POST hiccup doesn't drop the keyframe.
        let (framesToStream, framesToStreamContinuation) = AsyncStream.makeStream(
            of: CVImageBuffer.self,
            bufferingPolicy: .bufferingNewest(4)
        )

        // set up structured tasks (important -- this means the child tasks
        // are cancelled when the parent is cancelled)
        async let distributeFrames: () = {
            var displayFrameCount = 0
            for await sampleBuffer in frames {
                // raw-media recorder removed from production target (P0 honesty)
                if let frame = sampleBuffer.imageBuffer {
                    displayFrameCount += 1
                    if displayFrameCount == 1 || displayFrameCount % 120 == 0 {
                        let frameCountSnapshot = displayFrameCount
                        let frameWidth = CVPixelBufferGetWidth(frame)
                        let frameHeight = CVPixelBufferGetHeight(frame)
                        await MainActor.run {
                            appendNativeStatusLog(status: "camera_frame_received", extra: [
                                "frame_count": frameCountSnapshot,
                                "width": frameWidth,
                                "height": frameHeight,
                            ])
                        }
                    }
                    framesToDisplayContinuation.yield(frame)
                    // Dense frame->Mac stream every frame (sendDebugFrame gates emit/sharpness).
                    framesToStreamContinuation.yield(frame)
                    // Only send frames for analysis in continuous mode
                    if await selectedCameraType == .continuous {
                        framesToAnalyzeContinuation.yield(frame)
                    }
                }
            }

            await MainActor.run {
                self.framesToDisplay = nil
                if spatialMode {
                    TraceARKitEngine.shared.detatch()
                } else {
                    self.camera.detatch()
                }
            }

            framesToDisplayContinuation.finish()
            framesToAnalyzeContinuation.finish()
            framesToStreamContinuation.finish()
        }()

        // The dense frame->Mac streamer runs in ALL modes (it's the binder's input).
        async let stream: () = streamFramesToMac(framesToStream)

        // Only analyze frames if in continuous mode
        if selectedCameraType == .continuous {
            async let analyze: () = analyzeVideoFrames(framesToAnalyze)
            await distributeFrames
            await analyze
            await stream
        } else {
            await distributeFrames
            await stream
        }
    }

    /// DENSE CAPTURE consumer: stream frames+depth+pose to the Mac on the FrameSupplier
    /// cadence, fully decoupled from VLM inference. Each emit is fire-and-forget so the
    /// per-frame depth grab + network POST never serialize the stream (the old bottleneck).
    func streamFramesToMac(_ frames: AsyncStream<CVImageBuffer>) async {
        var frameIndex = 0
        for await frame in frames {
            frameIndex += 1
            let idx = frameIndex
            Task { await self.sendDebugFrame(frame, frameIndex: idx) }
        }
    }

    /// Perform FastVLM inference on a single frame.
    /// - Parameter frame: The frame to analyze.
    func processSingleFrame(_ frame: CVImageBuffer) {
        // Reset Response UI (show spinner)
        Task { @MainActor in
            model.output = ""
        }

        // Construct request to model
        var userInput = UserInput(chat: [
            .user("\(prompt) \(promptSuffix)", images: [.ciImage(CIImage(cvPixelBuffer: frame))])
        ])
        userInput.processing.resize = .init(width: 448, height: 448)

        // Post request to FastVLM
        Task {
            let task = await model.generate(userInput)
            _ = await task.result
            let memory = cleanTraceRecord(model.output)
            if !memory.isEmpty {
                await MainActor.run {
                    commitMemoryRecord(memory, raw: model.output, source: "fastvlm_manual")
                }
            }
        }
    }

    func runSemanticMemoryRefresh(_ frame: CVImageBuffer, scenePhase: String) async {
        // NO concrete example here: a tiny VLM copies any example object verbatim
        // (it parroted "Nutella jar / Pringles can" every frame). Format described in
        // words only; screens are INCLUDED (live feed combines physical + on-screen).
        let semanticPrompt = """
            You are a wearable first-person camera. Look at THIS image and list ONLY the \
            things actually visible in it right now — physical objects AND anything shown \
            on a screen.
            Put each on its own line, starting with "OBJECT | " then a short specific \
            name, then " | " then its visible details (color, material, state, position, \
            or any text legibly printed or displayed on it). Use a brand, product, or app \
            name only when its text is clearly readable; otherwise use the plain category.
            Describe only what is genuinely in THIS image. Never invent or guess something \
            that is not there. Do not repeat these instructions and do not output any \
            example object. If the view is unclear, output a single best-guess line, or \
            nothing.
            """

        // Chat form so Qwen2-VL's processor inserts the vision placeholder tokens
        // (the .text form fails: "placeholder tokens does not match number of frames").
        // resize caps vision tokens -> lower on-device memory + faster.
        var userInput = UserInput(chat: [
            .user(semanticPrompt, images: [.ciImage(CIImage(cvPixelBuffer: frame))])
        ])
        userInput.processing.resize = .init(width: 448, height: 448)

        let task = await model.generate(userInput)
        _ = await task.result
        let memory = cleanTraceRecord(model.output)
        await MainActor.run {
            if !memory.isEmpty {
                commitMemoryRecord(memory, raw: model.output, source: "fastvlm_stable_refresh")
                visionStatus = "Stable scene: semantic context refreshed"
                appendNativeStatusLog(status: "semantic_refresh_committed", extra: [
                    "scene_phase": scenePhase,
                    "line_count": memory.components(separatedBy: .newlines).filter { !$0.isEmpty }.count,
                ])
            } else {
                visionStatus = "Stable scene: semantic refresh returned no object/event memory"
                appendNativeStatusLog(status: "semantic_refresh_empty", extra: [
                    "scene_phase": scenePhase,
                    "raw_text": model.output.prefix(240).description,
                ])
            }
        }
    }

    func runPersonEnrichment(_ frame: CVImageBuffer, focus: String = "overview") async {
        // Ladder prompts: deeper passes ask for finer, NEW detail only.
        let detailInstruction: String
        switch focus {
        case "attributes":
            detailInstruction = """
                Focus on SPECIFIC attributes: exact clothing items and colors, \
                accessories (watch, bag, headphones, jewelry), glasses style, \
                facial hair style, hairstyle details.
                """
        case "minutiae":
            detailInstruction = """
                Focus on FINE identifying details only: logos or text on \
                clothing, distinctive marks, patterns, wear on clothing, \
                unique accessories, badge/lanyard text if readable.
                """
        default:
            detailInstruction = "Give the basic picture: age group, build, hair, clothing colors."
        }
        let enrichPrompt = """
            Describe ONLY the person visible in this first-person camera frame.
            \(detailInstruction)
            Output exactly ONE line in this format:
            OBJECT | visible person | [attributes separated by commas] | [pose or location] | likely
            Use these exact words when applicable:
            Age: child, teen, young adult, adult, older adult, elderly
            Build: tall, short, average height, medium build
            Hair: [color] [length] hair (colors: black, brown, dark, blond, gray, red, white)
            Face: glasses, beard, facial hair
            Clothing: [color] shirt/jacket/hoodie, [color] jeans/pants/shorts, [color] shoes/sneakers
            Skip anything not clearly visible. Do NOT output more than one line.
            """

        var userInput = UserInput(chat: [
            .user(enrichPrompt, images: [.ciImage(CIImage(cvPixelBuffer: frame))])
        ])
        userInput.processing.resize = .init(width: 448, height: 448)

        let task = await model.generate(userInput)
        _ = await task.result
        let memory = cleanTraceRecord(model.output)
        await MainActor.run {
            if !memory.isEmpty {
                commitMemoryRecord(memory, raw: model.output, source: "fastvlm_person_enrichment")
                visionStatus = "Person enrichment: VLM slot extraction committed"
                appendNativeStatusLog(status: "person_enrichment_committed", extra: [
                    "raw_text": model.output.prefix(300).description,
                    "clean_text": memory.prefix(300).description,
                ])
            } else {
                appendNativeStatusLog(status: "person_enrichment_empty", extra: [
                    "raw_text": model.output.prefix(240).description,
                ])
            }
        }
    }

    @MainActor
    func commitMemoryRecord(_ memory: String, raw: String, source: String, activeLabels: [String]? = nil) {
        guard !isMemoryPaused else {
            appendNativeStatusLog(status: "memory_commit_skipped_paused", extra: [
                "source": source,
            ])
            return
        }
        let signature = memoryDedupSignature(for: memory)
        let now = Date()
        if let lastSeen = recentMemorySignatures[signature], now.timeIntervalSince(lastSeen) < MEMORY_COMMIT_DEDUP_SECONDS {
            updateContextFacts(memory: memory, source: source, now: now)
            return
        }
        recentMemorySignatures[signature] = now
        recentMemorySignatures = recentMemorySignatures.filter { now.timeIntervalSince($0.value) < 120 }

        updateContextFacts(memory: memory, source: source, now: now)
        let timestamp = Date().formatted(date: .omitted, time: .standard)
        memoryRecords.insert("\(timestamp)\n\(memory)", at: 0)
        appendNativeTextLog(memory: memory, raw: raw, source: source, activeLabels: activeLabels)
        appendContextSnapshot(reason: "memory_commit", scenePhase: currentScenePhase, motionScore: currentMotionScore)
        if memoryRecords.count > 80 {
            memoryRecords.removeLast(memoryRecords.count - 80)
        }
    }

    // M5 — per-track CROP enrichment. The full-frame VLM misses small/far objects (the
    // crop-zoom finding: zoomed OCR recovered Michigan State/Turks). Give each confirmed
    // track ONE zoomed VLM read of its own box; the record carries track_id, so the binder
    // fuses the rich attributes (colour/material/brand) onto that physical instance.
    @MainActor
    func maybeEnrichTrackCrop(frame: CVImageBuffer, label: String, box: CGRect, trackID: String) {
        guard ENABLE_TRACK_CROP_ENRICHMENT else { return }  // kill switch — see flag definition
        let key = "\(label)|\(trackID)"
        guard ENABLE_TRACK_ANCHOR_EMISSION,
              !trackEnrichmentRunning,
              !enrichedTrackKeys.contains(key),
              Date().timeIntervalSince(lastTrackEnrichmentAt) >= 4,
              label != "person"  // people have their own enrichment ladder
        else { return }
        trackEnrichmentRunning = true
        lastTrackEnrichmentAt = Date()
        enrichedTrackKeys.insert(key)
        if enrichedTrackKeys.count > 400 { enrichedTrackKeys.removeAll() }  // session hygiene

        let ci = CIImage(cvPixelBuffer: frame)
        let w = ci.extent.width, h = ci.extent.height
        // Vision boxes are normalized, bottom-left origin — the same space as CIImage.
        let pad: CGFloat = 0.15
        let rect = CGRect(
            x: max(0, (box.minX - pad * box.width) * w),
            y: max(0, (box.minY - pad * box.height) * h),
            width: min(w, (box.width * (1 + 2 * pad)) * w),
            height: min(h, (box.height * (1 + 2 * pad)) * h)
        ).intersection(ci.extent)
        guard rect.width > 32, rect.height > 32 else {
            trackEnrichmentRunning = false
            return
        }
        let crop = ci.cropped(to: rect)
        let prompt = """
            This is a zoomed crop of a \(label) from a first-person camera. Describe ONLY \
            this \(label): its colour, material, brand or printed text if readable, and any \
            distinctive feature. Output exactly ONE line:
            OBJECT | \(label) | [attributes separated by commas] | crop-zoom | likely
            """
        Task {
            var userInput = UserInput(chat: [.user(prompt, images: [.ciImage(crop)])])
            userInput.processing.resize = .init(width: 448, height: 448)
            let task = await model.generate(userInput)
            _ = await task.result
            let memory = cleanTraceRecord(model.output)
            await MainActor.run {
                trackEnrichmentRunning = false
                guard !memory.isEmpty, memory.hasPrefix("OBJECT |") else {
                    appendNativeStatusLog(status: "track_crop_enrichment_empty", extra: [
                        "track_id": trackID, "label": label,
                    ])
                    return
                }
                let payload: [String: Any] = [
                    "timestamp": ISO8601DateFormatter().string(from: Date()),
                    "memory_text": memory,
                    "source": "fastvlm_track_crop",
                    "source_type": "vision",
                    "scene_phase": currentScenePhase,
                    "location_hint": locationContext.locationMemoryHint,
                    "metadata": ["track_id": trackID, "detector_label": label,
                                 "crop_zoom": true],
                ]
                postPerceptionPacketToHub(payload)
                appendNativeStatusLog(status: "track_crop_enrichment_committed", extra: [
                    "track_id": trackID, "label": label,
                    "clean_text": memory.prefix(200).description,
                ])
            }
        }
    }

    @MainActor
    func clearTextMemory(deleteLogFile: Bool) {
        memoryRecords.removeAll()
        contextFacts.removeAll()
        recentMemorySignatures.removeAll()
        lastContextDigestAt = Date.distantPast
        lastContextDigestSignature = ""
        lastPersonEnrichmentAt = Date.distantPast
        model.output = ""
        if deleteLogFile {
            try? FileManager.default.removeItem(at: nativeLogURL())
        }
        appendNativeStatusLog(status: deleteLogFile ? "text_log_deleted" : "text_memory_cleared")
    }

    @MainActor
    func updateContextFacts(memory: String, source: String, now: Date) {
        for line in memory.components(separatedBy: .newlines) {
            let cleaned = line.trimmingCharacters(in: .whitespacesAndNewlines)
            guard cleaned.hasPrefix("OBJECT |") || cleaned.hasPrefix("EVENT |") else {
                continue
            }

            let signature = contextFactKey(for: cleaned)
            if var fact = contextFacts[signature] {
                fact.lastSeen = now
                fact.observations += 1
                fact.source = source
                fact.text = preferredFactText(existing: fact.text, candidate: cleaned)
                contextFacts[signature] = fact
            } else {
                contextFacts[signature] = TraceContextFact(
                    id: signature,
                    text: cleaned,
                    firstSeen: now,
                    lastSeen: now,
                    observations: 1,
                    source: source
                )
            }
        }

        if contextFacts.count > 120 {
            let keep = contextFacts.values
                .sorted { $0.lastSeen > $1.lastSeen }
                .prefix(100)
            contextFacts = Dictionary(uniqueKeysWithValues: keep.map { ($0.id, $0) })
        }

        contextFacts = contextFacts.filter { _, fact in
            now.timeIntervalSince(fact.lastSeen) <= CONTEXT_STALE_SECONDS
        }
    }

    func activeContextFacts(limit: Int, now: Date = Date()) -> [TraceContextFact] {
        let facts = Array(contextFacts.values)
        let active = facts.filter { now.timeIntervalSince($0.lastSeen) <= CONTEXT_ACTIVE_SECONDS }
        let candidates = active.isEmpty ? facts : active
        return Array(
            candidates
                .sorted { contextFactScore($0, now: now) > contextFactScore($1, now: now) }
                .prefix(limit)
        )
    }

    func contextFactScore(_ fact: TraceContextFact, now: Date) -> Double {
        let age = max(0, now.timeIntervalSince(fact.lastSeen))
        let recency = max(0, 1 - (age / CONTEXT_ACTIVE_SECONDS))
        let strength = min(Double(fact.observations), 50)
        return recency * 1_000 + strength
    }

    func contextFactKey(for line: String) -> String {
        let parts = line
            .components(separatedBy: "|")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() }
        let meaningfulParts = parts.prefix(3).joined(separator: "|")
        return meaningfulParts
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    func memoryDedupSignature(for memory: String) -> String {
        let factKeys = memory
            .components(separatedBy: .newlines)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { $0.hasPrefix("OBJECT |") || $0.hasPrefix("EVENT |") }
            .map(contextFactKey)

        if !factKeys.isEmpty {
            return factKeys.joined(separator: "\n")
        }

        return memory
            .lowercased()
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    func preferredFactText(existing: String, candidate: String) -> String {
        let existingLikely = existing.lowercased().contains("| likely")
        let candidateLikely = candidate.lowercased().contains("| likely")
        if candidateLikely && !existingLikely {
            return candidate
        }
        if existingLikely && !candidateLikely {
            return existing
        }
        if candidate.count > existing.count {
            return candidate
        }
        return existing
    }

    func factDisplayLine(_ fact: TraceContextFact, now: Date = Date()) -> String {
        "\(fact.text) · seen \(fact.observations)x · last seen \(relativeAgeText(since: fact.lastSeen, now: now))"
    }

    func relativeAgeText(since date: Date, now: Date = Date()) -> String {
        let seconds = max(0, Int(now.timeIntervalSince(date)))
        if seconds < 2 {
            return "now"
        }
        if seconds < 60 {
            return "\(seconds)s ago"
        }
        let minutes = seconds / 60
        if minutes < 60 {
            return "\(minutes)m ago"
        }
        let hours = minutes / 60
        return "\(hours)h ago"
    }

    func cleanTraceRecord(_ text: String) -> String {
        text
            .components(separatedBy: .newlines)
            .map { rawLine in
                rawLine
                    .replacingOccurrences(of: #"^\s*[-*•]?\s*\d*\.?\s*"#, with: "", options: .regularExpression)
                    .trimmingCharacters(in: .whitespacesAndNewlines)
            }
            .compactMap { line -> String? in
                let lower = line.lowercased()
                let banned = [
                    "camera",
                    "taking a picture",
                    "photo",
                    "photograph",
                    "image",
                    "screenshot",
                    "object name",
                    "concrete visible attributes",
                    "visible action/change/state",
                    "visible action/state",
                    "likely/uncertain",
                    "involved object/person",
                    "relation/location",
                    "relation to other visible",
                ]
                if banned.contains(where: { lower.contains($0) }) {
                    return nil
                }
                if lower.hasPrefix("object:") {
                    let objectName = line.dropFirst("object:".count).trimmingCharacters(in: .whitespacesAndNewlines)
                    guard objectName.count >= 3, objectName.lowercased() != "person" else { return nil }
                    return "OBJECT | \(objectName) | visible object | visible frame | uncertain"
                }
                if lower.hasPrefix("event:") {
                    let eventName = line.dropFirst("event:".count).trimmingCharacters(in: .whitespacesAndNewlines)
                    guard eventName.count >= 3 else { return nil }
                    return "EVENT | visible scene | \(eventName) | visible frame | uncertain"
                }
                return line
            }
            .filter { line in
                let upper = line.uppercased()
                let lower = line.lowercased()
                guard upper.hasPrefix("OBJECT |") || upper.hasPrefix("EVENT |") else {
                    return false
                }
                if lower.hasPrefix("event | camera view |") {
                    return false
                }
                return !lower.contains("visible scene | taking a picture")
            }
            .map { line in
                if line.uppercased().hasPrefix("OBJECT |") {
                    return "OBJECT |" + line.dropFirst("OBJECT |".count)
                }
                if line.uppercased().hasPrefix("EVENT |") {
                    return "EVENT |" + line.dropFirst("EVENT |".count)
                }
                return line
            }
            .prefix(6)
            .joined(separator: "\n")
    }

    func localVisionRecord(_ frame: CVImageBuffer, scenePhase: String, frameIndex: Int, locationHint: String) -> TracePerceptionRecord {
        let personRequest = VNDetectHumanRectanglesRequest()
        let faceRequest = VNDetectFaceRectanglesRequest()
        let classificationRequest = VNClassifyImageRequest()
        var requests: [VNRequest] = [personRequest, faceRequest]
        if ENABLE_IMAGE_CLASSIFICATION_MEMORY {
            requests.append(classificationRequest)
        }
        let handler = VNImageRequestHandler(cvPixelBuffer: frame, orientation: .up)

        do {
            try handler.perform(requests)
        } catch {
            return TracePerceptionRecord(memory: "", activeLabels: [], anchorLabel: nil, anchorBox: nil)
        }

        var records: [String] = []
        let textRecognition = ENABLE_TEXT_OCR_MEMORY
            ? recognizedTextObservations(frame: frame, scenePhase: scenePhase)
            : TraceTextRecognitionResult(observations: [], orientationsWithHits: [])
        let textObservations = textRecognition.observations
        let humanObservations: [VNHumanObservation] = personRequest.results ?? []
        let faceObservations: [VNFaceObservation] = faceRequest.results ?? []
        let classificationObservations: [VNClassificationObservation] = ENABLE_IMAGE_CLASSIFICATION_MEMORY
            ? (classificationRequest.results ?? [])
            : []

        let rawTextHits = textObservations.compactMap { observation -> TraceTextHit? in
                guard let candidate = observation.topCandidates(1).first else { return nil }
                let text = cleanOcrText(candidate.string)
                guard !text.isEmpty else { return nil }
                return TraceTextHit(text: text, confidence: candidate.confidence, box: observation.boundingBox)
            }
        let textHits = uniqueTextHits(
            rawTextHits.filter { hit in
                isUsefulOcrText(hit.text, confidence: hit.confidence, scenePhase: scenePhase)
            }
        )
        let textBoxes = textHits.map { $0.box }
        var bodyBoxes = filterPersonLikeBoxes(
            humanObservations.map { $0.boundingBox },
            textBoxes: textBoxes,
            minimumArea: 0.015
        )
        var faceBoxes = filterPersonLikeBoxes(
            faceObservations.map { $0.boundingBox },
            textBoxes: textBoxes,
            minimumArea: 0.008
        )
        var bodyCount = bodyBoxes.count
        var faceCount = faceBoxes.count
        var personBoxes = bodyBoxes + faceBoxes
        var peopleCount = max(bodyCount, faceCount)
        let rawClassificationHits = classificationObservations.map {
            TraceClassificationHit(label: $0.identifier, confidence: $0.confidence)
        }
        var classificationHits = filteredClassificationHits(rawClassificationHits, scenePhase: scenePhase)
        // CoreML object detector (capture v2): localized real objects —
        // bicycle/bench/backpack-class — that scene classification missed.
        // Walking frames get a higher confidence bar (motion blur).
        let objectHits: [DetectedObjectV2] = ObjectDetectorV2.shared.detect(
            frame, minimumConfidence: scenePhase == "moving" ? 0.50 : 0.40
        )
        let primaryAnchorCandidate = objectHits.max { lhs, rhs in
            lhs.confidence < rhs.confidence
        }
        if isLikelySelfFacingArtifact(personBoxes: personBoxes, textHits: textHits, classificationHits: classificationHits) {
            bodyBoxes = []
            faceBoxes = []
            bodyCount = 0
            faceCount = 0
            personBoxes = []
            peopleCount = 0
            classificationHits = classificationHits.filter { !isWearableAccessoryClassification($0.label) }
        }
        let gpsHint = locationHint
        let frameRelation = relationSummary(textBoxes: textBoxes, personBoxes: personBoxes, peopleCount: peopleCount, gpsHint: gpsHint)

        // Step 1 track-anchor emission: each tracked object becomes its OWN observation carrying a
        // stable track_id, so the binder fuses aspects per physical object and counts distinct
        // instances without world coordinates. Additive `detector_track` channel — leaves the
        // frame-level VLM/OCR records below untouched. COCO-class labels only.
        if ENABLE_TRACK_ANCHOR_EMISSION, !objectHits.isEmpty {
            let assocs = TrackRegistry.shared.update(detections: objectHits, frameIndex: frameIndex) { det in
                MobileClipEncoder.shared.embed(frame, box: det.box)
            }
            // Only emit CONFIRMED tracks (seen >= 2) so a single-frame false detection never becomes
            // a phantom instance — one of the two over-count sources (the other, pan-away-and-back,
            // is handled by appearance re-ID inside the registry).
            for a in assocs where a.seenCount >= 2 {
                let det = a.det
                let cx = det.box.midX
                let horiz = cx < 0.33 ? "left" : (cx > 0.66 ? "right" : "center")
                let cy = det.box.midY  // Vision boundingBox origin is bottom-left
                let vert = cy > 0.66 ? "upper" : (cy < 0.33 ? "lower" : "middle")
                // Per-object depth (metres) sampled at the box centre — the spatial signal that lets
                // the brain reason "in front of / behind / on top of". nil when depth is unavailable.
                var md: [String: Any] = ["track_id": a.trackID, "detector_label": det.label]
                var depthTxt = ""
                // COORDINATE-FIRST: unproject the box to a measured 3D position + physical size, so
                // the binder can individuate by location and the brain answers "how big / where /
                // on top of" from measurement, not a guess. Degrades safely to no-depth.
                if let m = DepthReceiver.shared.metricBox(det.box) {
                    md["world_xyz"] = [Double(m.x), Double(m.y), Double(m.z)]
                    md["size_m"] = [Double(m.widthM), Double(m.heightM)]
                    md["depth_m"] = Double(m.z)
                    md["img_cx"] = Double(cx)
                    md["img_cy"] = Double(cy)
                    depthTxt = String(format: " ~%.2fm from camera, ~%.0f×%.0fcm;",
                                      Double(m.z), Double(m.widthM * 100), Double(m.heightM * 100))
                } else if let depth = DepthReceiver.shared.depthMeters(atNormalizedX: cx, y: cy) {
                    md["depth_m"] = Double(depth)
                    md["img_cx"] = Double(cx)
                    md["img_cy"] = Double(cy)
                    depthTxt = String(format: " ~%.2fm from camera;", Double(depth))
                }
                // M4: OCR->object binding. Text read INSIDE (or at the edge of) this track's
                // box is the object's own label/brand — bind it to the instance here, at the
                // only place both boxes exist. Downstream, "what brand is the drill" retrieves
                // the drill's track row carrying its verbatim text, instead of a floating OCR
                // row nothing links back. Worded as `label text:` so the count-floor's
                // verbatim guard never reads a bound digit as a scene count.
                var boundTxt = ""
                if !textHits.isEmpty {
                    let reach = det.box.insetBy(dx: -0.02, dy: -0.02)
                    let inside = textHits.filter { reach.intersects($0.box) }
                    if !inside.isEmpty {
                        let joined = String(inside.map { $0.text }.joined(separator: " / ").prefix(90))
                        boundTxt = " label text: \"\(joined)\";"
                        md["bound_text"] = joined
                    }
                }
                let text = "OBJECT | \(det.label) | detected by on-device tracker |\(boundTxt)\(depthTxt) \(vert)-\(horiz) of frame; \(frameRelation) | likely"
                let payload: [String: Any] = [
                    "memory_text": text,
                    "source": "detector_track",
                    "metadata": md,
                ]
                Task { @MainActor in
                    self.postPerceptionPacketToHub(payload)
                    // M5: one zoomed VLM read per confirmed track (throttled inside).
                    self.maybeEnrichTrackCrop(frame: frame, label: det.label,
                                              box: det.box, trackID: a.trackID)
                }
            }
        }

        if frameIndex == 1 || frameIndex % 30 == 0 {
            Task { @MainActor in
                lastRawOcrCount = rawTextHits.count
                lastAcceptedOcrCount = textHits.count
                lastObjectCount = objectHits.count
                lastBodyCount = bodyCount
                lastFaceCount = faceCount
                lastAcceptedOcrPreview = compactVisibleText(textHits, maxCharacters: 140) ?? ""
            }
            appendNativeStatusLog(status: "native_vision_candidates", extra: [
                "frame_index": frameIndex,
                "scene_phase": scenePhase,
                "raw_ocr_count": rawTextHits.count,
                "ocr_count": textHits.count,
                "ocr_orientations_with_hits": textRecognition.orientationsWithHits,
                "accepted_ocr_samples": textHits.prefix(6).map { "\($0.text):\(String(format: "%.2f", $0.confidence))" },
                "rejected_ocr_samples": rejectedOcrSamples(rawTextHits: rawTextHits, acceptedTextHits: textHits),
                "object_count": objectHits.count,
                "object_samples": objectHits.prefix(8).map { "\($0.label):\(String(format: "%.2f", $0.confidence))" },
                "body_count": bodyCount,
                "face_count": faceCount,
                "accepted_classifications": classificationHits.prefix(6).map { "\($0.label):\(String(format: "%.2f", $0.confidence))" },
                "raw_classifications": rawClassificationHits.prefix(8).map { "\(normalizedClassificationLabel($0.label)):\(String(format: "%.2f", $0.confidence))" },
            ])
        }

        if scenePhase == "moving" {
            let textSurfaceLabel = inferredTextSurfaceObjectLabel(textHits: textHits, classificationHits: classificationHits)
            if peopleCount == 1 {
                records.append("OBJECT | visible person | \(personAttributeText(bodyCount: bodyCount, faceCount: faceCount)); detected while camera moving | \(frameRelation) | uncertain")
            } else if peopleCount > 1 {
                records.append("OBJECT | visible people | \(peopleCount) people/faces detected; \(personGroupAttributeText(bodyCount: bodyCount, faceCount: faceCount)); detected while camera moving | \(frameRelation) | uncertain")
                records.append("OBJECT | background person | additional face/person detected; partial person visible while camera moving | behind/near foreground subject; \(gpsHint) | uncertain")
            }
            if let textBlock = compactVisibleText(textHits, maxCharacters: 90) {
                records.append("OBJECT | \(textSurfaceLabel) | provisional OCR text: \"\(textBlock)\" | \(frameRelation) | uncertain")
            }
            if ENABLE_DETECTOR_OBJECT_MEMORY {
                records.append(contentsOf: objectHits.map { obj in
                    "OBJECT | visible \(obj.label) | detected | \(frameRelation) | uncertain"
                })
            }
            records.append(contentsOf: classificationMemoryLines(
                classificationHits,
                scenePhase: scenePhase,
                frameRelation: frameRelation,
                peopleCount: peopleCount
            ))
            let memory = records.prefix(8).joined(separator: "\n")
            return TracePerceptionRecord(
                memory: memory,
                activeLabels: derivedActiveEntityLabels(
                    memory: memory,
                    textSurfaceLabel: textHits.isEmpty ? nil : textSurfaceLabel,
                    peopleCount: peopleCount,
                    classificationHits: classificationHits
                ),
                anchorLabel: memory.isEmpty ? nil : (primaryAnchorCandidate?.label ?? "scene"),
                anchorBox: memory.isEmpty ? nil : (primaryAnchorCandidate?.box ?? CGRect(x: 0.25, y: 0.25, width: 0.5, height: 0.5))
            )
        }

        let textSurfaceLabel = inferredTextSurfaceObjectLabel(textHits: textHits, classificationHits: classificationHits)
        if let textBlock = compactVisibleText(textHits, maxCharacters: scenePhase == "stable" ? 220 : 120) {
            let maxOcrConfidence = textHits.map { $0.confidence }.max() ?? 0
            let certainty = maxOcrConfidence > 0.65 ? "likely" : "uncertain"
            records.append("OBJECT | \(textSurfaceLabel) | OCR text: \"\(textBlock)\" | \(frameRelation) | \(certainty)")
        }

        if peopleCount == 1 {
            records.append("OBJECT | visible person | \(personAttributeText(bodyCount: bodyCount, faceCount: faceCount)); detected | \(frameRelation) | likely")
        } else if peopleCount > 1 {
            records.append("OBJECT | visible people | \(peopleCount) people/faces detected; \(personGroupAttributeText(bodyCount: bodyCount, faceCount: faceCount)) | \(frameRelation) | likely")
            records.append("OBJECT | background person | additional face/person detected; partial person visible | behind/near foreground subject; \(gpsHint) | likely")
        }

        if peopleCount > 0, !textHits.isEmpty {
            records.append("EVENT | visible person | near or below \(textSurfaceLabel) | \(frameRelation) | \(scenePhase == "stable" ? "likely" : "uncertain")")
        }

        if ENABLE_DETECTOR_OBJECT_MEMORY {
            records.append(contentsOf: objectHits.map { obj in
                "OBJECT | visible \(obj.label) | detected | \(frameRelation) | \(obj.confidence > 0.6 ? "likely" : "uncertain")"
            })
        }
        records.append(contentsOf: classificationMemoryLines(
            classificationHits,
            scenePhase: scenePhase,
            frameRelation: frameRelation,
            peopleCount: peopleCount
        ))

        let memory = records.prefix(12).joined(separator: "\n")
        return TracePerceptionRecord(
            memory: memory,
            activeLabels: derivedActiveEntityLabels(
                memory: memory,
                textSurfaceLabel: textHits.isEmpty ? nil : textSurfaceLabel,
                peopleCount: peopleCount,
                classificationHits: classificationHits
            ),
            anchorLabel: memory.isEmpty ? nil : (primaryAnchorCandidate?.label ?? "scene"),
            anchorBox: memory.isEmpty ? nil : (primaryAnchorCandidate?.box ?? CGRect(x: 0.25, y: 0.25, width: 0.5, height: 0.5))
        )
    }

    func personAttributeText(bodyCount: Int, faceCount: Int) -> String {
        var attributes: [String] = []
        if bodyCount > 0 {
            attributes.append("human figure")
            attributes.append("body/upper body visible")
        }
        if faceCount > 0 {
            attributes.append("face detected")
        }
        if attributes.isEmpty {
            attributes.append("face/partial person")
        }
        return attributes.joined(separator: "; ")
    }

    func personGroupAttributeText(bodyCount: Int, faceCount: Int) -> String {
        var attributes: [String] = []
        if bodyCount > 0 {
            attributes.append("\(bodyCount) human body rectangles")
        }
        if faceCount > 0 {
            attributes.append("\(faceCount) face rectangles")
        }
        if attributes.isEmpty {
            attributes.append("multiple partial people")
        }
        return attributes.joined(separator: "; ")
    }

    func recognizedTextObservations(frame: CVImageBuffer, scenePhase: String) -> TraceTextRecognitionResult {
        let orientations: [(String, CGImagePropertyOrientation)] = scenePhase == "moving"
            ? [("up", .up)]
            : [("up", .up), ("right", .right), ("left", .left), ("down", .down)]
        var observations: [VNRecognizedTextObservation] = []
        var orientationsWithHits: [String] = []

        for (name, orientation) in orientations {
            let request = VNRecognizeTextRequest()
            configureTextRecognition(request, scenePhase: scenePhase)
            let handler = VNImageRequestHandler(cvPixelBuffer: frame, orientation: orientation)
            do {
                try handler.perform([request])
                let results = request.results ?? []
                if !results.isEmpty {
                    observations.append(contentsOf: results)
                    orientationsWithHits.append(name)
                }
            } catch {
                continue
            }
        }

        return TraceTextRecognitionResult(
            observations: observations,
            orientationsWithHits: orientationsWithHits
        )
    }

    func configureTextRecognition(_ request: VNRecognizeTextRequest, scenePhase: String) {
        request.recognitionLevel = scenePhase == "moving" ? .fast : .accurate
        request.usesLanguageCorrection = scenePhase != "moving"
        request.recognitionLanguages = ["en-US", "en-GB", "de-DE"]
        request.minimumTextHeight = scenePhase == "moving" ? 0.012 : 0.008
        request.customWords = [
            "Garching",
            "Forschungszentrum",
            "Walther-Meissner-Str.",
            "Walther-Meißner-Str.",
            "Lichtenbergstr.",
            "Boltzmannstr.",
            "Anna-Boyksen-Str.",
            "Max-Planck-Campus",
            "Max Planck Campus",
            "Campus",
            "Bus",
            "U-Bahn",
            "S-Bahn",
            "Wikipedia",
            "featured",
            "article",
            "archive",
            "follow",
            "views",
            "edited",
            "instagram.com",
        ]
    }

    func filteredClassificationHits(_ hits: [TraceClassificationHit], scenePhase: String) -> [TraceClassificationHit] {
        let threshold: Float = scenePhase == "stable" ? 0.42 : 0.52
        var seen = Set<String>()
        return hits
            .map { hit in
                TraceClassificationHit(label: normalizedClassificationLabel(hit.label), confidence: hit.confidence)
            }
            .filter { hit in
                guard hit.confidence >= threshold else { return false }
                guard hit.label.count >= 3 else { return false }
                let lower = hit.label.lowercased()
                let blocked = [
                    "camera",
                    "photo",
                    "picture",
                    "image",
                    "snapshot",
                    "screenshot",
                    "person",
                    "people",
                    "human",
                    "face",
                    "adult",
                    "teen",
                    "child",
                    "portrait",
                    "selfie",
                    "outdoor",
                    "indoor",
                    "sky",
                    "night",
                    "daytime",
                    "landscape",
                    "scene",
                    "nature",
                    "horizon",
                    "cloud",
                    "sunset",
                    "sunrise",
                    "celestial",
                    "astronomy",
                    "space",
                    "room",
                    "ceiling",
                    "floor",
                    "wall",
                    "building",
                    "architecture",
                    "structure",
                    "conveyance",
                    "portal",
                    "material",
                    "optical equipment",
                    "sunglasses",
                    "raw glass",
                ]
                guard !blocked.contains(where: { lower.contains($0) }) else { return false }
                guard !seen.contains(lower) else { return false }
                seen.insert(lower)
                return true
            }
            .sorted { $0.confidence > $1.confidence }
    }

    func classificationMemoryLines(
        _ hits: [TraceClassificationHit],
        scenePhase: String,
        frameRelation: String,
        peopleCount: Int
    ) -> [String] {
        let prioritizedHits = hits.sorted { lhs, rhs in
            let lhsPriority = classificationPriority(lhs.label, peopleCount: peopleCount)
            let rhsPriority = classificationPriority(rhs.label, peopleCount: peopleCount)
            if lhsPriority == rhsPriority {
                return lhs.confidence > rhs.confidence
            }
            return lhsPriority < rhsPriority
        }
        let maxLines = scenePhase == "stable" ? 4 : 2
        var seen = Set<String>()
        var lines: [String] = []
        for hit in prioritizedHits {
            let key = hit.label.lowercased()
            guard !seen.contains(key) else { continue }
            seen.insert(key)
            guard let line = classificationMemoryLine(
                hit,
                scenePhase: scenePhase,
                frameRelation: frameRelation,
                peopleCount: peopleCount
            ) else {
                continue
            }
            lines.append(line)
            if lines.count >= maxLines {
                break
            }
        }
        return lines
    }

    func classificationPriority(_ label: String, peopleCount: Int) -> Int {
        let lower = label.lowercased()
        if peopleCount > 0 {
            if lower.contains("headphone") || lower.contains("earphone") { return 0 }
            if lower.contains("eyeglass") || lower == "glasses" { return 1 }
            if lower.contains("shirt") || lower.contains("jacket") || lower.contains("coat") || lower.contains("cap") || lower.contains("hat") { return 2 }
        }
        return 10
    }

    func classificationMemoryLine(
        _ hit: TraceClassificationHit,
        scenePhase: String,
        frameRelation: String,
        peopleCount: Int
    ) -> String? {
        let certainty = hit.confidence >= 0.62 ? "likely" : "uncertain"
        let lower = hit.label.lowercased()
        let movingSuffix = scenePhase == "moving" ? " while camera moving" : ""

        if peopleCount > 0 {
            if lower.contains("headphone") || lower.contains("earphone") {
                return "OBJECT | \(hit.label) | worn on head\(movingSuffix) | on visible person; \(frameRelation) | \(certainty)"
            }
            if lower.contains("eyeglass") || lower == "glasses" {
                return "OBJECT | \(hit.label) | eyewear visible\(movingSuffix) | near visible person; \(frameRelation) | \(certainty)"
            }
            if lower.contains("shirt") || lower.contains("jacket") || lower.contains("coat") {
                return "OBJECT | \(hit.label) | upper-body clothing\(movingSuffix) | worn by visible person; \(frameRelation) | \(certainty)"
            }
            if lower.contains("cap") || lower.contains("hat") {
                return "OBJECT | \(hit.label) | headwear visible\(movingSuffix) | worn by visible person; \(frameRelation) | \(certainty)"
            }
        }

        let descriptor = scenePhase == "moving"
            ? "provisional visual classification while camera moving"
            : "image-level visual classification"
        return "OBJECT | \(hit.label) | \(descriptor) | \(frameRelation) | \(certainty)"
    }

    func isLikelySelfFacingArtifact(personBoxes: [CGRect], textHits: [TraceTextHit], classificationHits: [TraceClassificationHit]) -> Bool {
        guard textHits.isEmpty, !personBoxes.isEmpty else { return false }
        guard let personBox = unionRect(personBoxes) else { return false }
        let personArea = max(0, personBox.width) * max(0, personBox.height)
        let centered = personBox.midX > 0.25 && personBox.midX < 0.75
        let largeEnough = personArea >= 0.12
        let accessoryHeavy = classificationHits.isEmpty || classificationHits.allSatisfy {
            isWearableAccessoryClassification($0.label)
        }
        return centered && largeEnough && accessoryHeavy
    }

    func isWearableAccessoryClassification(_ label: String) -> Bool {
        let lower = label.lowercased()
        return lower.contains("headphone")
            || lower.contains("earphone")
            || lower.contains("eyeglass")
            || lower.contains("glasses")
            || lower.contains("sunglasses")
    }

    func normalizedClassificationLabel(_ identifier: String) -> String {
        let firstLabel = identifier
            .components(separatedBy: ",")
            .first ?? identifier
        return firstLabel
            .replacingOccurrences(of: "_", with: " ")
            .replacingOccurrences(of: "-", with: " ")
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
    }

    func cleanOcrText(_ text: String) -> String {
        text
            .replacingOccurrences(of: "\n", with: " ")
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
            .replacingOccurrences(of: #"^[^\p{L}\p{N}]+|[^\p{L}\p{N}\.\-/:]+$"#, with: "", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    func isUsefulOcrText(_ text: String, confidence: VNConfidence, scenePhase: String) -> Bool {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count >= 3 else { return false }

        let normalized = trimmed
            .lowercased()
            .replacingOccurrences(of: "[^a-z0-9äöüß]+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard normalized.count >= 3 else { return false }

        let letters = normalized.filter { $0.isLetter }
        let digits = normalized.filter { $0.isNumber }
        guard letters.count >= 2 || digits.count >= 3 else { return false }

        let tokens = normalized
            .components(separatedBy: .whitespaces)
            .filter { $0.count >= 2 }
        let hasLongWord = tokens.contains { $0.count >= 4 }
        let enoughConfidence = confidence >= (scenePhase == "stable" ? 0.28 : 0.42)
        guard enoughConfidence || (hasLongWord && confidence >= 0.20) else { return false }

        let junkPatterns = [
            #"^[il1|/\\\-_.:;]+$"#,
            #"^[a-z]{1,2}\d?$"#,
            #"^\d{1,2}$"#,
        ]
        return !junkPatterns.contains { pattern in
            normalized.range(of: pattern, options: .regularExpression) != nil
        }
    }

    func rejectedOcrSamples(rawTextHits: [TraceTextHit], acceptedTextHits: [TraceTextHit]) -> [String] {
        let accepted = Set(acceptedTextHits.map {
            normalizedOcrKey($0.text)
        })

        return rawTextHits
            .filter { hit in
                let key = normalizedOcrKey(hit.text)
                return !accepted.contains(key)
            }
            .prefix(6)
            .map { "\($0.text):\(String(format: "%.2f", $0.confidence))" }
    }

    func uniqueTextHits(_ hits: [TraceTextHit]) -> [TraceTextHit] {
        let merged = mergeTextHitsIntoLines(hits)
        var bestByKey: [String: TraceTextHit] = [:]

        for hit in merged {
            let key = normalizedOcrKey(hit.text)
            guard !key.isEmpty else { continue }
            if let existing = bestByKey[key] {
                if shouldReplaceTextHit(existing: existing, candidate: hit) {
                    bestByKey[key] = hit
                }
            } else {
                bestByKey[key] = hit
            }
        }

        return bestByKey.values.sorted {
            if abs($0.box.midY - $1.box.midY) < 0.02 {
                return $0.box.minX < $1.box.minX
            }
            return $0.box.midY > $1.box.midY
        }
    }

    func mergeTextHitsIntoLines(_ hits: [TraceTextHit]) -> [TraceTextHit] {
        let sorted = hits.sorted {
            if abs($0.box.midY - $1.box.midY) < 0.025 {
                return $0.box.minX < $1.box.minX
            }
            return $0.box.midY > $1.box.midY
        }

        var lines: [[TraceTextHit]] = []
        for hit in sorted {
            if let index = lines.firstIndex(where: { belongsToSameTextLine(hit, line: $0) }) {
                lines[index].append(hit)
            } else {
                lines.append([hit])
            }
        }

        let mergedLines = lines.compactMap { line -> TraceTextHit? in
            let ordered = line.sorted { $0.box.minX < $1.box.minX }
            let mergedText = ordered
                .map(\.text)
                .reduce(into: [String]()) { parts, text in
                    let normalized = normalizedOcrKey(text)
                    guard !normalized.isEmpty else { return }
                    if parts.last.map(normalizedOcrKey) == normalized {
                        return
                    }
                    parts.append(text)
                }
                .joined(separator: " ")
            let cleaned = cleanOcrText(mergedText)
            guard !cleaned.isEmpty else { return nil }
            let mergedBox = unionRect(ordered.map(\.box)) ?? ordered[0].box
            let confidence = ordered.map(\.confidence).max() ?? ordered[0].confidence
            return TraceTextHit(text: cleaned, confidence: confidence, box: mergedBox)
        }

        return filterSubsumedTextHits(mergedLines)
    }

    func belongsToSameTextLine(_ hit: TraceTextHit, line: [TraceTextHit]) -> Bool {
        guard let anchor = line.first else { return false }
        let maxHeight = max(hit.box.height, line.map(\.box.height).max() ?? hit.box.height)
        let verticalThreshold = max(0.02, maxHeight * 0.75)
        return abs(hit.box.midY - anchor.box.midY) <= verticalThreshold
    }

    func filterSubsumedTextHits(_ hits: [TraceTextHit]) -> [TraceTextHit] {
        hits.filter { hit in
            let key = normalizedOcrKey(hit.text)
            guard !key.isEmpty else { return false }
            return !hits.contains { other in
                guard other.text != hit.text else { return false }
                let otherKey = normalizedOcrKey(other.text)
                guard otherKey.count > key.count else { return false }
                guard otherKey.contains(key) else { return false }
                let overlap = hit.box.intersection(other.box)
                let overlapArea = max(0, overlap.width) * max(0, overlap.height)
                let hitArea = max(0.0001, hit.box.width * hit.box.height)
                return overlapArea / hitArea > 0.35
            }
        }
    }

    func shouldReplaceTextHit(existing: TraceTextHit, candidate: TraceTextHit) -> Bool {
        if ocrTextQuality(candidate.text) != ocrTextQuality(existing.text) {
            return ocrTextQuality(candidate.text) > ocrTextQuality(existing.text)
        }
        if candidate.confidence != existing.confidence {
            return candidate.confidence > existing.confidence
        }
        let candidateArea = candidate.box.width * candidate.box.height
        let existingArea = existing.box.width * existing.box.height
        return candidateArea > existingArea
    }

    func normalizedOcrKey(_ text: String) -> String {
        cleanOcrText(text)
            .lowercased()
            .replacingOccurrences(of: "[^a-z0-9äöüß]+", with: " ", options: .regularExpression)
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    func ocrTextQuality(_ text: String) -> Int {
        let letters = text.filter(\.isLetter).count
        let shortWords = normalizedOcrKey(text)
            .components(separatedBy: .whitespaces)
            .filter { $0.count > 0 && $0.count <= 2 }
            .count
        let dotPenalty = text.components(separatedBy: "...").count - 1
        return max(0, letters - shortWords - (dotPenalty * 12))
    }

    func filterPersonLikeBoxes(_ boxes: [CGRect], textBoxes: [CGRect], minimumArea: CGFloat) -> [CGRect] {
        let textUnion = unionRect(textBoxes)
        return boxes.filter { box in
            let area = max(0, box.width) * max(0, box.height)
            guard area >= minimumArea else { return false }
            guard let textUnion else { return true }
            let overlap = box.intersection(textUnion)
            let overlapArea = max(0, overlap.width) * max(0, overlap.height)
            return overlapArea / max(area, 0.0001) < 0.45
        }
    }

    func compactVisibleText(_ hits: [TraceTextHit], maxCharacters: Int) -> String? {
        let joined = hits
            .sorted {
                if abs($0.box.midY - $1.box.midY) < 0.02 {
                    return $0.box.minX < $1.box.minX
                }
                return $0.box.midY > $1.box.midY
            }
            .map(\.text)
            .joined(separator: " / ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !joined.isEmpty else { return nil }
        if joined.count <= maxCharacters {
            return joined
        }
        let endIndex = joined.index(joined.startIndex, offsetBy: maxCharacters)
        return "\(joined[..<endIndex])..."
    }

    func inferredTextSurfaceObjectLabel(textHits: [TraceTextHit], classificationHits: [TraceClassificationHit]) -> String {
        let visibleText = compactVisibleText(textHits, maxCharacters: 260)?.lowercased() ?? ""
        let classifications = Set(classificationHits.map { $0.label.lowercased() })

        let transitClues = [
            "garching-forschungszentrum",
            "max-planck-campus",
            "walther-meißner",
            "walther-meissner",
            "lichtenbergstr",
            "anna-boyksen",
            "isarstr",
            "boltzmannstr",
            "bus",
            "p+r",
            "u-bahn",
            "s-bahn",
            "bahnhof",
        ]
        if transitClues.contains(where: visibleText.contains) {
            return "transit sign"
        }

        let screenClues = [
            "instagram",
            "wikipedia",
            "views",
            "post",
            "follow",
            "edited",
            "article",
            "archive",
            "featured",
            ".com",
            ".org",
        ]
        let looksLikeScreen = screenClues.contains(where: visibleText.contains)
            || visibleText.range(of: #"\\b\\d{1,2}:\\d{2}\\b"#, options: .regularExpression) != nil
            || classifications.contains("cell phone")
            || classifications.contains("consumer electronics")
            || classifications.contains("machine")
        if looksLikeScreen {
            return "display screen"
        }

        return "text surface"
    }

    func relationSummary(textBoxes: [CGRect], personBoxes: [CGRect], peopleCount: Int, gpsHint: String) -> String {
        let textPosition = dominantFramePosition(for: textBoxes)
        let personPosition = dominantFramePosition(for: personBoxes)
        let textDominance = visualDominance(for: textBoxes)
        let personDominance = visualDominance(for: personBoxes)
        if peopleCount == 0 {
            return "\(textPosition) in visible frame; \(textDominance); \(gpsHint)"
        }

        guard let textBox = unionRect(textBoxes), let personBox = unionRect(personBoxes) else {
            return "\(personPosition); \(personDominance); near visible person; \(gpsHint)"
        }

        let verticalRelation: String
        if textBox.midY > personBox.maxY {
            verticalRelation = "above visible person"
        } else if textBox.maxY < personBox.minY {
            verticalRelation = "below visible person"
        } else {
            verticalRelation = "overlapping/near visible person"
        }

        let countHint = peopleCount > 1 ? "; \(peopleCount) visible people/faces" : ""
        return "\(textPosition), \(textDominance), \(verticalRelation)\(countHint); \(gpsHint)"
    }

    func dominantFramePosition(for boxes: [CGRect]) -> String {
        guard let box = unionRect(boxes) else {
            return "visible frame"
        }
        let vertical: String
        if box.midY > 0.66 {
            vertical = "upper"
        } else if box.midY < 0.33 {
            vertical = "lower"
        } else {
            vertical = "middle"
        }
        let horizontal: String
        if box.midX < 0.33 {
            horizontal = "left"
        } else if box.midX > 0.66 {
            horizontal = "right"
        } else {
            horizontal = "center"
        }
        return "\(vertical) \(horizontal) frame"
    }

    func unionRect(_ boxes: [CGRect]) -> CGRect? {
        guard var result = boxes.first else {
            return nil
        }
        for box in boxes.dropFirst() {
            result = result.union(box)
        }
        return result
    }

    func visualDominance(for boxes: [CGRect]) -> String {
        guard let box = unionRect(boxes) else {
            return "small visible object"
        }
        let area = max(0, box.width) * max(0, box.height)
        if area >= 0.35 {
            return "dominant foreground object"
        }
        if area >= 0.12 {
            return "large visible object"
        }
        if area >= 0.03 {
            return "medium visible object"
        }
        return "small visible object"
    }

    func scenePhase(stableFrameCount: Int, motionScore: Double?) -> String {
        guard let motionScore else {
            return "settling"
        }
        if motionScore > 0.14 {
            return "moving"
        }
        if stableFrameCount >= 3 {
            return "stable"
        }
        return "settling"
    }

    func frameMotion(_ frame: CVImageBuffer, previousFingerprint: [UInt8]?) -> (fingerprint: [UInt8], score: Double?) {
        let fingerprint = frameFingerprint(frame)
        guard let previousFingerprint, previousFingerprint.count == fingerprint.count else {
            return (fingerprint, nil)
        }

        let total = zip(fingerprint, previousFingerprint).reduce(0) { partial, pair in
            partial + abs(Int(pair.0) - Int(pair.1))
        }
        let score = Double(total) / Double(max(1, fingerprint.count * 255))
        return (fingerprint, score)
    }

    func frameFingerprint(_ frame: CVImageBuffer) -> [UInt8] {
        CVPixelBufferLockBaseAddress(frame, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(frame, .readOnly) }

        let planeCount = CVPixelBufferGetPlaneCount(frame)
        let width: Int
        let height: Int
        let rowBytes: Int
        let baseAddress: UnsafeMutableRawPointer?
        let bytesPerPixel: Int

        if planeCount > 0 {
            width = CVPixelBufferGetWidthOfPlane(frame, 0)
            height = CVPixelBufferGetHeightOfPlane(frame, 0)
            rowBytes = CVPixelBufferGetBytesPerRowOfPlane(frame, 0)
            baseAddress = CVPixelBufferGetBaseAddressOfPlane(frame, 0)
            bytesPerPixel = 1
        } else {
            width = CVPixelBufferGetWidth(frame)
            height = CVPixelBufferGetHeight(frame)
            rowBytes = CVPixelBufferGetBytesPerRow(frame)
            baseAddress = CVPixelBufferGetBaseAddress(frame)
            bytesPerPixel = max(1, rowBytes / max(1, width))
        }

        guard let baseAddress, width > 0, height > 0 else {
            return []
        }

        let pointer = baseAddress.assumingMemoryBound(to: UInt8.self)
        var values: [UInt8] = []
        let columns = 12
        let rows = 8
        for row in 0 ..< rows {
            let y = min(height - 1, max(0, row * height / rows))
            for column in 0 ..< columns {
                let x = min(width - 1, max(0, column * width / columns))
                values.append(pointer[y * rowBytes + x * bytesPerPixel])
            }
        }
        return values
    }

    func appendNativeStatusLog(status: String, extra: [String: Any] = [:]) {
        var payload: [String: Any] = [
            "timestamp": ISO8601DateFormatter().string(from: Date()),
            "type": "native_status",
            "status": status,
        ]
        for (key, value) in extra {
            payload[key] = value
        }
        appendNativePayload(payload)
    }

    @MainActor
    func appendNativeTextLog(memory: String, raw: String, source: String, activeLabels: [String]? = nil) {
        let labels = !((activeLabels ?? []).isEmpty)
            ? dedupeLabels(activeLabels ?? [])
            : activeEntityLabels(from: memory)
        let payload: [String: Any] = [
            "timestamp": ISO8601DateFormatter().string(from: Date()),
            "type": "native_inference_result",
            "source": source,
            "source_type": source.lowercased().contains("speech") ? "audio" : "vision",
            "scene_phase": currentScenePhase,
            "motion_score": currentMotionScore ?? NSNull(),
            "location_hint": locationContext.locationMemoryHint,
            "active_entity_labels": labels,
            "memory_text": memory,
            "raw_text": raw,
        ]
        appendNativePayload(payload)
        postPerceptionPacketToHub(payload)
    }

    @MainActor
    func appendContextSnapshot(reason: String, scenePhase: String, motionScore: Double?) {
        let now = Date()
        let facts = activeContextFacts(limit: 30, now: now)
            .map { fact in
                [
                    "text": fact.text,
                    "first_seen": ISO8601DateFormatter().string(from: fact.firstSeen),
                    "last_seen": ISO8601DateFormatter().string(from: fact.lastSeen),
                    "observations": fact.observations,
                    "age_seconds": Int(now.timeIntervalSince(fact.lastSeen)),
                    "active_score": contextFactScore(fact, now: now),
                    "source": fact.source,
                ] as [String : Any]
            }

        appendNativePayload([
            "timestamp": ISO8601DateFormatter().string(from: Date()),
            "type": "native_context_snapshot",
            "reason": reason,
            "scene_phase": scenePhase,
            "motion_score": motionScore ?? NSNull(),
            "fact_count": contextFacts.count,
            "facts": Array(facts),
        ])
    }

    @MainActor
    func appendContextDigest(reason: String, scenePhase: String, motionScore: Double?, locationHint: String) {
        let now = Date()
        let activeFacts = activeContextFacts(limit: 30, now: now)
        guard !activeFacts.isEmpty else { return }

        let stableFacts = activeFacts
            .filter { fact in
                fact.observations >= 3 && now.timeIntervalSince(fact.lastSeen) <= CONTEXT_ACTIVE_SECONDS
            }
            .prefix(12)
        let provisionalFacts = activeFacts
            .filter { fact in
                fact.observations < 3 && now.timeIntervalSince(fact.lastSeen) <= CONTEXT_ACTIVE_SECONDS
            }
            .prefix(8)
        let staleButRememberedFacts = Array(contextFacts.values)
            .filter { fact in
                let age = now.timeIntervalSince(fact.lastSeen)
                return age > CONTEXT_ACTIVE_SECONDS && age <= CONTEXT_STALE_SECONDS
            }
            .sorted { $0.lastSeen > $1.lastSeen }
            .prefix(8)

        let signature = activeFacts
            .prefix(12)
            .map { "\($0.id):\($0.observations):\(Int(now.timeIntervalSince($0.lastSeen) / 15))" }
            .joined(separator: "\n")
        if signature == lastContextDigestSignature && now.timeIntervalSince(lastContextDigestAt) < CONTEXT_DIGEST_SECONDS * 2 {
            return
        }
        lastContextDigestSignature = signature
        lastContextDigestAt = now

        appendNativePayload([
            "timestamp": ISO8601DateFormatter().string(from: now),
            "type": "native_context_digest",
            "reason": reason,
            "scene_phase": scenePhase,
            "motion_score": motionScore ?? NSNull(),
            "location_hint": locationHint,
            "active_fact_count": activeFacts.count,
            "stable_facts": stableFacts.map { digestFactPayload($0, now: now) },
            "provisional_facts": provisionalFacts.map { digestFactPayload($0, now: now) },
            "stale_but_remembered_facts": staleButRememberedFacts.map { digestFactPayload($0, now: now) },
        ])
    }

    func digestFactPayload(_ fact: TraceContextFact, now: Date) -> [String: Any] {
        [
            "text": fact.text,
            "first_seen": ISO8601DateFormatter().string(from: fact.firstSeen),
            "last_seen": ISO8601DateFormatter().string(from: fact.lastSeen),
            "observations": fact.observations,
            "age_seconds": Int(now.timeIntervalSince(fact.lastSeen)),
            "source": fact.source,
        ]
    }

    func appendNativePayload(_ payload: [String: Any]) {
        let fileManager = FileManager.default
        let logURL = nativeLogURL()
        let directoryURL = logURL.deletingLastPathComponent()

        do {
            try fileManager.createDirectory(at: directoryURL, withIntermediateDirectories: true)
            let data = try JSONSerialization.data(withJSONObject: payload)
            guard var line = String(data: data, encoding: .utf8) else { return }
            line.append("\n")
            let lineData = Data(line.utf8)

            if !fileManager.fileExists(atPath: logURL.path) {
                fileManager.createFile(atPath: logURL.path, contents: nil)
            }

            let handle = try FileHandle(forWritingTo: logURL)
            try handle.seekToEnd()
            try handle.write(contentsOf: lineData)
            try handle.close()
        } catch {
            // Text logging is diagnostic only; live perception should continue if it fails.
        }
    }

    func activeEntityLabels(from memory: String) -> [String] {
        var seen = Set<String>()
        return memory
            .components(separatedBy: .newlines)
            .compactMap { line -> String? in
                let parts = line
                    .components(separatedBy: "|")
                    .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                guard parts.count >= 2, parts[0] == "OBJECT" else { return nil }
                let label = parts[1]
                let key = label.lowercased()
                guard !seen.contains(key) else { return nil }
                seen.insert(key)
                return label
            }
    }

    func derivedActiveEntityLabels(
        memory: String,
        textSurfaceLabel: String?,
        peopleCount: Int,
        classificationHits: [TraceClassificationHit]
    ) -> [String] {
        var labels = activeEntityLabels(from: memory)
        if peopleCount == 1 {
            labels.append("visible person")
        } else if peopleCount > 1 {
            labels.append("visible people")
            labels.append("background person")
        }
        if let textSurfaceLabel, !textSurfaceLabel.isEmpty {
            labels.append(textSurfaceLabel)
        }
        for hit in classificationHits {
            labels.append(hit.label)
        }
        return dedupeLabels(labels)
    }

    func dedupeLabels(_ labels: [String]) -> [String] {
        var seen = Set<String>()
        return labels.compactMap { label in
            let cleaned = label.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !cleaned.isEmpty else { return nil }
            let key = cleaned.lowercased()
            guard !seen.contains(key) else { return nil }
            seen.insert(key)
            return cleaned
        }
    }

    // TESTING ONLY — see the comment on `debugFramesEnabled`. Throttled to ~1/sec,
    // downscaled, and double-gated (app toggle + Mac's TRACE_DEBUG_FRAMES). Lets the
    // operator view what the camera actually captured; never part of the product path.
    static let debugCIContext = CIContext()

    // maxDim raised 640 -> 1920: the Mac-side instance pipeline (detector + SAM2 +
    // per-crop VLM) needs readable pixels to lift fine print / brands out of crops.
    // Demo is plugged in + on LAN, so the bandwidth of a 1080p JPEG/sec is a non-issue.
    static func jpegFromBuffer(_ buffer: CVImageBuffer, maxDim: CGFloat = 1920) -> Data? {
        let ci = CIImage(cvImageBuffer: buffer)
        let longest = max(ci.extent.width, ci.extent.height)
        let scale = longest > maxDim ? maxDim / longest : 1
        let scaled = scale < 1 ? ci.transformed(by: CGAffineTransform(scaleX: scale, y: scale)) : ci
        return debugCIContext.jpegRepresentation(
            of: scaled, colorSpace: CGColorSpaceCreateDeviceRGB(), options: [:]
        )
    }

    func sendDebugFrame(_ buffer: CVImageBuffer, frameIndex: Int) async {
        // L1 (spec v3): raw frames never leave the phone. Hard-off regardless of
        // the persisted Settings toggle (older installs stored it as true).
        guard DEBUG_FRAMES_BUILD_ALLOWED else { return }
        struct FrameCtx { let baseURL: String; let pose: [String: Any]; let arkit: [String: Any]; let depthGrid: [String: Any]?; let motion: [String: Any] }
        let ctx: FrameCtx? = await MainActor.run {
            guard debugFramesEnabled else { return nil }
            let pose = PoseStamper.shared.snapshot()
            // Frame supplier: keep SHARP keyframes (emit when motion settles), drop
            // blurry fast-pan frames, and carry the movement signal between them.
            let decision = FrameSupplier.shared.consider(pose: pose)
            guard decision.emit else { return nil }
            // Sharpness gate: drop motion-settled-but-blurry frames (autofocus hunt).
            let sharp = FrameSupplier.shared.sharpness(buffer)
            guard sharp >= FrameSupplier.shared.sharpnessThreshold else { return nil }
            lastDebugFrameAt = Date()
            let base = traceHubURL.isEmpty ? "http://127.0.0.1:8765" : traceHubURL
            return FrameCtx(baseURL: base,
                            pose: pose,
                            arkit: TraceARKitEngine.shared.metadataSnapshot(),
                            depthGrid: TraceARKitEngine.shared.depthGridSnapshot(),
                            motion: ["since_keyframe": decision.motionSinceKeyframe,
                                     "peak": decision.peakMotion,
                                     "step": decision.stepMotion,
                                     "sharpness": sharp])
        }
        guard let ctx,
              let jpeg = Self.jpegFromBuffer(buffer),
              let url = URL(string: "\(ctx.baseURL)/debug/frame") else { return }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("dev-token", forHTTPHeaderField: "X-TRACE-Token")
        // Attach camera pose (yaw/pitch) so the Mac can individuate instances by
        // viewing direction (world-anchored counting). ARKit anchors ride along too
        // when spatial mode is on. Derived numbers only — still no raw media retained.
        var meta: [String: Any] = ["pose": ctx.pose]
        for (k, v) in ctx.arkit { meta[k] = v }
        if let grid = ctx.depthGrid { meta["depth_grid"] = grid }  // world-coord substrate
        meta["motion"] = ctx.motion  // movement signal between keyframes
        req.httpBody = try? JSONSerialization.data(withJSONObject: [
            "moment_id": "live",
            "t": frameIndex,
            "jpeg_b64": jpeg.base64EncodedString(),
            "metadata": meta,
        ])
        _ = try? await URLSession.shared.data(for: req)
    }

    @MainActor
    func postPerceptionPacketToHub(_ payload: [String: Any]) {
        let baseURL = traceHubURL.isEmpty ? "http://127.0.0.1:8765" : traceHubURL
        // Capture v2: every packet carries device pose + battery — day-one
        // insurance for the persistent spatial scene graph (pose rides in
        // metadata so the hub stores it as observation provenance).
        var payload = payload
        var meta = (payload["metadata"] as? [String: Any]) ?? [:]
        let pose = PoseStamper.shared.snapshot()
        if !pose.isEmpty { meta["pose"] = pose }
        let arkitMeta = TraceARKitEngine.shared.metadataSnapshot()
        for (key, value) in arkitMeta {
            meta[key] = value
        }
        meta["battery_pct"] = PoseStamper.batteryPercent
        meta["build"] = BuildStamp.sha
        payload["metadata"] = meta
        guard JSONSerialization.isValidJSONObject(payload),
              let body = try? JSONSerialization.data(withJSONObject: payload) else {
            return
        }
        guard let url = URL(string: "\(baseURL)/capture/perception") else {
            // Bad hub URL (the historic comma-bug class) — never lose the packet
            spoolPerceptionPacket(body)
            return
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("dev-token", forHTTPHeaderField: "X-TRACE-Token")
        request.httpBody = body

        URLSession.shared.dataTask(with: request) { _, response, error in
            // Offline walk or hub down: spool the packet for post-walk replay
            // via scripts/replay_perception_spool.py (M1 capture path).
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            if error != nil || status < 200 || status >= 300 {
                self.spoolPerceptionPacket(body)
            }
            if let error = error {
                // Log error to ndjson so we can diagnose network path without Xcode
                let logEntry: [String: Any] = [
                    "timestamp": ISO8601DateFormatter().string(from: Date()),
                    "type": "hub_post_error",
                    "target_url": url.absoluteString,
                    "error_code": (error as NSError).code,
                    "error_domain": (error as NSError).domain,
                    "error_desc": error.localizedDescription,
                ]
                if let data = try? JSONSerialization.data(withJSONObject: logEntry),
                   var line = String(data: data, encoding: .utf8) {
                    line.append("\n")
                    let logURL = self.nativeLogURL()
                    let dirURL = logURL.deletingLastPathComponent()
                    try? FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
                    if let handle = try? FileHandle(forWritingTo: logURL) {
                        try? handle.seekToEnd()
                        try? handle.write(contentsOf: Data(line.utf8))
                        try? handle.close()
                    }
                }
            }
        }.resume()
    }

    @MainActor
    func postSceneStateToHub(scenePhase: String, motionScore: Double?, locationHint: String) {
        let payload: [String: Any] = [
            "timestamp": ISO8601DateFormatter().string(from: Date()),
            "type": "native_scene_state",
            "source": "native_vision_state",
            "source_type": "vision",
            "scene_phase": scenePhase,
            "motion_score": motionScore ?? NSNull(),
            "location_hint": locationHint,
            "active_entity_labels": [],
            "store_legacy": false,
            "memory_text": "EVENT | scene visibility | no reliable object/event currently visible | visible frame; \(locationHint) | likely",
        ]
        postPerceptionPacketToHub(payload)
    }

    func nativeLogURL() -> URL {
        let fileManager = FileManager.default
        let baseURL = fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? fileManager.temporaryDirectory
        return baseURL
            .appendingPathComponent("Trace", isDirectory: true)
            .appendingPathComponent("trace_native_text.ndjson")
    }

    /// Serializes spool appends — perception packets and their network
    /// callbacks arrive concurrently.
    static let spoolQueue = DispatchQueue(label: "de.zer00.trace.perception-spool")

    func spoolPerceptionPacket(_ body: Data) {
        let url = nativeLogURL()
            .deletingLastPathComponent()
            .appendingPathComponent("perception_spool.ndjson")
        Self.spoolQueue.async {
            let fileManager = FileManager.default
            try? fileManager.createDirectory(
                at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
            if !fileManager.fileExists(atPath: url.path) {
                fileManager.createFile(atPath: url.path, contents: nil)
            }
            guard let handle = try? FileHandle(forWritingTo: url) else { return }
            try? handle.seekToEnd()
            try? handle.write(contentsOf: body)
            try? handle.write(contentsOf: Data("\n".utf8))
            try? handle.close()
        }
    }
}

// MARK: - Hub Setup

#if os(iOS)
struct TraceHubSetupView: View {
    @Binding var hubURL: String
    @State private var ipInput: String = ""
    @AppStorage("traceDebugFrames") private var debugFramesEnabled = true
    @AppStorage("spatialMode") private var spatialMode = false
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("192.168.x.x", text: $ipInput)
                        .keyboardType(.decimalPad)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                } header: {
                    Text("Mac Hub IP Address")
                } footer: {
                    Text("Run `ipconfig getifaddr en0` on your Mac to find the LAN IP. Hub listens on port 8765. Both devices must be on the same Wi-Fi network.")
                }

                if !hubURL.isEmpty {
                    Section("Connected to") {
                        Text(hubURL)
                            .foregroundStyle(.secondary)
                            .font(.footnote.monospaced())
                    }
                }

                Section {
                    Toggle("Send debug frames to Mac", isOn: $debugFramesEnabled)
                } header: {
                    Text("Testing")
                } footer: {
                    Text("TESTING ONLY: streams ~1 downscaled JPEG/sec to the Mac so the operator can see what the camera saw while debugging. Not part of the product — turn off when done.")
                }

                Section {
                    Toggle("Spatial mode (ARKit)", isOn: $spatialMode)
                } header: {
                    Text("Spatial")
                } footer: {
                    Text("EXPERIMENTAL: ARKit owns the camera for world tracking + per-object world anchors (enables true counting). Restart the app after toggling. If the view misbehaves, turn this OFF to return to the standard camera.")
                }
            }
            .navigationTitle("Trace Hub Setup")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        let trimmed = ipInput.trimmingCharacters(in: .whitespacesAndNewlines)
                        if !trimmed.isEmpty {
                            hubURL = "http://\(trimmed):8765"
                        }
                        dismiss()
                    }
                    .fontWeight(.bold)
                    .disabled(ipInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
            .onAppear {
                if hubURL.hasPrefix("http://") {
                    ipInput = hubURL
                        .replacingOccurrences(of: "http://", with: "")
                        .components(separatedBy: ":").first ?? ""
                }
            }
        }
    }
}

#endif // os(iOS) — TraceHubSetupView

#Preview {
    ContentView()
}

// ── TRACE brain client ────────────────────────────────────────────────────── //
// Talks to the Mac brain (scripts/trace_brain_server.py) over the LAN. The phone
// already live-streams perception to /capture/perception; this asks /ask about
// the rolling "live" moment and gets a cited, honest-or-answered reply.
enum BrainClient {
    struct Citation: Decodable { let t: Double?; let label: String? }
    struct AskResult: Decodable {
        let answer: String
        let source: String?
        let refused: Bool?
        let citations: [Citation]?
        let model: String?
    }

    static func ask(base: String, question: String, allowFrontier: Bool) async throws -> AskResult {
        let trimmed = base.hasSuffix("/") ? String(base.dropLast()) : base
        guard let url = URL(string: trimmed + "/ask") else { throw URLError(.badURL) }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("dev-token", forHTTPHeaderField: "X-TRACE-Token")
        req.timeoutInterval = 180
        req.httpBody = try JSONSerialization.data(withJSONObject: [
            "moment_id": "live",
            "question": question,
            "allow_frontier": allowFrontier,
        ])
        let (data, _) = try await URLSession.shared.data(for: req)
        return try JSONDecoder().decode(AskResult.self, from: data)
    }

    /// Lightweight reachability probe against GET /health. Returns true only on a
    /// 200 from the brain; any error/timeout is treated as not connected.
    static func isHealthy(base: String) async -> Bool {
        let trimmed = base.hasSuffix("/") ? String(base.dropLast()) : base
        guard !trimmed.isEmpty, let url = URL(string: trimmed + "/health") else { return false }
        var req = URLRequest(url: url)
        req.httpMethod = "GET"
        req.setValue("dev-token", forHTTPHeaderField: "X-TRACE-Token")
        req.timeoutInterval = 4
        do {
            let (_, response) = try await URLSession.shared.data(for: req)
            return (response as? HTTPURLResponse)?.statusCode == 200
        } catch {
            return false
        }
    }
}
