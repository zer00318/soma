from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import ask_home
import structured_recall


class StructuredRecallTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.memory_dir = Path(self.temp.name)
        self.memory_path = self.memory_dir / "world_memory.json"
        self.memory_path.write_text('{"objects": []}')

    def tearDown(self):
        self.temp.cleanup()

    def write_kf(self, rows):
        (self.memory_dir / "kf_memory.json").write_text(json.dumps(rows))

    def test_high_confidence_addressee_becomes_wearer_identity(self):
        self.write_kf([{"t": 1.0, "caption": "A hallway.", "ocr": []}])
        (self.memory_dir / "asr.json").write_text(json.dumps({"segments": [
            {"start": 2.0, "text": "Take care, Mira."},
        ]}))

        result = structured_recall.recall("Could you tell me my name?", str(self.memory_path))

        self.assertEqual(result["value"], "Mira")
        self.assertGreaterEqual(result["confidence"], 0.9)
        self.assertEqual(result["provenance"][0]["channel"], "speech")

    def test_hailing_someone_else_does_not_become_wearer_identity(self):
        self.write_kf([{"t": 1.0, "caption": "A hallway.", "ocr": []}])
        (self.memory_dir / "asr.json").write_text(json.dumps({"segments": [
            {"start": 2.0, "text": "What's up, Nolan?"},
        ]}))

        self.assertIsNone(structured_recall.recall(
            "What is my identity?", str(self.memory_path)))

    def test_named_wearable_is_not_routed_as_a_generic_outfit(self):
        self.write_kf([
            {"t": 1.0, "caption": "POV getting dressed, wearing a green shirt."},
            {"t": 2.0, "caption": "First-person outfit, wearing a green shirt."},
        ])
        self.assertIsNone(structured_recall.recall(
            "Do I wear eyewear or glasses?", str(self.memory_path)))

    def test_repeated_labeled_identifier_is_recalled_with_both_sources(self):
        self.write_kf([
            {"t": 1.0, "frame": "a.jpg", "caption": "A display.",
             "ocr": ["Sample ID: ZX-41"]},
            {"t": 2.0, "frame": "b.jpg", "caption": "The same display.",
             "ocr": ["Sample ID ZX-41"]},
            {"t": 3.0, "frame": "c.jpg", "caption": "Another label.",
             "ocr": ["Sample ID: NOISE-8"]},
        ])

        result = structured_recall.recall(
            "Which sample identifiers were labeled?", str(self.memory_path))

        self.assertEqual(result["value"], ["ZX-41"])
        self.assertEqual(len(result["provenance"]), 2)

    def test_outfit_requires_consensus_inside_detected_dressing_event(self):
        self.write_kf([
            {"t": 1.0, "frame": "a.jpg",
             "caption": "First-person view while getting dressed; the wearer is wearing a navy hoodie and black trousers.",
             "ocr": []},
            {"t": 2.0, "frame": "b.jpg",
             "caption": "Point of view during outfit selection, wearing a navy hoodie with black trousers.",
             "ocr": []},
            {"t": 3.0, "frame": "c.jpg",
             "caption": "POV getting dressed; the person is wearing a navy hoodie and black trousers.",
             "ocr": []},
            {"t": 30.0, "frame": "d.jpg",
             "caption": "A stranger is wearing a red jacket outside.", "ocr": []},
        ])

        result = structured_recall.recall("What outfit was I wearing?", str(self.memory_path))

        self.assertEqual(set(result["value"]), {"navy hoodie", "black trousers"})
        self.assertTrue(all(row["t"] < 10 for row in result["provenance"]))

    def test_named_institution_needs_repeated_or_cross_channel_visible_text(self):
        self.write_kf([
            {"t": 1.0, "frame": "a.jpg", "caption": "A sign.",
             "ocr": ["Northbridge University"]},
        ])
        (self.memory_dir / "screen_memory.json").write_text(json.dumps([
            {"t": 2.0, "frame": "screen.jpg", "screen_ocr": ["Northbridge University"]},
        ]))

        result = structured_recall.recall(
            "Which institution or university was visible?", str(self.memory_path))

        self.assertEqual(result["value"], "Northbridge University")
        self.assertEqual({row["channel"] for row in result["provenance"]}, {"ocr", "screen"})
        self.assertEqual(result["confidence"], 0.95)

    def test_single_unconfirmed_visible_value_is_not_answered(self):
        self.write_kf([
            {"t": 1.0, "caption": "A label.", "ocr": ["Example ID: SOLO-7"]},
            {"t": 2.0, "caption": "A sign.", "ocr": ["Eastmere Institute"]},
        ])
        self.assertIsNone(structured_recall.recall(
            "Which example identifiers were labeled?", str(self.memory_path)))
        self.assertIsNone(structured_recall.recall(
            "What institution was visible?", str(self.memory_path)))

    def test_display_count_uses_distinct_temporal_episodes(self):
        self.write_kf([
            {"t": 1.0, "caption": "A poster is visible."},
            {"t": 2.0, "caption": "The same poster remains visible."},
            {"t": 10.0, "caption": "A billboard is visible."},
            {"t": 11.0, "caption": "The billboard remains visible."},
        ])
        result = structured_recall.recall(
            "How many posters were there in total?", str(self.memory_path))
        self.assertEqual(result["value"], 2)

    def test_empty_place_requires_repeated_zero_person_frames(self):
        self.write_kf([
            {"t": float(t), "caption": "An empty subway platform."} for t in range(6)
        ])
        (self.memory_dir / "entity_capture.json").write_text(json.dumps([
            {"t": float(t), "frame": f"f{t}", "parse_ok": True, "persons": []}
            for t in range(6)
        ]))
        result = structured_recall.recall(
            "Was the station crowded or empty?", str(self.memory_path))
        self.assertEqual(result["value"], "empty")

    def test_ask_uses_structured_result_before_assembler(self):
        self.write_kf([
            {"t": 1.0, "frame": "a.jpg", "caption": "A display.",
             "ocr": ["Case ID: LM-22"]},
            {"t": 2.0, "frame": "b.jpg", "caption": "A display.",
             "ocr": ["Case ID: LM-22"]},
        ])

        with patch.object(ask_home, "answer_assembler",
                          side_effect=AssertionError("assembler must not run")):
            result = ask_home.ask(
                "What case identifier was labeled?", str(self.memory_path))

        self.assertEqual(result["structured_recall"]["value"], ["LM-22"])
        self.assertEqual(len(result["scenes"]), 2)

    def test_unrelated_question_continues_to_assembler(self):
        self.write_kf([
            {"t": 1.0, "frame": "a.jpg", "caption": "A lamp is beside a sofa.",
             "ocr": []},
        ])
        assembled = {"answer": "assembler result", "scenes": []}

        with patch.object(ask_home, "answer_assembler", return_value=assembled) as call:
            result = ask_home.ask("Where was the lamp?", str(self.memory_path))

        self.assertEqual(result, assembled)
        call.assert_called_once()


if __name__ == "__main__":
    unittest.main()
