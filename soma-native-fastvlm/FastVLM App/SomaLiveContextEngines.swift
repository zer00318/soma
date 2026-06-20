import AVFoundation
import Combine
import CoreLocation
import Foundation
import Speech

@MainActor
final class SomaAudioContextEngine: NSObject, ObservableObject {
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
    private var shouldKeepRunning = false
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
        #if os(macOS)
        stopWhisperStream(nextStatus: "Speech stopped")
        #endif
        stopAudioSession(nextStatus: "Speech stopped")
    }

    #if os(macOS)
    private func startWhisperStreamIfAvailable() -> Bool {
        guard whisperProcess == nil else { return true }

        let missing = SomaLocalRuntime.missingWhisperRequirements()
        guard missing.isEmpty, let binaryPath = SomaLocalRuntime.whisperStreamBinary else {
            status = "Local Whisper unavailable: \(missing.joined(separator: "; "))"
            return false
        }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: binaryPath)
        process.arguments = [
            "--model", SomaLocalRuntime.asrModel,
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

    private func handleRecognition(result: SFSpeechRecognitionResult?, error: Error?) {
        if let result {
            let text = result.bestTranscription.formattedString.trimmingCharacters(in: .whitespacesAndNewlines)
            liveTranscript = text
            commitIfUseful(text, isFinal: result.isFinal)
            if result.isFinal {
                status = "Speech segment complete; restarting"
                stopAudioSession()
                restartSoon()
            }
        }

        if let error {
            let message = error.localizedDescription
            status = "Speech recognition stopped: \(message)"
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

    private func commitIfUseful(_ text: String, isFinal: Bool) {
        let normalized = text
            .lowercased()
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard normalized.count >= 12 else { return }
        guard normalized != lastCommittedNormalized else { return }

        let now = Date()
        guard isFinal || now.timeIntervalSince(lastCommitAt) >= 5 else { return }

        lastCommitAt = now
        lastCommittedNormalized = normalized
        lastCommittedTranscript = text
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
final class SomaLocationContextEngine: NSObject, ObservableObject, @preconcurrency CLLocationManagerDelegate {
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
