from __future__ import annotations

import unittest

from soma_perception.memory import MemoryEmitter
from soma_perception.models import TrackState


class SomaPerceptionTests(unittest.TestCase):
    def test_memory_emitter_includes_detector_spatial_grounding(self) -> None:
        emitter = MemoryEmitter()
        track = TrackState(
            track_id=7,
            label="person",
            color="gray",
            confidence=0.83,
            bbox_xyxy=(10, 20, 200, 380),
            first_seen_utc="2026-06-05T10:00:00+00:00",
            last_seen_utc="2026-06-05T10:00:02+00:00",
            seen_count=4,
            frame_position="middle center frame",
            area_ratio=0.22,
        )

        events = emitter.events_from_tracks([track])

        self.assertEqual(len(events), 1)
        self.assertIn("OBJECT | visible person", events[0].summary_text)
        self.assertIn("middle center frame", events[0].summary_text)
        self.assertIn("large visible object", events[0].summary_text)
        self.assertNotIn("tracked for", events[0].summary_text)

    def test_memory_emitter_deduplicates_unchanged_track_summary(self) -> None:
        emitter = MemoryEmitter()
        track = TrackState(
            track_id=9,
            label="bottle",
            color="blue",
            confidence=0.74,
            bbox_xyxy=(10, 20, 60, 150),
            first_seen_utc="2026-06-05T10:00:00+00:00",
            last_seen_utc="2026-06-05T10:00:02+00:00",
            seen_count=4,
            frame_position="lower right frame",
            area_ratio=0.04,
        )

        first = emitter.events_from_tracks([track])
        second = emitter.events_from_tracks([track])

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])

    def test_memory_emitter_ignores_seen_count_only_changes(self) -> None:
        emitter = MemoryEmitter()
        first_track = TrackState(
            track_id=11,
            label="person",
            color="gray",
            confidence=0.80,
            bbox_xyxy=(10, 20, 200, 380),
            first_seen_utc="2026-06-05T10:00:00+00:00",
            last_seen_utc="2026-06-05T10:00:02+00:00",
            seen_count=4,
            frame_position="middle center frame",
            area_ratio=0.22,
        )
        later_same_track = TrackState(
            track_id=11,
            label="person",
            color="gray",
            confidence=0.81,
            bbox_xyxy=(12, 22, 202, 382),
            first_seen_utc="2026-06-05T10:00:00+00:00",
            last_seen_utc="2026-06-05T10:00:10+00:00",
            seen_count=12,
            frame_position="middle center frame",
            area_ratio=0.23,
        )
        moved_track = TrackState(
            track_id=11,
            label="person",
            color="gray",
            confidence=0.82,
            bbox_xyxy=(260, 20, 420, 380),
            first_seen_utc="2026-06-05T10:00:00+00:00",
            last_seen_utc="2026-06-05T10:00:16+00:00",
            seen_count=18,
            frame_position="middle right frame",
            area_ratio=0.20,
        )

        self.assertEqual(len(emitter.events_from_tracks([first_track])), 1)
        self.assertEqual(emitter.events_from_tracks([later_same_track]), [])
        moved = emitter.events_from_tracks([moved_track])
        self.assertEqual(len(moved), 1)
        self.assertIn("middle right frame", moved[0].summary_text)


if __name__ == "__main__":
    unittest.main()
