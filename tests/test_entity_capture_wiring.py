from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ask_home import build_evidence_dossier, gather_evidence


class EntityCaptureWiringTests(unittest.TestCase):
    def _memory(self, root: Path) -> Path:
        path = root / "world_memory.json"
        path.write_text(json.dumps({"objects": []}), encoding="utf-8")
        return path

    def _mems(self) -> dict:
        return {"kf": None, "world": [], "kf_path": None}

    def test_entity_capture_is_bound_and_missing_zip_gets_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory_path = self._memory(root)
            rows = [
                {
                    "t": 1.5,
                    "frame": "frame_1.jpg",
                    "persons": [{
                        "appearance": "short-haired person",
                        "clothing": {"top": "green top", "bottom": "black trousers",
                                     "colors": ["green", "black"]},
                        "accessories": ["backpack"],
                        "holding": [],
                        "position": "left",
                    }],
                    "text_objects": [],
                    "is_self_view": False,
                    "self_attributes": {},
                    "parse_ok": True,
                },
                {
                    "t": 2.0,
                    "frame": "frame_2.jpg",
                    "persons": [],
                    "text_objects": [{"object": "backpack", "logo_or_text": "North Face"}],
                    "is_self_view": False,
                    "self_attributes": {},
                    "parse_ok": True,
                },
                {
                    "t": 3.0,
                    "frame": "frame_3.jpg",
                    "persons": [],
                    "text_objects": [],
                    "is_self_view": True,
                    "self_attributes": {"holding": ["keys"], "body": ["hands"]},
                    "parse_ok": True,
                },
                {
                    "t": 4.0,
                    "frame": "frame_4.jpg",
                    "persons": [{"appearance": "ignored red person"}],
                    "text_objects": [],
                    "parse_ok": False,
                },
            ]
            ndjson = "\n".join(json.dumps(row) for row in rows[:2])
            ndjson += "\nnot valid json\n\n" + "\n".join(json.dumps(row) for row in rows[2:])
            (root / "entity_capture.json").write_text(ndjson + "\n", encoding="utf-8")

            channels = gather_evidence(
                "was my bag zip open or closed", str(memory_path),
                self._mems(),
            )
            dossier, _ = build_evidence_dossier(
                "was my bag zip open or closed", channels, max_per_channel=10,
            )

            self.assertEqual(len(channels["entity_capture"]), 4)
            self.assertIn("PERSON: short-haired person — top green top", dossier)
            self.assertIn('OBJECT: backpack — logo/text: "North Face"', dossier)
            person_line = next(line for line in dossier.splitlines() if "PERSON:" in line)
            object_line = next(line for line in dossier.splitlines() if "OBJECT: backpack" in line)
            self.assertNotIn("North Face", person_line)
            self.assertIn("North Face", object_line)
            self.assertIn("SELF-VIEW:", dossier)
            self.assertNotIn("ignored red person", dossier)
            self.assertIn("no zip/zipper state was recorded for bag", dossier)

    def test_missing_entity_capture_degrades_to_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory_path = self._memory(root)
            channels = gather_evidence(
                "what did I see", str(memory_path), self._mems(),
            )

            self.assertIsNone(channels["entity_capture"])
            dossier, cited = build_evidence_dossier("what did I see", channels)
            self.assertIsInstance(dossier, str)
            self.assertEqual(cited, [])
            self.assertNotIn("=== ENTITY CAPTURE", dossier)

            (root / "entity_capture.json").write_text("garbage\n[]\n", encoding="utf-8")
            channels = gather_evidence("what did I see", str(memory_path), self._mems())
            self.assertIsNone(channels["entity_capture"])


if __name__ == "__main__":
    unittest.main()
