from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from same_event_relations import build_relation_index, compact_relation_summary, query_focus
from ask_home import build_evidence_dossier


def row(t, *, objects=(), persons=()):
    return {"t": t, "frame": f"frame_{t}.jpg", "parse_ok": True,
            "text_objects": list(objects), "persons": list(persons)}


def obj(kind, text):
    return {"object": kind, "logo_or_text": text}


def person(description, top=""):
    return {"appearance": description, "clothing": {"top": top, "bottom": "", "colors": []},
            "accessories": [], "holding": [], "position": "center"}


class SameEventRelationTests(unittest.TestCase):
    def test_ocr_variants_merge_with_frame_provenance(self):
        rows = [row(1.0, objects=[obj("poster", "Hans Fischer")]),
                row(1.5, objects=[obj("wall poster", "H. Fischer")])]
        episode = build_relation_index(rows)["object_episodes"][0]
        self.assertEqual(len(episode["text_groups"]), 1)
        self.assertEqual({v["value"] for v in episode["text_groups"][0]["variants"]},
                         {"Hans Fischer", "H. Fischer"})
        provenance = [p for v in episode["text_groups"][0]["variants"] for p in v["provenance"]]
        self.assertEqual({p["t"] for p in provenance}, {1.0, 1.5})
        self.assertFalse(episode["conflicts"])

    def test_incompatible_same_surface_reads_preserve_conflict(self):
        rows = [row(2.0, objects=[obj("door sign", "ROOM A")]),
                row(2.4, objects=[obj("door sign", "ROOM B")])]
        index = build_relation_index(rows)
        episode = index["object_episodes"][0]
        self.assertEqual(len(episode["text_groups"]), 2)
        self.assertTrue(episode["conflicts"])
        self.assertEqual(query_focus(index, "what did the sign say")["binding"], "ambiguous")

    def test_person_focus_cannot_borrow_text_from_distant_episode(self):
        blue = person("adult with short hair", "blue jacket")
        rows = [
            row(1.0, objects=[obj("poster", "Alpha Name")], persons=[blue]),
            row(1.4, objects=[obj("poster", "A. Name")], persons=[blue]),
            row(8.0, objects=[obj("poster", "Distant Name")]),
        ]
        summary = compact_relation_summary(rows, "what name was on the poster near the person in blue")
        self.assertIn("Alpha Name", summary)
        self.assertNotIn("Distant Name", summary)
        self.assertIn("one temporally supported focus episode", summary)

    def test_object_descriptor_selects_only_matching_episode(self):
        rows = [row(1.0, objects=[obj("blue poster", "First Name")]),
                row(7.0, objects=[obj("red poster", "Second Name")])]
        summary = compact_relation_summary(rows, "what name was on the blue poster")
        self.assertIn("First Name", summary)
        self.assertNotIn("Second Name", summary)

    def test_distinctive_text_context_beats_generic_surface_type(self):
        rows = [
            row(1.0, objects=[obj("poster", "GENERIC SUBJECT")]),
            row(7.0, objects=[obj("display sign", "CONTEXT SUBJECT")]),
            row(7.4, objects=[obj("whiteboard", "MOLECULE DIAGRAM")]),
        ]
        summary = compact_relation_summary(rows, "who was named on the poster of the molecule")
        self.assertIn("CONTEXT SUBJECT", summary)
        self.assertIn("MOLECULE DIAGRAM", summary)
        self.assertNotIn("GENERIC SUBJECT", summary)

    def test_generic_type_without_context_is_never_uniquely_bound(self):
        rows = [row(1.0, objects=[obj("poster", "ONLY READ")])]
        result = query_focus(build_relation_index(rows), "what name was on the poster")
        self.assertEqual(result["binding"], "ambiguous")
        summary = compact_relation_summary(rows, "what name was on the poster")
        self.assertNotIn("BOUND contains_text", summary)
        self.assertIn("AMBIGUOUS", summary)

    def test_person_text_relation_is_cooccurrence_not_ownership(self):
        rows = [row(3.0, objects=[obj("name tag", "Visitor Name")],
                    persons=[person("person in a green coat", "green coat")])]
        summary = compact_relation_summary(rows, "what text was near the person in green")
        self.assertIn("Visitor Name", summary)
        self.assertIn("co-occurrence only", summary)
        self.assertIn("ownership is not inferred", summary)

    def test_relation_summary_is_wired_into_evidence_dossier(self):
        blue = person("adult with glasses", "blue coat")
        rows = [row(4.0, objects=[obj("poster", "Sample Name")], persons=[blue]),
                row(4.5, objects=[obj("poster", "S. Name")], persons=[blue])]
        dossier, _ = build_evidence_dossier(
            "what name was on the poster near the person in blue", {"entity_capture": rows},
            max_per_channel=5,
        )
        self.assertIn("=== SAME-EVENT RELATIONS", dossier)
        self.assertIn("BOUND contains_text", dossier)
        self.assertIn("Sample Name", dossier)
        self.assertIn("do not bind names/text across timestamps", dossier)


if __name__ == "__main__":
    unittest.main()
