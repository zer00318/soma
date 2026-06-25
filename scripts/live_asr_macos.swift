import AVFoundation
import Foundation
import Speech

final class LiveTranscriber {
    private let audioEngine = AVAudioEngine()
    private let speechRecognizer = SFSpeechRecognizer()
    private let request = SFSpeechAudioBufferRecognitionRequest()
    private var task: SFSpeechRecognitionTask?
    private var lastPrinted = ""

    func run() throws {
        guard let recognizer = speechRecognizer, recognizer.isAvailable else {
            throw NSError(domain: "TRACE", code: 1, userInfo: [NSLocalizedDescriptionKey: "Speech recognizer unavailable"])
        }

        let group = DispatchGroup()
        group.enter()

        SFSpeechRecognizer.requestAuthorization { status in
            guard status == .authorized else {
                fputs("Speech permission not granted: \(status.rawValue)\n", stderr)
                exit(1)
            }

            AVCaptureDevice.requestAccess(for: .audio) { granted in
                guard granted else {
                    fputs("Microphone permission not granted\n", stderr)
                    exit(1)
                }

                DispatchQueue.main.async {
                    do {
                        try self.startRecognition(with: recognizer)
                        group.leave()
                    } catch {
                        fputs("Failed to start live transcription: \(error.localizedDescription)\n", stderr)
                        exit(1)
                    }
                }
            }
        }

        group.wait()
        RunLoop.main.run()
    }

    private func startRecognition(with recognizer: SFSpeechRecognizer) throws {
        request.shouldReportPartialResults = true
        let inputNode = audioEngine.inputNode
        let format = inputNode.outputFormat(forBus: 0)

        inputNode.removeTap(onBus: 0)
        inputNode.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] buffer, _ in
            self?.request.append(buffer)
        }

        audioEngine.prepare()
        try audioEngine.start()

        task = recognizer.recognitionTask(with: request) { [weak self] result, error in
            guard let self else { return }
            if let result {
                let transcript = result.bestTranscription.formattedString.trimmingCharacters(in: .whitespacesAndNewlines)
                if !transcript.isEmpty && transcript != self.lastPrinted {
                    print(transcript)
                    fflush(stdout)
                    self.lastPrinted = transcript
                }
            }

            if let error {
                fputs("Recognition error: \(error.localizedDescription)\n", stderr)
            }
        }
    }
}

do {
    try LiveTranscriber().run()
} catch {
    fputs("Live ASR bridge failed: \(error.localizedDescription)\n", stderr)
    exit(1)
}
