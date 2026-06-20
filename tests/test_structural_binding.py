#!/usr/bin/env python3
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import ask_home
import entity_graph


class StructuralBindingTests(unittest.TestCase):
    def _memory(self, root):
        path = os.path.join(root, "world_memory.json")
        with open(path, "w") as out:
            json.dump({"objects": []}, out)
        entities = [
            {"entity_id": "self", "type": "self", "label": "the wearer (camera/self)",
             "attributes": [{"attr": "accessory", "value": "black watch",
                              "frames": [1.0, 2.0], "confidence": 0.7}],
             "mentions": [1.0, 2.0]},
            {"entity_id": "person:1", "type": "person", "label": "person in pink top",
             "attributes": [{"attr": "accessory", "value": "glasses",
                              "frames": [3.0], "confidence": 0.6}], "mentions": [3.0]},
            {"entity_id": "person:2", "type": "person", "label": "person in green top",
             "attributes": [{"attr": "top", "value": "green shirt",
                              "frames": [4.0], "confidence": 0.6}], "mentions": [4.0]},
            {"entity_id": "object:backpack", "type": "object", "label": "backpack",
             "attributes": [{"attr": "logo_or_text", "value": "North Face",
                              "frames": [5.0], "confidence": 0.9}], "mentions": [5.0]},
        ]
        with open(os.path.join(root, "entity_centric.json"), "w") as out:
            json.dump(entities, out)
        return path

    def test_other_person_glasses_cannot_become_self_attribute(self):
        with tempfile.TemporaryDirectory() as root:
            memory = self._memory(root)
            verdict, _ = ask_home.structural_grounding(
                "Do I wear eyewear or glasses?", "Yes, the person is wearing glasses.", memory)
            self.assertEqual(verdict, "refuse")
            verdict, text = ask_home.structural_grounding(
                "Was I wearing a watch?", "Yes, you were wearing a black watch.", memory)
            self.assertEqual((verdict, text), ("assert", "Yes, you were wearing a black watch."))

    def test_relational_logo_resolves_to_person_not_free_object(self):
        with tempfile.TemporaryDirectory() as root:
            self._memory(root)
            graph = entity_graph.build_entities(root)
            binding = entity_graph.binding_confidence(
                "What was the logo on the mate I fist-bumped?", graph)
            self.assertFalse(binding["answerable"])
            self.assertGreater(binding["confidence"], 0)
            self.assertIn("owner person", binding["reason"])

    def test_binary_state_must_be_present_in_capture_text(self):
        with tempfile.TemporaryDirectory() as root:
            memory = self._memory(root)
            with open(os.path.join(root, "kf_memory.json"), "w") as out:
                json.dump([
                    {"t": 1.0, "caption": "A backpack is visible.", "ocr": []},
                    {"t": 2.0, "caption": "The nearby door is closed.", "ocr": []},
                ], out)
            verdict, _ = ask_home.structural_grounding(
                "Was my bag zip open or closed?", "The bag was zipped closed.", memory)
            self.assertEqual(verdict, "refuse")

    def test_third_person_pronoun_overrides_incidental_first_person_event(self):
        with tempfile.TemporaryDirectory() as root:
            self._memory(root)
            graph = entity_graph.build_entities(root)
            binding = entity_graph.binding_confidence(
                "I said hi to someone; what was he wearing?", graph)
            self.assertFalse(binding["answerable"])
            self.assertIn("non-self person", binding["reason"])
            self.assertIn("2 distinct person", binding["reason"])

    def test_caption_only_presence_cannot_be_licensed_by_other_words(self):
        with tempfile.TemporaryDirectory() as root:
            memory = self._memory(root)
            with open(os.path.join(root, "kf_memory.json"), "w") as out:
                json.dump([
                    {"t": 1.0, "caption": "A blurry train may be beside the platform.", "ocr": []},
                    {"t": 2.0, "caption": "A sign with a train icon is visible.", "ocr": []},
                ], out)
            verdict, _ = ask_home.structural_grounding(
                "Was there a train at the station or was it empty?",
                "There was a train at the station beside a clearly visible platform sign.",
                memory,
            )
            self.assertEqual(verdict, "refuse")

    def test_ocr_text_alone_cannot_prove_ui_state(self):
        with tempfile.TemporaryDirectory() as root:
            memory = self._memory(root)
            with open(os.path.join(root, "screen_memory.json"), "w") as out:
                json.dump([{"t": 1, "screen_ocr": ["Workspace / Chat title", "Input"]}], out)
            verdict, _ = ask_home.structural_grounding(
                "Which chat was actively asking for input?", "The Chat title was active.", memory)
            self.assertEqual(verdict, "refuse")

            with open(os.path.join(root, "screen_memory.json"), "w") as out:
                json.dump([{"t": 1, "screen_ocr": ["Chat title"],
                            "ui_state": {"active": True}}], out)
            verdict, text = ask_home.structural_grounding(
                "Which chat was actively asking for input?", "The Chat title was active.", memory)
            self.assertEqual((verdict, text), ("assert", "The Chat title was active."))


if __name__ == "__main__":
    unittest.main()
