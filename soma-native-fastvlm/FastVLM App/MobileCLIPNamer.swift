#if os(iOS)
import CoreML
import Foundation
import ImageIO
import Vision

struct MobileCLIPPrediction {
    let word: String
    let score: Float
    let margin: Float
    let accepted: Bool
}

final class MobileCLIPNamer: @unchecked Sendable {
    static let shared = MobileCLIPNamer()

    private struct VocabEntry {
        let word: String
        let vector: [Float]
    }

    private let vnModel: VNCoreMLModel?
    private let vocab: [VocabEntry]

    private init(
        scoreFloor: Float = 0.22,
        marginFloor: Float = 0.008
    ) {
        UserDefaults.standard.register(defaults: [
            "mobileclipScoreFloor": scoreFloor,
            "mobileclipMarginFloor": marginFloor,
        ])
        if let url = Bundle.main.url(forResource: "mobileclip_s0_image", withExtension: "mlmodelc"),
           let mlModel = try? MLModel(contentsOf: url) {
            self.vnModel = try? VNCoreMLModel(for: mlModel)
        } else {
            self.vnModel = nil
        }
        self.vocab = Self.loadVocab()
    }

    var isAvailable: Bool {
        vnModel != nil && !vocab.isEmpty
    }

    private(set) lazy var vocabWords: Set<String> = Set(vocab.map { $0.word.lowercased() })

    var status: String {
        if vnModel == nil {
            return "MobileCLIP image model missing"
        }
        if vocab.isEmpty {
            return "MobileCLIP vocab missing"
        }
        return "MobileCLIP S0 ready (\(vocab.count) words)"
    }

    private var scoreFloor: Float {
        let value = UserDefaults.standard.double(forKey: "mobileclipScoreFloor")
        guard value.isFinite, value > 0 else { return 0.22 }
        return Float(value)
    }

    private var marginFloor: Float {
        let value = UserDefaults.standard.double(forKey: "mobileclipMarginFloor")
        guard value.isFinite, value >= 0 else { return 0.008 }
        return Float(value)
    }

    func name(crop: CVPixelBuffer) -> MobileCLIPPrediction? {
        name(frame: crop, regionOfInterest: CGRect(x: 0, y: 0, width: 1, height: 1), orientation: .up)
    }

    func name(
        frame: CVImageBuffer,
        regionOfInterest: CGRect,
        orientation: CGImagePropertyOrientation = .right
    ) -> MobileCLIPPrediction? {
        guard let prediction = classify(frame: frame, regionOfInterest: regionOfInterest, orientation: orientation),
              prediction.accepted else {
            return nil
        }
        return prediction
    }

    func classify(
        frame: CVImageBuffer,
        regionOfInterest: CGRect,
        orientation: CGImagePropertyOrientation = .right
    ) -> MobileCLIPPrediction? {
        classify(frame: frame, regionOfInterests: [regionOfInterest], orientation: orientation).first ?? nil
    }

    func classify(
        frame: CVImageBuffer,
        regionOfInterests: [CGRect],
        orientation: CGImagePropertyOrientation = .right
    ) -> [MobileCLIPPrediction?] {
        guard let vnModel, !vocab.isEmpty else {
            return Array(repeating: nil, count: regionOfInterests.count)
        }
        guard !regionOfInterests.isEmpty else { return [] }
        let requests = regionOfInterests.map { roi -> VNCoreMLRequest in
            let request = VNCoreMLRequest(model: vnModel)
            request.preferBackgroundProcessing = false
            request.imageCropAndScaleOption = .scaleFill
            request.regionOfInterest = Self.clamped(roi)
            return request
        }

        let handler = VNImageRequestHandler(
            cvPixelBuffer: frame,
            orientation: orientation,
            options: [:]
        )
        do {
            try handler.perform(requests)
        } catch {
            return Array(repeating: nil, count: regionOfInterests.count)
        }

        return requests.map { request in
            guard let observation = (request.results as? [VNCoreMLFeatureValueObservation])?.first,
                  let array = observation.featureValue.multiArrayValue else {
                return nil
            }
            return match(imageEmbedding: Self.normalized(array))
        }
    }

    private func match(imageEmbedding: [Float]) -> MobileCLIPPrediction? {
        guard imageEmbedding.count == 512 else { return nil }
        var bestWord = ""
        var bestScore = -Float.greatestFiniteMagnitude
        var runnerUp = -Float.greatestFiniteMagnitude

        for entry in vocab {
            let score = dot(imageEmbedding, entry.vector)
            if score > bestScore {
                runnerUp = bestScore
                bestScore = score
                bestWord = entry.word
            } else if score > runnerUp {
                runnerUp = score
            }
        }

        let margin = bestScore - runnerUp
        return MobileCLIPPrediction(
            word: bestWord,
            score: bestScore,
            margin: margin,
            accepted: bestScore >= scoreFloor && margin >= marginFloor
        )
    }

    private func dot(_ lhs: [Float], _ rhs: [Float]) -> Float {
        var total: Float = 0
        for idx in 0..<min(lhs.count, rhs.count) {
            total += lhs[idx] * rhs[idx]
        }
        return total
    }

    private static func loadVocab() -> [VocabEntry] {
        guard let url = Bundle.main.url(forResource: "vocab_embeddings", withExtension: "json"),
              let data = try? Data(contentsOf: url),
              let raw = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return []
        }

        let wordPayload: [String: Any]
        if let nested = raw["words"] as? [String: Any] {
            wordPayload = nested
        } else {
            wordPayload = raw
        }

        return wordPayload.compactMap { key, value in
            guard let vector = floatVector(from: value), vector.count == 512 else {
                return nil
            }
            return VocabEntry(word: key, vector: vector)
        }
        .sorted { $0.word < $1.word }
    }

    private static func floatVector(from value: Any) -> [Float]? {
        guard let rawValues = value as? [Any] else { return nil }
        var floats: [Float] = []
        floats.reserveCapacity(rawValues.count)
        for raw in rawValues {
            if let number = raw as? NSNumber {
                floats.append(number.floatValue)
            } else if let double = raw as? Double {
                floats.append(Float(double))
            } else {
                return nil
            }
        }
        return floats
    }

    private static func normalized(_ array: MLMultiArray) -> [Float] {
        let count = array.count
        var values = [Float](repeating: 0, count: count)
        switch array.dataType {
        case .float32:
            let ptr = array.dataPointer.bindMemory(to: Float32.self, capacity: count)
            for idx in 0..<count { values[idx] = ptr[idx] }
        case .float64:
            let ptr = array.dataPointer.bindMemory(to: Double.self, capacity: count)
            for idx in 0..<count { values[idx] = Float(ptr[idx]) }
        default:
            for idx in 0..<count { values[idx] = array[idx].floatValue }
        }

        let norm = sqrtf(values.reduce(Float(0)) { $0 + $1 * $1 })
        guard norm > 0 else { return values }
        return values.map { $0 / norm }
    }

    private static func clamped(_ rect: CGRect) -> CGRect {
        let minX = max(0, min(1, rect.minX))
        let minY = max(0, min(1, rect.minY))
        let maxX = max(minX, min(1, rect.maxX))
        let maxY = max(minY, min(1, rect.maxY))
        let width = max(0.01, maxX - minX)
        let height = max(0.01, maxY - minY)
        return CGRect(x: minX, y: minY, width: width, height: height)
    }
}
#endif
