from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import ask_home
from scripts import build_egomotion_visual as egomotion


class EgomotionIsolationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def artifact(self, clip: str, final_pan: float) -> Path:
        memory = self.root / clip / "memory"
        memory.mkdir(parents=True)
        artifact = memory / "egomotion_visual.json"
        artifact.write_text(json.dumps({
            "schema": "egomotion_visual.v1",
            "track": [
                {"t": 0.0, "cumulative_pan_deg": 0.0, "coherence": 1.0},
                {"t": 10.0, "cumulative_pan_deg": final_pan, "coherence": 1.0},
            ],
        }))
        return artifact

    def test_direction_requires_an_explicit_track_or_artifact(self) -> None:
        with self.assertRaisesRegex(ValueError, "artifact_path is required"):
            egomotion.answer_relative_direction(0.0, 10.0)

    def test_two_artifacts_produce_opposite_answers_without_global_fallback(self) -> None:
        left = self.artifact("left_clip", -30.0)
        right = self.artifact("right_clip", 30.0)

        left_answer = egomotion.answer_relative_direction(0.0, 10.0, artifact_path=left)
        right_answer = egomotion.answer_relative_direction(0.0, 10.0, artifact_path=right)

        self.assertEqual(left_answer["direction"], "left")
        self.assertEqual(right_answer["direction"], "right")

    def test_ask_home_uses_the_artifact_beside_requested_memory(self) -> None:
        left = self.artifact("left_clip", -30.0)
        right = self.artifact("right_clip", 30.0)
        mems = {"kf": [
            {"t": 0.0, "caption": "using a laptop", "_ocr_txt": ""},
            {"t": 10.0, "caption": "a lift door", "_ocr_txt": ""},
        ]}

        # run_live adds scripts/ to sys.path; patching the same import name keeps
        # this focused test independent of how unittest was launched.
        with patch.dict(sys.modules, {"build_egomotion_visual": egomotion}):
            left_result = ask_home.answer_spatial(
                "Where is the lift compared to me when viewing the laptop?",
                mems, str(left.parent / "world_memory.json"))
            right_result = ask_home.answer_spatial(
                "Where is the lift compared to me when viewing the laptop?",
                mems, str(right.parent / "world_memory.json"))

        self.assertIn("to your left", left_result["answer"])
        self.assertIn("to your right", right_result["answer"])

    def test_malformed_clip_artifact_refuses_instead_of_using_other_clip(self) -> None:
        good = self.artifact("good_clip", 30.0)
        bad = self.artifact("bad_clip", -30.0)
        bad.write_text('{"track": []}')
        mems = {"kf": [
            {"t": 0.0, "caption": "using a laptop", "_ocr_txt": ""},
            {"t": 10.0, "caption": "a lift door", "_ocr_txt": ""},
        ]}

        # A valid artifact elsewhere must never rescue the requested bad clip.
        self.assertTrue(good.exists())
        with patch.dict(sys.modules, {"build_egomotion_visual": egomotion}):
            result = ask_home.answer_spatial(
                "Where is the lift compared to me when viewing the laptop?",
                mems, str(bad.parent / "world_memory.json"))

        self.assertEqual(result["answer"], ask_home.SPATIAL_REFUSAL)


if __name__ == "__main__":
    unittest.main()
