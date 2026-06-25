"""Enrichment scheduler: salience, budget governance, and queue behavior.

Pure-logic tests with a fake clock — these specify the algorithm that will be
ported to Swift, so every behavior here is a contract, not an implementation
detail.
"""
from __future__ import annotations

import unittest

from trace_perception.scheduler import (
    EnrichmentScheduler,
    SalienceScorer,
    TokenBucket,
    TrackView,
)


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def _novel(_: str) -> float:
    return 0.0  # nothing is familiar


def _familiar(_: str) -> float:
    return 1.0  # everything is familiar


def make_scheduler(clock, per_hour=30.0, familiarity=_novel, threshold=0.45):
    return EnrichmentScheduler(
        budget=TokenBucket(per_hour, clock),
        scorer=SalienceScorer(familiarity),
        clock=clock,
        threshold=threshold,
    )


class TestSalience(unittest.TestCase):
    def test_dwell_grows_salience(self) -> None:
        clock = FakeClock()
        scorer = SalienceScorer(_novel)
        track = TrackView("t1", "person", first_seen=clock.t, last_seen=clock.t)
        early = scorer.score(track, clock.t + 0.5)
        late = scorer.score(track, clock.t + 20.0)
        self.assertGreater(late, early)

    def test_familiar_static_object_scores_lower_than_novel(self) -> None:
        clock = FakeClock()
        novel_score = SalienceScorer(_novel).score(
            TrackView("a", "person", clock.t, clock.t), clock.t + 10
        )
        familiar_score = SalienceScorer(_familiar).score(
            TrackView("b", "person", clock.t, clock.t), clock.t + 10
        )
        self.assertGreater(novel_score, familiar_score + 0.3)

    def test_motion_reduces_salience(self) -> None:
        clock = FakeClock()
        scorer = SalienceScorer(_novel)
        steady = scorer.score(TrackView("a", "person", clock.t, clock.t, motion=0.0), clock.t + 10)
        shaky = scorer.score(TrackView("b", "person", clock.t, clock.t, motion=1.0), clock.t + 10)
        self.assertGreater(steady, shaky)

    def test_higher_levels_need_more_dwell(self) -> None:
        clock = FakeClock()
        scorer = SalienceScorer(_novel)
        fresh = TrackView("a", "person", clock.t, clock.t)
        at_level_2 = TrackView("b", "person", clock.t, clock.t, enriched_count=2)
        self.assertGreater(
            scorer.score(fresh, clock.t + 10),
            2.5 * scorer.score(at_level_2, clock.t + 10),
        )

    def test_max_level_scores_zero(self) -> None:
        clock = FakeClock()
        scorer = SalienceScorer(_novel)
        maxed = TrackView("a", "person", clock.t, clock.t, enriched_count=3)
        self.assertEqual(scorer.score(maxed, clock.t + 3600), 0.0)


class TestPasserbyVsFixation(unittest.TestCase):
    def test_brief_passerby_not_enriched_long_dwell_is(self) -> None:
        clock = FakeClock()
        sched = make_scheduler(clock)
        # Passerby: in view 0.5s
        sched.observe(TrackView("passerby", "person", clock.t, clock.t))
        clock.advance(0.5)
        self.assertIsNone(sched.next_enrichment())
        # Same track keeps dwelling for 15s -> fixation
        clock.advance(15.0)
        sched.observe(TrackView("passerby", "person", clock.t - 15.5, clock.t))
        decision = sched.next_enrichment()
        self.assertIsNotNone(decision)
        self.assertEqual(decision.track_id, "passerby")


class TestBudget(unittest.TestCase):
    def test_hard_ceiling_then_refill(self) -> None:
        clock = FakeClock()
        sched = make_scheduler(clock, per_hour=2.0)
        for i in range(2):
            sched.observe(TrackView(f"t{i}", "person", clock.t - 30, clock.t))
            self.assertIsNotNone(sched.next_enrichment(), f"budget should allow call {i}")
        # Third salient track: budget exhausted
        sched.observe(TrackView("t2", "person", clock.t - 30, clock.t))
        self.assertIsNone(sched.next_enrichment())
        self.assertEqual(sched.stats.budget_denied, 1)
        # Half an hour later one token has refilled
        clock.advance(1800)
        sched.observe(TrackView("t2", "person", clock.t - 30, clock.t))
        self.assertIsNotNone(sched.next_enrichment())

    def test_thermal_scale_shrinks_capacity(self) -> None:
        clock = FakeClock()
        bucket = TokenBucket(per_hour=10.0, clock=clock)
        bucket.scale(0.2)  # thermal pressure: 10/h -> 2/h
        self.assertLessEqual(bucket.available, 2.0)

    def test_token_not_wasted_below_threshold(self) -> None:
        clock = FakeClock()
        sched = make_scheduler(clock, per_hour=5.0, familiarity=_familiar)
        # Familiar + zero dwell -> below threshold; must NOT consume budget
        sched.observe(TrackView("t0", "chair", clock.t, clock.t))
        self.assertIsNone(sched.next_enrichment())
        self.assertEqual(sched.stats.below_threshold, 1)
        self.assertEqual(sched.stats.budget_denied, 0)


class TestQueue(unittest.TestCase):
    def test_max_salience_wins_not_fifo(self) -> None:
        clock = FakeClock()
        sched = make_scheduler(clock)
        sched.observe(TrackView("early-shaky", "person", clock.t - 10, clock.t, motion=0.9))
        sched.observe(TrackView("late-steady", "person", clock.t - 10, clock.t, motion=0.0))
        decision = sched.next_enrichment()
        self.assertEqual(decision.track_id, "late-steady")

    def test_stale_track_evicted(self) -> None:
        clock = FakeClock()
        sched = make_scheduler(clock)
        sched.observe(TrackView("gone", "person", clock.t - 30, clock.t))
        clock.advance(120)  # out of view for 2 minutes
        self.assertIsNone(sched.next_enrichment())
        self.assertEqual(sched.stats.evicted_stale, 1)

    def test_enriched_track_leaves_queue(self) -> None:
        clock = FakeClock()
        sched = make_scheduler(clock)
        sched.observe(TrackView("t0", "person", clock.t - 30, clock.t))
        self.assertIsNotNone(sched.next_enrichment())
        self.assertIsNone(sched.next_enrichment())  # queue empty now


class TestProgressiveLadder(unittest.TestCase):
    """Attention depth = knowledge depth: overview -> attributes -> minutiae."""

    def test_sustained_dwell_climbs_levels(self) -> None:
        clock = FakeClock()
        sched = make_scheduler(clock, per_hour=100.0)
        first_seen = clock.t
        track_kwargs = dict(track_id="toy", class_name="teddy bear")

        def observe(enriched: int) -> None:
            sched.observe(TrackView(
                first_seen=first_seen, last_seen=clock.t,
                enriched_count=enriched, **track_kwargs,
            ))

        # ~10s in: first enrichment = overview
        clock.advance(10)
        observe(0)
        d1 = sched.next_enrichment()
        self.assertIsNotNone(d1)
        self.assertEqual((d1.level, d1.detail_focus), (1, "overview"))

        # Immediately after: NOT eligible for level 2 yet
        clock.advance(2)
        observe(1)
        self.assertIsNone(sched.next_enrichment())

        # ~40s total dwell: deeper pass = attributes
        clock.advance(30)
        observe(1)
        d2 = sched.next_enrichment()
        self.assertIsNotNone(d2)
        self.assertEqual((d2.level, d2.detail_focus), (2, "attributes"))

        # ~2.5min total dwell: minutiae (the color peel, the scratch)
        clock.advance(110)
        observe(2)
        d3 = sched.next_enrichment()
        self.assertIsNotNone(d3)
        self.assertEqual((d3.level, d3.detail_focus), (3, "minutiae"))

        # Fully studied: no further enrichment no matter the dwell
        clock.advance(3600)
        observe(3)
        self.assertIsNone(sched.next_enrichment())


if __name__ == "__main__":
    unittest.main()
