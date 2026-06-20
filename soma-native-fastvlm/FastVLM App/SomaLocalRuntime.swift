import Foundation

enum SomaLocalRuntime {
    static let defaultWorkspace = "/Users/zer00/Documents/VLM"

    static var workspace: String {
        let configured = ProcessInfo.processInfo.environment["SOMA_WORKSPACE"]?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return configured?.isEmpty == false ? configured! : defaultWorkspace
    }

    static var detectorPython: String {
        "\(workspace)/.venv/bin/python"
    }

    static var detectorModel: String {
        "\(workspace)/yolo11n.pt"
    }

    static var asrModel: String {
        "\(workspace)/models/asr/ggml-base.en.bin"
    }

    static var whisperStreamBinary: String? {
        firstExistingPath([
            "\(workspace)/tools/whisper-stream",
            "/opt/homebrew/bin/whisper-stream",
            "/usr/local/bin/whisper-stream",
        ])
    }

    static func fileExists(_ path: String) -> Bool {
        FileManager.default.fileExists(atPath: path)
    }

    static func missingDetectorRequirements() -> [String] {
        [
            fileExists(detectorPython) ? nil : "Python venv missing at \(detectorPython)",
            fileExists(detectorModel) ? nil : "YOLO model missing at \(detectorModel)",
        ].compactMap { $0 }
    }

    static func missingWhisperRequirements() -> [String] {
        [
            whisperStreamBinary == nil ? "whisper-stream binary missing" : nil,
            fileExists(asrModel) ? nil : "Whisper model missing at \(asrModel)",
        ].compactMap { $0 }
    }

    static func statusPayload() -> [String: Any] {
        let whisperBinary = whisperStreamBinary ?? "missing"
        let missingDetector = missingDetectorRequirements()
        let missingWhisper = missingWhisperRequirements()

        return [
            "workspace": workspace,
            "detector_python": detectorPython,
            "detector_python_exists": fileExists(detectorPython),
            "detector_model": detectorModel,
            "detector_model_exists": fileExists(detectorModel),
            "whisper_stream": whisperBinary,
            "whisper_stream_exists": whisperStreamBinary != nil,
            "asr_model": asrModel,
            "asr_model_exists": fileExists(asrModel),
            "detector_ready_for_start": missingDetector.isEmpty,
            "whisper_ready_for_start": missingWhisper.isEmpty,
            "missing_detector_requirements": missingDetector,
            "missing_whisper_requirements": missingWhisper,
        ]
    }

    private static func firstExistingPath(_ candidates: [String]) -> String? {
        candidates.first { fileExists($0) }
    }
}
