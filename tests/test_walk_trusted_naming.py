from __future__ import annotations

import unittest
from unittest.mock import patch

from scripts.walk_name_objects import name_records, parse_gemma_answer
from scripts.walk_fuse_world import fuse_world
from scripts.walk_build_inventory import cluster


class WalkTrustedNamingTests(unittest.TestCase):
    def test_gemma_answer_parser_is_conservative(self) -> None:
        self.assertEqual(parse_gemma_answer("YES", "keyboard"), ("keyboard", "confirmed"))
        self.assertEqual(parse_gemma_answer("NAME: corkboard", "bedpan"), ("corkboard", "named"))
        self.assertEqual(parse_gemma_answer("NONE", "razorblade"), (None, "none"))
        self.assertEqual(parse_gemma_answer("background itself", "desk"), (None, "none"))

    def test_name_records_tiers_and_fuse_drops_rejected_positions(self) -> None:
        records = [
            {"word": "keyboard", "score": 0.9, "crop_path": "/tmp/k.jpg", "frame": "frame_000000_0.0s.jpg", "box": [300, 410, 340, 450]},
            {"word": "bedpan", "score": 0.9, "crop_path": "/tmp/b.jpg", "frame": "frame_000000_0.0s.jpg", "box": [300, 410, 340, 450]},
            {"word": "razorblade", "score": 0.9, "crop_path": "/tmp/r.jpg", "frame": "frame_000000_0.0s.jpg", "box": [300, 410, 340, 450]},
        ]
        answers = {"keyboard": "YES", "bedpan": "NAME: cabinet", "razorblade": "NONE"}

        with patch("os.path.exists", return_value=True):
            named, stats = name_records(records, lambda _record, _path, clip: answers[clip], score_floor=0.28, progress_every=0)

        self.assertEqual(stats["trusted_records"], 2)
        self.assertEqual(named[0]["name_source"], "clip_agreed")
        self.assertEqual(named[1]["word"], "cabinet")
        self.assertEqual(named[1]["name_source"], "gemma_named")
        self.assertEqual(named[2]["trust"], "rejected")

        inventory = cluster(named, score_floor=0.22)
        world = fuse_world(
            inventory,
            named,
            [{"file": "frame_000000_0.0s.jpg", "t": 0.0}],
            [
                {
                    "t": 0.0,
                    "intrinsics": [500.0, 0.0, 0.0, 0.0, 500.0, 0.0, 320.0, 240.0, 1.0],
                    "transform": [
                        1.0, 0.0, 0.0, 0.0,
                        0.0, 1.0, 0.0, 0.0,
                        0.0, 0.0, 1.0, 0.0,
                        0.0, 1.5, 0.0, 1.0,
                    ],
                }
            ],
        )
        by_label = {obj["label"]: obj for obj in world["objects"]}
        self.assertEqual(by_label["keyboard"]["trust"], "trusted")
        self.assertIsNotNone(by_label["keyboard"]["x"])
        self.assertEqual(by_label["cabinet"]["trust"], "trusted")
        self.assertEqual(by_label["razorblade"]["trust"], "rejected")
        self.assertIsNone(by_label["razorblade"]["x"])


if __name__ == "__main__":
    unittest.main()
