//
// For licensing see accompanying LICENSE file.
// Copyright (C) 2025 Apple Inc. All Rights Reserved.
//

import AVFoundation
import Foundation
import MLXLMCommon
import SwiftUI
import Video
import Vision

// support swift 6
extension CVImageBuffer: @unchecked @retroactive Sendable {}
extension CMSampleBuffer: @unchecked @retroactive Sendable {}

// Continuous mode is Vision-first. FastVLM stays available as a slower semantic backup.
let VISION_FRAME_DELAY = Duration.milliseconds(650)
let ENABLE_STABLE_VLM_REFRESH = false
let ENABLE_TEXT_OCR_MEMORY = false
let ENABLE_OCR_STILL_PASS = false
let ENABLE_IMAGE_CLASSIFICATION_MEMORY = false
let ENABLE_LOCAL_DETECTOR_MEMORY = false
let STABLE_VLM_REFRESH_SECONDS: TimeInterval = 45
let ENABLE_PERSON_VLM_ENRICHMENT = false
let PERSON_VLM_ENRICHMENT_COOLDOWN: TimeInterval = 30
let MEMORY_COMMIT_DEDUP_SECONDS: TimeInterval = 10
let CONTEXT_SNAPSHOT_SECONDS: TimeInterval = 8
let CONTEXT_DIGEST_SECONDS: TimeInterval = 20
let CONTEXT_ACTIVE_SECONDS: TimeInterval = 90
let CONTEXT_STALE_SECONDS: TimeInterval = 1_800

struct SomaContextFact: Identifiable {
    let id: String
    var text: String
    var firstSeen: Date
    var lastSeen: Date
    var observations: Int
    var source: String
}

struct SomaTextHit {
    let text: String
    let confidence: Float
    let box: CGRect
}

struct SomaTextRecognitionResult {
    let observations: [VNRecognizedTextObservation]
    let orientationsWithHits: [String]
}

struct SomaClassificationHit {
    let label: String
    let confidence: Float
}

struct SomaPerceptionRecord {
    let memory: String
    let activeLabels: [String]
}

struct ContentView: View {
    @State private var camera = CameraController()
    @State private var model = FastVLMModel()
    @StateObject private var audioContext = SomaAudioContextEngine()
    @StateObject private var locationContext = SomaLocationContextEngine()
    @StateObject private var detectorBridge = SomaDetectorBridge()

    /// stream of frames -> VideoFrameView, see distributeVideoFrames
    @State private var framesToDisplay: AsyncStream<CVImageBuffer>?

    @State private var prompt = """
        You are SOMA's wearable first-person perception engine.
        Convert the current camera frame into durable text memory.
        Use only this ontology:
        OBJECT | visible entity or body/object attribute | concrete attributes | relation/location if visible | certainty
        EVENT | object/person involved | action/change/state | relation/location if visible | certainty
        """
    @State private var promptSuffix = """
        No prose captions. No categories outside OBJECT and EVENT. Output 2-6 lines only. If uncertain, say uncertain instead of guessing.
        """
    @State private var memoryRecords: [String] = []
    @State private var contextFacts: [String: SomaContextFact] = [:]
    @State private var recentMemorySignatures: [String: Date] = [:]
    @State private var visionStatus = "Native Vision waiting for camera frames"
    @State private var currentScenePhase = "settling"
    @State private var currentMotionScore: Double?
    @State private var lastContextSnapshotAt = Date.distantPast
    @State private var lastContextDigestAt = Date.distantPast
    @State private var lastContextDigestSignature = ""
    @State private var lastSemanticRefreshAt = Date.distantPast
    @State private var lastPersonEnrichmentAt = Date.distantPast
    @State private var lastRawOcrCount = 0
    @State private var lastAcceptedOcrCount = 0
    @State private var lastObjectCount = 0
    @State private var lastFaceCount = 0
    @State private var lastOcrStillAt = Date.distantPast
    @AppStorage(GroundTruthRecorder.toggleKey) private var gtRecordingEnabled = false
    @State private var showSpatialWorld = false
    @State private var lastBodyCount = 0
    @State private var lastAcceptedOcrPreview = ""
    @State private var lastVisionInferenceAt: Date?
    @State private var lastVisionNoRecordAt: Date?

    @State private var isShowingInfo: Bool = false
    @State private var isShowingHubSetup: Bool = false
    @AppStorage("somaHubURL") private var somaHubURL: String = ""
    @State private var isMemoryPaused = false

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
            Form {
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

                promptSections

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

                #if os(macOS)
                Spacer()
                #endif
            }
            
            #if os(iOS)
            .listSectionSpacing(0)
            #elseif os(macOS)
            .padding()
            #endif
            .task {
                appendNativeStatusLog(status: "local_runtime_status", extra: SomaLocalRuntime.statusPayload())
                appendNativeStatusLog(status: "camera_start_requested")
                camera.start()
                locationContext.start()
                audioContext.start()
                if ENABLE_LOCAL_DETECTOR_MEMORY {
                    detectorBridge.start()
                } else {
                    detectorBridge.status = "Detector disabled; FastVLM spatial naming active"
                }
            }
            .onChange(of: detectorBridge.lastMemoryText) { _, memoryText in
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
            .onChange(of: detectorBridge.status) { _, status in
                appendNativeStatusLog(status: "detector_status", extra: [
                    "detector_status": status,
                ])
            }
            .onChange(of: audioContext.lastCommittedTranscript) { _, transcript in
                let cleaned = transcript.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !cleaned.isEmpty, !isMemoryPaused else { return }
                let memory = "EVENT | nearby speech | transcript: \"\(cleaned)\" | \(locationContext.locationMemoryHint) | likely"
                commitMemoryRecord(memory, raw: cleaned, source: "native_speech")
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
            #if !os(macOS)
            .onAppear {
                // Prevent the screen from dimming or sleeping due to inactivity
                UIApplication.shared.isIdleTimerDisabled = true
                migrateAutoOpenCapturePreference()
            }
            .onDisappear {
                // Resumes normal idle timer behavior
                UIApplication.shared.isIdleTimerDisabled = false
            }
            #endif

            // task to distribute video frames -- this will cancel
            // and restart when the view is on/off screen.  note: it is
            // important that this is here (attached to the VideoFrameView)
            // rather than the outer view because this has the correct lifecycle
            .task {
                if Task.isCancelled {
                    return
                }

                appendNativeStatusLog(status: "distribute_video_frames_task_started")
                await distributeVideoFrames()
            }

            .navigationTitle("SOMA POV")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: toolbarItemPlacement) {
                    Button {
                        isShowingInfo.toggle()
                    }
                    label: {
                        Image(systemName: "info.circle")
                    }
                }

                #if os(iOS)
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        isShowingHubSetup.toggle()
                    } label: {
                        Image(systemName: somaHubURL.isEmpty ? "wifi.slash" : "wifi")
                            .foregroundStyle(somaHubURL.isEmpty ? Color.orange : Color.green)
                    }
                }
                // Walk-2 ground-truth recorder: founder-toggled, self-data
                // only; the file is reviewed against the graph afterwards.
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        gtRecordingEnabled.toggle()
                    } label: {
                        Image(systemName: gtRecordingEnabled ? "record.circle.fill" : "record.circle")
                            .foregroundStyle(gtRecordingEnabled ? Color.red : Color.gray)
                    }
                }
                // Genesis-frame spatial mode (words, not polygons). ARKit
                // needs the camera, so normal capture pauses while open.
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        camera.stop()
                        showSpatialWorld = true
                    } label: {
                        Image(systemName: "move.3d")
                            .foregroundStyle(Color.cyan)
                    }
                }
                #endif

                ToolbarItem(placement: .primaryAction) {
                    if isEditingPrompt {
                        Button {
                            isEditingPrompt.toggle()
                        }
                        label: {
                            Text("Done")
                                .fontWeight(.bold)
                        }
                    }
                    else {
                        Menu {
                            Button("SOMA object/event memory") {
                                prompt = """
                                    You are SOMA's wearable first-person perception engine.
                                    Convert the current camera frame into durable text memory.
                                    Use only this ontology:
                                    OBJECT | visible entity or body/object attribute | concrete attributes | relation/location if visible | certainty
                                    EVENT | object/person involved | action/change/state | relation/location if visible | certainty
                                    """
                                promptSuffix = """
                                    No prose captions. No categories outside OBJECT and EVENT. Output 2-6 lines only. If uncertain, say uncertain instead of guessing.
                                    """
                            }
                            Button("Facial expression") {
                                prompt = "What is this person's facial expression?"
                                promptSuffix = "Output only one or two words."
                            }
                            Button("Read text") {
                                prompt = "What is written in this image?"
                                promptSuffix = "Output only the text in the image."
                            }
                            #if !os(macOS)
                            Button("Customize...") {
                                isEditingPrompt.toggle()
                            }
                            #endif
                        } label: { Text("Prompts") }
                    }
                }
            }
            #if os(iOS)
            .fullScreenCover(isPresented: $showSpatialWorld) {
                SpatialWorldView(hubURL: somaHubURL, onClose: { camera.start() })
            }
            #endif
            .sheet(isPresented: $isShowingInfo) {
                InfoView()
            }
            #if os(iOS)
            .sheet(isPresented: $isShowingHubSetup) {
                SomaHubSetupView(hubURL: $somaHubURL)
            }
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
                    && scenePhase == "stable"
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
                if let still = await camera.captureStill() {
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
            camera.attach(continuation: $0)
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

        // set up structured tasks (important -- this means the child tasks
        // are cancelled when the parent is cancelled)
        async let distributeFrames: () = {
            var displayFrameCount = 0
            for await sampleBuffer in frames {
                GroundTruthRecorder.shared.ingest(sampleBuffer)
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
                    // Only send frames for analysis in continuous mode
                    if await selectedCameraType == .continuous {
                        framesToAnalyzeContinuation.yield(frame)
                    }
                }
            }

            // detach from the camera controller and feed to the video view
            await MainActor.run {
                self.framesToDisplay = nil
                self.camera.detatch()
            }

            framesToDisplayContinuation.finish()
            framesToAnalyzeContinuation.finish()
        }()

        // Only analyze frames if in continuous mode
        if selectedCameraType == .continuous {
            async let analyze: () = analyzeVideoFrames(framesToAnalyze)
            await distributeFrames
            await analyze
        } else {
            await distributeFrames
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
        let userInput = UserInput(
            prompt: .text("\(prompt) \(promptSuffix)"),
            images: [.ciImage(CIImage(cvPixelBuffer: frame))]
        )

        // Post request to FastVLM
        Task {
            let task = await model.generate(userInput)
            _ = await task.result
            let memory = cleanSomaRecord(model.output)
            if !memory.isEmpty {
                await MainActor.run {
                    commitMemoryRecord(memory, raw: model.output, source: "fastvlm_manual")
                }
            }
        }
    }

    func runSemanticMemoryRefresh(_ frame: CVImageBuffer, scenePhase: String) async {
        let semanticPrompt = """
            You are SOMA's wearable first-person object/event perception engine.
            Inspect only the current camera frame. Do not use previous memory.
            Write at most 4 plain text memory facts.
            Every line must start exactly with OBJECT | or EVENT |
            Do not print a table, headings, examples, placeholders, or this instruction.
            The camera, photo, picture, image, and act of taking a picture are not memory facts.
            Prefer specific visible objects and readable sign/board text over a general scene caption.
            Mention relation/location only if visible. If nothing is clear, output nothing.
            """

        let userInput = UserInput(
            prompt: .text(semanticPrompt),
            images: [.ciImage(CIImage(cvPixelBuffer: frame))]
        )

        let task = await model.generate(userInput)
        _ = await task.result
        let memory = cleanSomaRecord(model.output)
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

        let userInput = UserInput(
            prompt: .text(enrichPrompt),
            images: [.ciImage(CIImage(cvPixelBuffer: frame))]
        )

        let task = await model.generate(userInput)
        _ = await task.result
        let memory = cleanSomaRecord(model.output)
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
                contextFacts[signature] = SomaContextFact(
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

    func activeContextFacts(limit: Int, now: Date = Date()) -> [SomaContextFact] {
        let facts = Array(contextFacts.values)
        let active = facts.filter { now.timeIntervalSince($0.lastSeen) <= CONTEXT_ACTIVE_SECONDS }
        let candidates = active.isEmpty ? facts : active
        return Array(
            candidates
                .sorted { contextFactScore($0, now: now) > contextFactScore($1, now: now) }
                .prefix(limit)
        )
    }

    func contextFactScore(_ fact: SomaContextFact, now: Date) -> Double {
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

    func factDisplayLine(_ fact: SomaContextFact, now: Date = Date()) -> String {
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

    func cleanSomaRecord(_ text: String) -> String {
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

    func localVisionRecord(_ frame: CVImageBuffer, scenePhase: String, frameIndex: Int, locationHint: String) -> SomaPerceptionRecord {
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
            return SomaPerceptionRecord(memory: "", activeLabels: [])
        }

        var records: [String] = []
        let textRecognition = ENABLE_TEXT_OCR_MEMORY
            ? recognizedTextObservations(frame: frame, scenePhase: scenePhase)
            : SomaTextRecognitionResult(observations: [], orientationsWithHits: [])
        let textObservations = textRecognition.observations
        let humanObservations: [VNHumanObservation] = personRequest.results ?? []
        let faceObservations: [VNFaceObservation] = faceRequest.results ?? []
        let classificationObservations: [VNClassificationObservation] = ENABLE_IMAGE_CLASSIFICATION_MEMORY
            ? (classificationRequest.results ?? [])
            : []

        let rawTextHits = textObservations.compactMap { observation -> SomaTextHit? in
                guard let candidate = observation.topCandidates(1).first else { return nil }
                let text = cleanOcrText(candidate.string)
                guard !text.isEmpty else { return nil }
                return SomaTextHit(text: text, confidence: candidate.confidence, box: observation.boundingBox)
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
            SomaClassificationHit(label: $0.identifier, confidence: $0.confidence)
        }
        var classificationHits = filteredClassificationHits(rawClassificationHits, scenePhase: scenePhase)
        // CoreML object detector (capture v2): localized real objects —
        // bicycle/bench/backpack-class — that scene classification missed.
        // Walking frames get a higher confidence bar (motion blur).
        let objectHits: [DetectedObjectV2] = ObjectDetectorV2.shared.detect(
            frame, minimumConfidence: scenePhase == "moving" ? 0.50 : 0.40
        )
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
            records.append(contentsOf: objectHits.map { obj in
                "OBJECT | visible \(obj.label) | detected | \(frameRelation) | uncertain"
            })
            records.append(contentsOf: classificationMemoryLines(
                classificationHits,
                scenePhase: scenePhase,
                frameRelation: frameRelation,
                peopleCount: peopleCount
            ))
            let memory = records.prefix(8).joined(separator: "\n")
            return SomaPerceptionRecord(
                memory: memory,
                activeLabels: derivedActiveEntityLabels(
                    memory: memory,
                    textSurfaceLabel: textHits.isEmpty ? nil : textSurfaceLabel,
                    peopleCount: peopleCount,
                    classificationHits: classificationHits
                )
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

        records.append(contentsOf: objectHits.map { obj in
            "OBJECT | visible \(obj.label) | detected | \(frameRelation) | \(obj.confidence > 0.6 ? "likely" : "uncertain")"
        })
        records.append(contentsOf: classificationMemoryLines(
            classificationHits,
            scenePhase: scenePhase,
            frameRelation: frameRelation,
            peopleCount: peopleCount
        ))

        let memory = records.prefix(12).joined(separator: "\n")
        return SomaPerceptionRecord(
            memory: memory,
            activeLabels: derivedActiveEntityLabels(
                memory: memory,
                textSurfaceLabel: textHits.isEmpty ? nil : textSurfaceLabel,
                peopleCount: peopleCount,
                classificationHits: classificationHits
            )
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

    func recognizedTextObservations(frame: CVImageBuffer, scenePhase: String) -> SomaTextRecognitionResult {
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

        return SomaTextRecognitionResult(
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

    func filteredClassificationHits(_ hits: [SomaClassificationHit], scenePhase: String) -> [SomaClassificationHit] {
        let threshold: Float = scenePhase == "stable" ? 0.42 : 0.52
        var seen = Set<String>()
        return hits
            .map { hit in
                SomaClassificationHit(label: normalizedClassificationLabel(hit.label), confidence: hit.confidence)
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
        _ hits: [SomaClassificationHit],
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
        _ hit: SomaClassificationHit,
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

    func isLikelySelfFacingArtifact(personBoxes: [CGRect], textHits: [SomaTextHit], classificationHits: [SomaClassificationHit]) -> Bool {
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

    func rejectedOcrSamples(rawTextHits: [SomaTextHit], acceptedTextHits: [SomaTextHit]) -> [String] {
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

    func uniqueTextHits(_ hits: [SomaTextHit]) -> [SomaTextHit] {
        let merged = mergeTextHitsIntoLines(hits)
        var bestByKey: [String: SomaTextHit] = [:]

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

    func mergeTextHitsIntoLines(_ hits: [SomaTextHit]) -> [SomaTextHit] {
        let sorted = hits.sorted {
            if abs($0.box.midY - $1.box.midY) < 0.025 {
                return $0.box.minX < $1.box.minX
            }
            return $0.box.midY > $1.box.midY
        }

        var lines: [[SomaTextHit]] = []
        for hit in sorted {
            if let index = lines.firstIndex(where: { belongsToSameTextLine(hit, line: $0) }) {
                lines[index].append(hit)
            } else {
                lines.append([hit])
            }
        }

        let mergedLines = lines.compactMap { line -> SomaTextHit? in
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
            return SomaTextHit(text: cleaned, confidence: confidence, box: mergedBox)
        }

        return filterSubsumedTextHits(mergedLines)
    }

    func belongsToSameTextLine(_ hit: SomaTextHit, line: [SomaTextHit]) -> Bool {
        guard let anchor = line.first else { return false }
        let maxHeight = max(hit.box.height, line.map(\.box.height).max() ?? hit.box.height)
        let verticalThreshold = max(0.02, maxHeight * 0.75)
        return abs(hit.box.midY - anchor.box.midY) <= verticalThreshold
    }

    func filterSubsumedTextHits(_ hits: [SomaTextHit]) -> [SomaTextHit] {
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

    func shouldReplaceTextHit(existing: SomaTextHit, candidate: SomaTextHit) -> Bool {
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

    func compactVisibleText(_ hits: [SomaTextHit], maxCharacters: Int) -> String? {
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

    func inferredTextSurfaceObjectLabel(textHits: [SomaTextHit], classificationHits: [SomaClassificationHit]) -> String {
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

    func digestFactPayload(_ fact: SomaContextFact, now: Date) -> [String: Any] {
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
        classificationHits: [SomaClassificationHit]
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

    func postPerceptionPacketToHub(_ payload: [String: Any]) {
        let baseURL = somaHubURL.isEmpty ? "http://127.0.0.1:8765" : somaHubURL
        // Capture v2: every packet carries device pose + battery — day-one
        // insurance for the persistent spatial scene graph (pose rides in
        // metadata so the hub stores it as observation provenance).
        var payload = payload
        var meta = (payload["metadata"] as? [String: Any]) ?? [:]
        let pose = PoseStamper.shared.snapshot()
        if !pose.isEmpty { meta["pose"] = pose }
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
        request.setValue("dev-token", forHTTPHeaderField: "X-SOMA-Token")
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
            .appendingPathComponent("SOMA", isDirectory: true)
            .appendingPathComponent("soma_native_text.ndjson")
    }

    /// Serializes spool appends — perception packets and their network
    /// callbacks arrive concurrently.
    static let spoolQueue = DispatchQueue(label: "de.zer00.soma.perception-spool")

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
struct SomaHubSetupView: View {
    @Binding var hubURL: String
    @State private var ipInput: String = ""
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
            }
            .navigationTitle("SOMA Hub Setup")
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

#endif // os(iOS) — SomaHubSetupView

#Preview {
    ContentView()
}
