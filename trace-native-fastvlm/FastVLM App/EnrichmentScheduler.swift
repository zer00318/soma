// EnrichmentScheduler.swift
// 1:1 port of trace_perception/scheduler.py — the contract is
// tests/test_enrichment_scheduler.py in the repo root. Any behavior change
// must land in BOTH implementations.
//
// Salience-scored, budget-governed VLM enrichment with a progressive ladder:
// attention depth = knowledge depth. overview -> attributes -> minutiae at
// 8s/24s/72s accumulated dwell, one budget token per level, hard hourly
// ceiling with thermal scale-down.

import Foundation

enum EnrichmentLevel: Int, CaseIterable {
    case overview = 1
    case attributes = 2
    case minutiae = 3

    var detailFocus: String {
        switch self {
        case .overview: return "overview"
        case .attributes: return "attributes"
        case .minutiae: return "minutiae"
        }
    }

    static let maxLevel = 3
}

struct SchedulerTrackView {
    let trackID: String
    let className: String
    let firstSeen: TimeInterval
    let lastSeen: TimeInterval
    var motion: Double = 0.0       // 0 = static scene, 1 = heavy motion/blur
    var enrichedCount: Int = 0     // completed ladder levels
}

struct EnrichmentDecision {
    let trackID: String
    let className: String
    let salience: Double
    let decidedAt: TimeInterval
    let level: Int
    let detailFocus: String
}

/// salience = dwell_progress * (0.6*novelty + 0.4*stability)
/// Dwell GATES multiplicatively; progress is measured against the NEXT
/// ladder level's requirement so freshly-enriched subjects cool down.
final class SalienceScorer {
    static let dwellBaseSeconds = 8.0
    static let dwellEscalation = 3.0

    private let familiarity: (String) -> Double

    init(familiarity: @escaping (String) -> Double) {
        self.familiarity = familiarity
    }

    func requiredDwellSeconds(currentLevel: Int) -> Double {
        Self.dwellBaseSeconds * pow(Self.dwellEscalation, Double(currentLevel))
    }

    func score(_ track: SchedulerTrackView, now: TimeInterval) -> Double {
        if track.enrichedCount >= EnrichmentLevel.maxLevel { return 0.0 }
        let dwellSeconds = max(0.0, now - track.firstSeen)
        let dwell = 1.0 - exp(-dwellSeconds / requiredDwellSeconds(currentLevel: track.enrichedCount))
        let novelty = 1.0 - min(1.0, max(0.0, familiarity(track.className)))
        let stability = 1.0 - min(1.0, max(0.0, track.motion))
        return dwell * (0.6 * novelty + 0.4 * stability)
    }
}

/// Hard hourly ceiling on enrichments, continuous refill. scale() shrinks
/// capacity under thermal/battery pressure and never grants burst credit.
final class TokenBucket {
    private let basePerHour: Double
    private var scaleFactor = 1.0
    private let clock: () -> TimeInterval
    private var capacity: Double
    private var tokens: Double
    private var lastRefill: TimeInterval

    init(perHour: Double, clock: @escaping () -> TimeInterval) {
        precondition(perHour > 0, "perHour must be positive")
        self.basePerHour = perHour
        self.clock = clock
        self.capacity = perHour
        self.tokens = perHour
        self.lastRefill = clock()
    }

    private var perHour: Double { basePerHour * scaleFactor }

    private func refill() {
        let now = clock()
        let elapsed = max(0.0, now - lastRefill)
        lastRefill = now
        tokens = min(capacity, tokens + perHour * elapsed / 3600.0)
    }

    /// 0 < factor <= 1; e.g. 0.5 under .serious thermal state.
    func scale(_ factor: Double) {
        refill()
        scaleFactor = min(1.0, max(0.01, factor))
        capacity = perHour
        tokens = min(tokens, capacity)
    }

    /// Map ProcessInfo.thermalState to a budget scale.
    func applyThermalState(_ state: ProcessInfo.ThermalState) {
        switch state {
        case .nominal: scale(1.0)
        case .fair: scale(0.7)
        case .serious: scale(0.4)
        case .critical: scale(0.1)
        @unknown default: scale(0.5)
        }
    }

    func tryConsume() -> Bool {
        refill()
        if tokens >= 1.0 {
            tokens -= 1.0
            return true
        }
        return false
    }

    var available: Double {
        refill()
        return tokens
    }
}

struct SchedulerStats {
    var observed = 0
    var queued = 0
    var enriched = 0
    var belowThreshold = 0
    var budgetDenied = 0
    var evictedStale = 0
}

/// Decides which tracks earn a VLM call, max-salience first.
/// Host loop contract:
///   scheduler.observe(track)        // every detector tick, per track
///   if let d = scheduler.nextEnrichment() { run VLM at d.detailFocus }
final class EnrichmentScheduler {
    private let budget: TokenBucket
    private let scorer: SalienceScorer
    private let clock: () -> TimeInterval
    private let threshold: Double
    private let staleAfterSeconds: Double
    private var queue: [String: SchedulerTrackView] = [:]
    private(set) var stats = SchedulerStats()

    init(
        budget: TokenBucket,
        scorer: SalienceScorer,
        clock: @escaping () -> TimeInterval,
        threshold: Double = 0.45,
        staleAfterSeconds: Double = 60.0
    ) {
        self.budget = budget
        self.scorer = scorer
        self.clock = clock
        self.threshold = threshold
        self.staleAfterSeconds = staleAfterSeconds
    }

    func observe(_ track: SchedulerTrackView) {
        stats.observed += 1
        queue[track.trackID] = track
    }

    private func evictStale(now: TimeInterval) {
        let stale = queue.filter { now - $0.value.lastSeen > staleAfterSeconds }.map(\.key)
        for key in stale {
            queue.removeValue(forKey: key)
            stats.evictedStale += 1
        }
    }

    func nextEnrichment() -> EnrichmentDecision? {
        let now = clock()
        evictStale(now: now)
        guard !queue.isEmpty else { return nil }

        let scored = queue.values
            .map { (scorer.score($0, now: now), $0) }
            .sorted { $0.0 > $1.0 }
        guard let (salience, best) = scored.first else { return nil }

        if salience < threshold {
            stats.belowThreshold += 1
            return nil
        }
        // Token consumed only when a salient track actually wins.
        guard budget.tryConsume() else {
            stats.budgetDenied += 1
            return nil
        }

        let newLevel = best.enrichedCount + 1
        queue.removeValue(forKey: best.trackID)
        stats.enriched += 1
        stats.queued = queue.count
        let focus = EnrichmentLevel(rawValue: newLevel)?.detailFocus ?? "overview"
        return EnrichmentDecision(
            trackID: best.trackID,
            className: best.className,
            salience: salience,
            decidedAt: now,
            level: newLevel,
            detailFocus: focus
        )
    }
}

/// App-side host for the scheduler: owns track continuity (dwell across
/// frames), per-label familiarity, and the thermal-scaled budget.
/// Person identity is still the session-singleton simplification — the
/// ladder applies per continuous presence (absence > 60s resets dwell).
@MainActor
final class EnrichmentGovernor {
    static let shared = EnrichmentGovernor(perHour: 30)

    private let bucket: TokenBucket
    private let scheduler: EnrichmentScheduler
    private var firstSeen: [String: TimeInterval] = [:]
    private var lastSeen: [String: TimeInterval] = [:]
    private var levels: [String: Int] = [:]
    private var labelEnriched: [String: Int] = [:]
    private let now: () -> TimeInterval = { Date().timeIntervalSince1970 }

    init(perHour: Double) {
        var labelCounts: () -> [String: Int] = { [:] }
        let bucket = TokenBucket(perHour: perHour, clock: { Date().timeIntervalSince1970 })
        self.bucket = bucket
        self.scheduler = EnrichmentScheduler(
            budget: bucket,
            scorer: SalienceScorer(familiarity: { label in
                min(1.0, Double(labelCounts()[label] ?? 0) / 3.0)
            }),
            clock: { Date().timeIntervalSince1970 }
        )
        labelCounts = { [weak self] in self?.labelEnriched ?? [:] }
    }

    /// Call once per analysis tick while the subject is visible.
    /// Returns a decision when this tick earns a (deeper) VLM pass.
    func tick(label: String, motion: Double?) -> EnrichmentDecision? {
        bucket.applyThermalState(ProcessInfo.processInfo.thermalState)
        let t = now()
        // Absence beyond the stale window resets dwell: re-appearance is a
        // new fixation, not a continuation.
        if let seen = lastSeen[label], t - seen > 60 {
            firstSeen[label] = t
            levels[label] = levels[label] ?? 0
        }
        let first = firstSeen[label] ?? t
        firstSeen[label] = first
        lastSeen[label] = t

        scheduler.observe(SchedulerTrackView(
            trackID: label,
            className: label,
            firstSeen: first,
            lastSeen: t,
            motion: min(1.0, max(0.0, motion ?? 0.0)),
            enrichedCount: levels[label] ?? 0
        ))
        guard let decision = scheduler.nextEnrichment() else { return nil }
        levels[label] = decision.level
        labelEnriched[label, default: 0] += 1
        return decision
    }

    var statsDescription: String {
        let s = scheduler.stats
        return "enriched=\(s.enriched) denied=\(s.budgetDenied) below=\(s.belowThreshold) tokens=\(String(format: "%.1f", bucket.available))"
    }
}
