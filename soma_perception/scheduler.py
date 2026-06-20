"""Salience-scored, budget-governed VLM enrichment scheduler.

The core "coarse passerby / fine fixation" engine: a cheap always-on detector
feeds track observations in; sparse, expensive VLM enrichment requests come
out, governed by a hard hourly budget so the loop can run all day on phone
hardware.

Pure logic, no I/O, injected clock — unit-testable and portable 1:1 to Swift
(see ops/enrichment_scheduler_design.md). The host loop owns the detector and
the VLM call; this module only decides WHAT is worth enriching and WHEN the
budget allows it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class TrackView:
    """The scheduler's minimal view of a detector track."""

    track_id: str
    class_name: str
    first_seen: float  # clock seconds
    last_seen: float
    motion: float = 0.0  # 0 = static scene, 1 = heavy motion/blur
    enriched_count: int = 0


# Progressive enrichment ladder: attention depth = knowledge depth.
# Each level looks deeper at the same subject; each costs a budget token
# and demands ~3x the accumulated dwell of the previous one.
ENRICHMENT_LEVELS = ("overview", "attributes", "minutiae")
MAX_ENRICHMENT_LEVEL = len(ENRICHMENT_LEVELS)


@dataclass
class EnrichmentDecision:
    track_id: str
    class_name: str
    salience: float
    decided_at: float
    level: int = 1  # 1-based: the level this enrichment will ESTABLISH
    detail_focus: str = "overview"  # ENRICHMENT_LEVELS[level-1]


class SalienceScorer:
    """salience = dwell_progress * (0.6*novelty + 0.4*stability).

    Dwell GATES rather than adds: a brand-new track scores near zero no
    matter how novel, so passersby cannot reach the threshold and burn
    budget — only fixation earns enrichment. (Revised from the additive
    design-doc formula, which let novelty+stability alone clear the bar.)

    dwell_progress is measured against the NEXT enrichment level's dwell
    requirement (8s, 24s, 72s): a freshly-enriched subject scores low again
    until sustained attention justifies a deeper pass — overview first,
    then attributes, then minutiae (the color peel, the scratch). Subjects
    at max level score zero.
    """

    DWELL_BASE_S = 8.0
    DWELL_ESCALATION = 3.0

    def __init__(self, familiarity: Callable[[str], float]) -> None:
        """familiarity(class_name) -> 0..1; 1 = the graph knows this well
        in the current context (e.g. the user's own desk objects)."""
        self._familiarity = familiarity

    def required_dwell_s(self, current_level: int) -> float:
        """Dwell needed to saturate progress toward level current_level+1."""
        return self.DWELL_BASE_S * (self.DWELL_ESCALATION ** current_level)

    def score(self, track: TrackView, now: float) -> float:
        if track.enriched_count >= MAX_ENRICHMENT_LEVEL:
            return 0.0
        dwell_s = max(0.0, now - track.first_seen)
        # Saturating progress toward the next level: ~0.63 at requirement.
        dwell = 1.0 - math.exp(-dwell_s / self.required_dwell_s(track.enriched_count))
        novelty = 1.0 - min(1.0, max(0.0, self._familiarity(track.class_name)))
        stability = 1.0 - min(1.0, max(0.0, track.motion))
        return dwell * (0.6 * novelty + 0.4 * stability)


class TokenBucket:
    """Hard hourly ceiling on enrichments, continuous refill.

    scale() lets the host shrink capacity under thermal/battery pressure
    (ProcessInfo.thermalState on iOS); scaling never grants burst credit.
    """

    def __init__(self, per_hour: float, clock: Callable[[], float]) -> None:
        if per_hour <= 0:
            raise ValueError("per_hour must be positive")
        self._base_per_hour = per_hour
        self._scale = 1.0
        self._clock = clock
        self._capacity = self._per_hour()
        self._tokens = self._per_hour()
        self._last_refill = clock()

    def _per_hour(self) -> float:
        return self._base_per_hour * self._scale

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._last_refill)
        self._last_refill = now
        self._tokens = min(self._capacity, self._tokens + self._per_hour() * elapsed / 3600.0)

    def scale(self, factor: float) -> None:
        """0 < factor <= 1; e.g. 0.5 under serious thermal pressure."""
        self._refill()
        self._scale = min(1.0, max(0.01, factor))
        self._capacity = self._per_hour()
        self._tokens = min(self._tokens, self._capacity)

    def try_consume(self) -> bool:
        self._refill()
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False

    @property
    def available(self) -> float:
        self._refill()
        return self._tokens


@dataclass
class SchedulerStats:
    observed: int = 0
    queued: int = 0
    enriched: int = 0
    below_threshold: int = 0
    budget_denied: int = 0
    evicted_stale: int = 0


class EnrichmentScheduler:
    """Decides which tracks earn a VLM call, max-salience first.

    Host loop contract:
        scheduler.observe(track)            # every detector tick, per track
        decision = scheduler.next_enrichment()
        if decision: run VLM on that track, then observe() continues
    """

    def __init__(
        self,
        budget: TokenBucket,
        scorer: SalienceScorer,
        clock: Callable[[], float],
        threshold: float = 0.45,
        stale_after_s: float = 60.0,
    ) -> None:
        self._budget = budget
        self._scorer = scorer
        self._clock = clock
        self._threshold = threshold
        self._stale_after_s = stale_after_s
        self._queue: dict[str, TrackView] = {}
        self.stats = SchedulerStats()

    def observe(self, track: TrackView) -> None:
        self.stats.observed += 1
        self._queue[track.track_id] = track

    def _evict_stale(self, now: float) -> None:
        stale = [
            tid for tid, t in self._queue.items()
            if now - t.last_seen > self._stale_after_s
        ]
        for tid in stale:
            del self._queue[tid]
            self.stats.evicted_stale += 1

    def next_enrichment(self) -> EnrichmentDecision | None:
        now = self._clock()
        self._evict_stale(now)
        if not self._queue:
            return None

        scored = sorted(
            ((self._scorer.score(t, now), t) for t in self._queue.values()),
            key=lambda pair: pair[0],
            reverse=True,
        )
        salience, best = scored[0]
        if salience < self._threshold:
            self.stats.below_threshold += 1
            return None
        # Token consumed only when a salient track actually wins.
        if not self._budget.try_consume():
            self.stats.budget_denied += 1
            return None

        new_level = best.enriched_count + 1
        best.enriched_count = new_level
        # Track leaves the queue; the host's next observe() re-enters it at
        # the new level, where the steeper dwell requirement applies.
        del self._queue[best.track_id]
        self.stats.enriched += 1
        self.stats.queued = len(self._queue)
        return EnrichmentDecision(
            track_id=best.track_id,
            class_name=best.class_name,
            salience=salience,
            decided_at=now,
            level=new_level,
            detail_focus=ENRICHMENT_LEVELS[new_level - 1],
        )
