import AVFoundation
import Combine
import CoreLocation
import Foundation
import Speech

@MainActor
final class TraceAudioContextEngine: NSObject, ObservableObject {
    @Published var status = "Speech idle"
    @Published var liveTranscript = ""
    @Published var lastCommittedTranscript = ""
    @Published var isRunning = false

    private let audioEngine = AVAudioEngine()
    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var recognitionTask: SFSpeechRecognitionTask?
    private var lastCommitAt = Date.distantPast
    private var lastCommittedNormalized = ""
    private var cumulativeCommitted = ""  // raw text already emitted this recognition segment
    private var shouldKeepRunning = false

    // P05 utterance-boundary commits. The old cadence committed a DELTA every fixed 5s of
    // continuous speech, so a spoken sentence was sliced mid-phrase into several memory rows
    // ("Everything I" / "do I do it just for you"). Instead we commit on a NATURAL endpoint:
    // result.isFinal, OR a ~1.2s pause with no new partial (utterance boundary), whichever
    // comes first. A hard ceiling keeps a long monologue committing progressively.
    private static let pausePartialSeconds: TimeInterval = 1.2
    private static let hardCeilingSeconds: TimeInterval = 20
    private var pauseCommitTask: Task<Void, Never>?
    private var segmentStartAt = Date.distantPast  // when the current uncommitted span began
    private var pendingPartial = ""                 // latest partial awaiting a boundary

    // Engine-upgrade spike (P05): iOS 26 SpeechAnalyzer/SpeechTranscriber behind a flag.
    // SFSpeechRecognizer stays the shipped fallback; flip to try the long-form engine.
    static let useSpeechAnalyzerEngine = false
    // Stored untyped so the class needn't be gated to iOS 26; cast inside @available methods.
    private var analyzerBox: AnyObject?          // SpeechAnalyzer
    private var analyzerAppend: ((AVAudioPCMBuffer) -> Void)?  // feeds the analyzer input stream
    private var analyzerFinish: (() -> Void)?    // closes the input stream on teardown
    private var analyzerResultsTask: Task<Void, Never>?
    #if os(macOS)
    private var whisperProcess: Process?
    private var whisperOutputPipe: Pipe?
    private var whisperErrorPipe: Pipe?
    private var whisperBuffer = ""
    #endif

    func start() {
        shouldKeepRunning = true
        guard !isRunning else { return }
        #if os(macOS)
        if startWhisperStreamIfAvailable() {
            return
        }
        #endif
        status = "Requesting speech and microphone permission"

        SFSpeechRecognizer.requestAuthorization { [weak self] speechStatus in
            AVCaptureDevice.requestAccess(for: .audio) { micGranted in
                Task { @MainActor in
                    self?.startIfPermitted(speechStatus: speechStatus, micGranted: micGranted)
                }
            }
        }
    }

    func stop() {
        shouldKeepRunning = false
        pauseCommitTask?.cancel()
        pauseCommitTask = nil
        pendingPartial = ""
        segmentStartAt = Date.distantPast
        if analyzerBox != nil {
            stopAnalyzerEngine()
        }
        #if os(macOS)
        stopWhisperStream(nextStatus: "Speech stopped")
        #endif
        stopAudioSession(nextStatus: "Speech stopped")
    }

    #if os(macOS)
    private func startWhisperStreamIfAvailable() -> Bool {
        guard whisperProcess == nil else { return true }

        let missing = TraceLocalRuntime.missingWhisperRequirements()
        guard missing.isEmpty, let binaryPath = TraceLocalRuntime.whisperStreamBinary else {
            status = "Local Whisper unavailable: \(missing.joined(separator: "; "))"
            return false
        }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: binaryPath)
        process.arguments = [
            "--model", TraceLocalRuntime.asrModel,
            "--language", "en",
            "--step", "3000",
            "--length", "8000",
            "--keep", "400",
            "--max-tokens", "48",
            "--keep-context",
        ]

        let outputPipe = Pipe()
        let errorPipe = Pipe()
        process.standardOutput = outputPipe
        process.standardError = errorPipe

        outputPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let text = String(data: data, encoding: .utf8) else { return }
            Task { @MainActor in
                self?.consumeWhisperOutput(text)
            }
        }

        errorPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let text = String(data: data, encoding: .utf8) else { return }
            Task { @MainActor in
                self?.consumeWhisperStatus(text)
            }
        }

        process.terminationHandler = { [weak self] _ in
            Task { @MainActor in
                guard self?.shouldKeepRunning == true else { return }
                self?.whisperProcess = nil
                self?.isRunning = false
                self?.status = "Whisper stream stopped; restarting"
                self?.restartSoon()
            }
        }

        do {
            try process.run()
            whisperProcess = process
            whisperOutputPipe = outputPipe
            whisperErrorPipe = errorPipe
            isRunning = true
            status = "Listening locally with Whisper; audio is not saved"
            return true
        } catch {
            status = "Whisper stream failed: \(error.localizedDescription)"
            return false
        }
    }

    private func stopWhisperStream(nextStatus: String? = nil) {
        whisperOutputPipe?.fileHandleForReading.readabilityHandler = nil
        whisperErrorPipe?.fileHandleForReading.readabilityHandler = nil
        whisperProcess?.terminate()
        whisperProcess = nil
        whisperOutputPipe = nil
        whisperErrorPipe = nil
        whisperBuffer = ""
        isRunning = false
        if let nextStatus {
            status = nextStatus
        }
    }

    private func consumeWhisperOutput(_ text: String) {
        whisperBuffer.append(text)
        while let newline = whisperBuffer.firstIndex(of: "\n") {
            let line = String(whisperBuffer[..<newline])
            whisperBuffer.removeSubrange(...newline)
            consumeWhisperLine(line)
        }
    }

    private func consumeWhisperLine(_ line: String) {
        let cleaned = cleanWhisperTranscript(line)
        guard !cleaned.isEmpty else { return }
        liveTranscript = cleaned
        commitIfUseful(cleaned, isFinal: false)
        status = "Whisper heard speech locally"
    }

    private func cleanWhisperTranscript(_ line: String) -> String {
        var cleaned = line
            .replacingOccurrences(of: "\u{001B}\\[[0-9;?]*[ -/]*[@-~]", with: " ", options: .regularExpression)
            .replacingOccurrences(of: "\u{001B}", with: " ")
            .replacingOccurrences(of: "\\[[^\\]]+\\]", with: " ", options: .regularExpression)
            .replacingOccurrences(of: "\\([^\\)]+\\)", with: " ", options: .regularExpression)
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)

        while cleaned.hasPrefix(">") {
            cleaned.removeFirst()
            cleaned = cleaned.trimmingCharacters(in: .whitespacesAndNewlines)
        }

        let lower = cleaned.lowercased()
        let blockedPrefixes = [
            "whisper_",
            "main:",
            "init:",
            "ggml_",
            "load_",
            "error:",
            "warning:",
        ]
        guard !blockedPrefixes.contains(where: { lower.hasPrefix($0) }) else {
            return ""
        }
        guard cleaned.range(of: "[a-zA-Z]", options: .regularExpression) != nil else {
            return ""
        }
        return cleaned
    }

    private func consumeWhisperStatus(_ text: String) {
        let cleaned = text
            .components(separatedBy: .newlines)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .last { !$0.isEmpty } ?? ""
        guard !cleaned.isEmpty else { return }

        let lower = cleaned.lowercased()
        if lower.contains("capture") || lower.contains("microphone") || lower.contains("processing") {
            status = String("Whisper local ASR: \(cleaned)".prefix(180))
        }
    }
    #endif

    private func stopAudioSession(nextStatus: String? = nil) {
        audioEngine.stop()
        audioEngine.inputNode.removeTap(onBus: 0)
        recognitionRequest?.endAudio()
        recognitionTask?.cancel()
        recognitionTask = nil
        recognitionRequest = nil
        isRunning = false
        if let nextStatus {
            status = nextStatus
        }
    }

    private func startIfPermitted(speechStatus: SFSpeechRecognizerAuthorizationStatus, micGranted: Bool) {
        guard speechStatus == .authorized else {
            status = "Speech permission not authorized: \(speechStatus.readableDescription)"
            return
        }
        guard micGranted else {
            status = "Microphone permission not authorized"
            return
        }
        guard let recognizer else {
            status = "Speech recognizer unavailable"
            return
        }
        guard recognizer.isAvailable else {
            status = "Speech recognizer currently unavailable"
            return
        }
        guard recognizer.supportsOnDeviceRecognition else {
            status = "On-device speech recognition unavailable on this Mac"
            return
        }

        #if os(iOS)
        // On iOS the microphone hardware stays OFF until an AVAudioSession is
        // configured and activated. Nothing in this app ever did that — in the
        // old mode the AVCapture pipeline warmed the audio route incidentally,
        // but with ARKit owning the camera SFSpeech ran against silence
        // (measured 2026-07-03: founder spoke through a whole walk, zero ASR
        // rows landed). Activate explicitly; ARKit does not use the mic, so
        // there is no ownership conflict.
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playAndRecord, mode: .measurement,
                                    options: [.mixWithOthers, .defaultToSpeaker])
            try session.setActive(true, options: .notifyOthersOnDeactivation)
        } catch {
            status = "Audio session activation failed: \(error.localizedDescription)"
            return
        }
        #endif

        // P05 ENGINE SPIKE: prefer the iOS 26 long-form on-device engine when the flag is set and
        // the OS supports it. SFSpeechRecognizer below stays the fallback. Audio session is already
        // active (both engines need it); the analyzer owns the mic tap on its own.
        if Self.useSpeechAnalyzerEngine {
            if #available(iOS 26.0, *) {
                startAnalyzerEngine()
                return
            } else {
                status = "SpeechAnalyzer requires iOS 26; using SFSpeech fallback"
            }
        }

        recognitionTask?.cancel()
        recognitionTask = nil

        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        request.requiresOnDeviceRecognition = true
        recognitionRequest = request

        let inputNode = audioEngine.inputNode
        let format = inputNode.outputFormat(forBus: 0)
        inputNode.removeTap(onBus: 0)
        inputNode.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak request] buffer, _ in
            request?.append(buffer)
        }

        audioEngine.prepare()
        do {
            try audioEngine.start()
        } catch {
            status = "Microphone start failed: \(error.localizedDescription)"
            return
        }

        isRunning = true
        status = "Listening locally; audio is not saved"

        recognitionTask = recognizer.recognitionTask(with: request) { [weak self] result, error in
            Task { @MainActor in
                self?.handleRecognition(result: result, error: error)
            }
        }
    }

    // P05 ENGINE SPIKE — iOS 26 SpeechAnalyzer/SpeechTranscriber long-form on-device path.
    // Behind `useSpeechAnalyzerEngine`; SFSpeech stays the fallback. Streams mic buffers into a
    // SpeechTranscriber configured for progressive (volatile + final) results, and routes each
    // result through the SAME utterance-boundary commit path as SFSpeech: a finalized segment
    // commits as one row, volatile partials feed the pause/ceiling timer. This keeps L1/L2
    // intact — on-device, verbatim only.
    @available(iOS 26.0, *)
    private func startAnalyzerEngine() {
        let transcriber = SpeechTranscriber(locale: Locale(identifier: "en-US"),
                                            preset: .progressiveTranscription)
        let analyzer = SpeechAnalyzer(modules: [transcriber])
        analyzerBox = analyzer

        // Input stream the mic tap writes into.
        let (stream, continuation) = AsyncStream.makeStream(of: AnalyzerInput.self)
        analyzerAppend = { buffer in continuation.yield(AnalyzerInput(buffer: buffer)) }
        analyzerFinish = { continuation.finish() }

        // Consume results: route volatile vs final through the boundary commit path.
        analyzerResultsTask = Task { @MainActor [weak self] in
            do {
                for try await result in transcriber.results {
                    guard let self else { return }
                    let text = String(result.text.characters)
                        .trimmingCharacters(in: .whitespacesAndNewlines)
                    self.liveTranscript = text
                    if result.isFinal {
                        self.pauseCommitTask?.cancel()
                        self.pauseCommitTask = nil
                        self.commitIfUseful(text, isFinal: true)
                        self.pendingPartial = ""
                        self.segmentStartAt = Date.distantPast
                        self.cumulativeCommitted = ""  // fresh diff baseline per finalized segment
                    } else {
                        self.onPartial(text)
                    }
                }
            } catch {
                self?.status = "SpeechAnalyzer stopped: \(error.localizedDescription)"
                self?.stopAudioSession()
                self?.restartSoon()
            }
        }

        // Ensure the on-device model is present, then start analysis and pump mic buffers in.
        Task { @MainActor [weak self] in
            guard let self else { return }
            do {
                if let reserved = try? await AssetInventory.reserve(locale: Locale(identifier: "en-US")),
                   reserved == false {
                    self.status = "SpeechAnalyzer model unavailable for locale; SFSpeech recommended"
                }
                try await analyzer.start(inputSequence: stream)
            } catch {
                self.status = "SpeechAnalyzer start failed: \(error.localizedDescription)"
                self.stopAnalyzerEngine()
                return
            }

            let inputNode = self.audioEngine.inputNode
            let format = inputNode.outputFormat(forBus: 0)
            inputNode.removeTap(onBus: 0)
            inputNode.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] buffer, _ in
                Task { @MainActor in self?.analyzerAppend?(buffer) }
            }
            self.audioEngine.prepare()
            do {
                try self.audioEngine.start()
            } catch {
                self.status = "Microphone start failed: \(error.localizedDescription)"
                self.stopAnalyzerEngine()
                return
            }
            self.isRunning = true
            self.status = "Listening locally (iOS 26 SpeechAnalyzer); audio is not saved"
        }
    }

    private func stopAnalyzerEngine() {
        analyzerResultsTask?.cancel()
        analyzerResultsTask = nil
        analyzerFinish?()
        analyzerFinish = nil
        analyzerAppend = nil
        analyzerBox = nil
        audioEngine.stop()
        audioEngine.inputNode.removeTap(onBus: 0)
        isRunning = false
    }

    private func handleRecognition(result: SFSpeechRecognitionResult?, error: Error?) {
        if let result {
            let text = result.bestTranscription.formattedString.trimmingCharacters(in: .whitespacesAndNewlines)
            liveTranscript = text

            if result.isFinal {
                // A natural sentence end: commit the whole utterance as ONE row, then reset.
                pauseCommitTask?.cancel()
                pauseCommitTask = nil
                commitIfUseful(text, isFinal: true)
                pendingPartial = ""
                segmentStartAt = Date.distantPast
                status = "Speech segment complete; restarting"
                cumulativeCommitted = ""  // next segment's partials start a fresh diff baseline
                stopAudioSession()
                restartSoon()
            } else {
                onPartial(text)
            }
        }

        if let error {
            let message = error.localizedDescription
            status = "Speech recognition stopped: \(message)"
            // Flush any words captured but not yet past a boundary so the tail isn't lost when
            // the segment tears down (the pause timer would fire after teardown otherwise).
            pauseCommitTask?.cancel()
            pauseCommitTask = nil
            if !pendingPartial.isEmpty {
                commitIfUseful(pendingPartial, isFinal: true)
            }
            pendingPartial = ""
            segmentStartAt = Date.distantPast
            cumulativeCommitted = ""
            stopAudioSession()
            if message.localizedCaseInsensitiveContains("Siri and Dictation are disabled") {
                shouldKeepRunning = false
                status = "Apple Speech blocked: Siri and Dictation are disabled"
            } else {
                restartSoon()
            }
        }
    }

    private func restartSoon() {
        guard shouldKeepRunning else { return }
        Task { @MainActor in
            try? await Task.sleep(for: .seconds(1))
            guard shouldKeepRunning, !isRunning else { return }
            start()
        }
    }

    /// Each new partial: publish it, arm the hard ceiling, and (re)arm a pause timer. As long as
    /// new partials keep arriving the pause timer keeps resetting; when speech stops for
    /// `pausePartialSeconds` the timer fires and commits the span at that natural boundary. If the
    /// span runs past `hardCeilingSeconds` (a long monologue), commit immediately so it lands
    /// progressively instead of one giant row.
    private func onPartial(_ text: String) {
        guard !text.isEmpty else { return }
        if segmentStartAt == Date.distantPast {
            segmentStartAt = Date()
        }
        pendingPartial = text

        if Date().timeIntervalSince(segmentStartAt) >= Self.hardCeilingSeconds {
            pauseCommitTask?.cancel()
            pauseCommitTask = nil
            commitIfUseful(text, isFinal: false)
            // Keep listening; the next words start a fresh span for the ceiling clock.
            segmentStartAt = Date()
            return
        }

        pauseCommitTask?.cancel()
        pauseCommitTask = Task { @MainActor [weak self] in
            try? await Task.sleep(for: .seconds(Self.pausePartialSeconds))
            guard let self, !Task.isCancelled else { return }
            let pending = self.pendingPartial
            guard !pending.isEmpty else { return }
            // Boundary reached: no new partial for the pause window -> commit this utterance.
            self.commitIfUseful(pending, isFinal: false)
            self.segmentStartAt = Date()
        }
    }

    private func commitIfUseful(_ text: String, isFinal: Bool) {
        let normalized = text
            .lowercased()
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard normalized.count >= 12 else { return }
        guard normalized != lastCommittedNormalized else { return }

        // P05: timing is now decided by the caller (isFinal or a detected pause / ceiling), so
        // there is no fixed-interval gate here. A continuous sentence lands as ONE row.

        // M5: emit only the NEW words. SFSpeech partials are CUMULATIVE for the segment, so
        // publishing the whole transcript each commit stored the same speech repeatedly
        // (retrieval then surfaces N near-duplicate rows for one utterance). The delta is
        // the record; the cumulative text is only the baseline for the next diff.
        var emit = text
        if !cumulativeCommitted.isEmpty, text.hasPrefix(cumulativeCommitted) {
            emit = String(text.dropFirst(cumulativeCommitted.count))
                .trimmingCharacters(in: .whitespacesAndNewlines)
        }
        guard emit.count >= 4 else { return }  // nothing new worth a record

        lastCommitAt = Date()
        lastCommittedNormalized = normalized
        cumulativeCommitted = text
        lastCommittedTranscript = emit
    }
}

extension SFSpeechRecognizerAuthorizationStatus {
    var readableDescription: String {
        switch self {
        case .notDetermined:
            return "not determined"
        case .denied:
            return "denied"
        case .restricted:
            return "restricted"
        case .authorized:
            return "authorized"
        @unknown default:
            return "unknown"
        }
    }
}

@MainActor
final class TraceLocationContextEngine: NSObject, ObservableObject, @preconcurrency CLLocationManagerDelegate {
    @Published var status = "Location idle"
    @Published var locationMemoryHint = "GPS unavailable"

    private let manager = CLLocationManager()
    private let geocoder = CLGeocoder()
    private var lastGeocodeAt = Date.distantPast
    private var lastPlaceName = ""

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
        manager.distanceFilter = 25
    }

    func start() {
        guard CLLocationManager.locationServicesEnabled() else {
            status = "Location services disabled"
            locationMemoryHint = "GPS unavailable"
            return
        }
        status = "Requesting location permission"
        manager.requestWhenInUseAuthorization()
        manager.startUpdatingLocation()
    }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        switch manager.authorizationStatus {
        case .authorizedAlways, .authorizedWhenInUse:
            status = "Location available"
            manager.startUpdatingLocation()
        case .denied, .restricted:
            status = "Location permission not authorized"
            locationMemoryHint = "GPS unavailable"
        case .notDetermined:
            status = "Location permission pending"
        @unknown default:
            status = "Location authorization unknown"
            locationMemoryHint = "GPS unavailable"
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let location = locations.last else { return }
        let lat = String(format: "%.5f", location.coordinate.latitude)
        let lon = String(format: "%.5f", location.coordinate.longitude)
        let accuracy = Int(location.horizontalAccuracy)
        let baseHint = "GPS \(lat), \(lon), accuracy ~\(accuracy)m"
        locationMemoryHint = lastPlaceName.isEmpty ? baseHint : "\(baseHint) | \(lastPlaceName)"
        status = lastPlaceName.isEmpty ? "Location \(lat), \(lon)" : "Location \(lastPlaceName)"

        guard Date().timeIntervalSince(lastGeocodeAt) >= 60, !geocoder.isGeocoding else { return }
        lastGeocodeAt = Date()
        geocoder.reverseGeocodeLocation(location) { [weak self] placemarks, _ in
            let placemark = placemarks?.first
            let components = [
                placemark?.name,
                placemark?.locality,
                placemark?.administrativeArea,
                placemark?.country,
            ]
            .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }

            let placeName = Array(NSOrderedSet(array: components)).compactMap { $0 as? String }.joined(separator: ", ")
            Task { @MainActor in
                guard let self, !placeName.isEmpty else { return }
                self.lastPlaceName = placeName
                self.locationMemoryHint = "\(baseHint) | \(placeName)"
                self.status = "Location \(placeName)"
            }
        }
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        status = "Location unavailable: \(error.localizedDescription)"
        locationMemoryHint = "GPS unavailable"
    }
}
