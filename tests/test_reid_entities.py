from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import reid_entities


def person(appearance, top="", bottom="", position="center", accessories=None, holding=None):
    return {
        "appearance": appearance,
        "clothing": {"top": top, "bottom": bottom, "colors": []},
        "accessories": accessories or [],
        "holding": holding or [],
        "position": position,
    }


class ReidentificationTests(unittest.TestCase):
    def test_mixed_self_view_routes_only_egocentric_record_to_self(self):
        rows = [{
            "t": 1.0,
            "is_self_view": True,
            "self_attributes": {"body": ["hands"], "clothing": ["black shirt"]},
            "persons": [
                person("hands visible, wearing a watch", "black shirt"),
                person("young man with blonde hair", "gray t-shirt", "black shorts", "right"),
            ],
        }]
        graph = reid_entities.reid(rows)
        selves = [e for e in graph["entities"] if e["type"] == "self"]
        others = [e for e in graph["entities"] if e["type"] == "person"]

        self.assertEqual(len(selves), 1)
        self.assertEqual(len(others), 1)
        self.assertIn("gray", " ".join(a["value"] for a in others[0]["attributes"]))
        self.assertNotIn("gray", " ".join(a["value"] for a in selves[0]["attributes"]))

    def test_body_crop_routes_to_self_when_boolean_flag_was_missed(self):
        rows = [{
            "t": 1.0,
            "is_self_view": False,
            "self_attributes": {},
            "persons": [person("hand with visible fingers", holding=["stylus"])],
        }]
        graph = reid_entities.reid(rows)
        self.assertEqual([e["type"] for e in graph["entities"]], ["self"])

    def test_visible_hands_do_not_override_clear_other_person_identity(self):
        rows = [{
            "t": 1.0,
            "is_self_view": False,
            "persons": [person("young woman with long hair, hands visible", "blue jacket")],
        }]
        graph = reid_entities.reid(rows)
        self.assertEqual([e["type"] for e in graph["entities"]], ["person"])

    def test_two_similarly_dressed_people_in_one_frame_remain_distinct(self):
        black_center = person("man wearing a black shirt", "black shirt", "black pants", "center")
        black_right = person("man wearing a black shirt", "black shirt", "black pants", "right")
        rows = [
            {"t": 1.0, "persons": [black_center, black_right]},
            {"t": 1.3, "persons": [black_center, black_right]},
        ]
        people = [e for e in reid_entities.reid(rows)["entities"] if e["type"] == "person"]
        self.assertEqual(len(people), 2)
        self.assertEqual(sorted(len(e["mentions"]) for e in people), [2, 2])

    def test_generic_clothing_does_not_merge_across_scene_boundary(self):
        white = person("person wearing a white shirt", "white shirt")
        rows = [{"t": 1.0, "persons": [white]}, {"t": 8.0, "persons": [white]}]
        people = [e for e in reid_entities.reid(rows)["entities"] if e["type"] == "person"]
        self.assertEqual(len(people), 2)

    def test_changing_held_item_does_not_fragment_same_person(self):
        rows = [
            {"t": 1.0, "persons": [person("blonde hair, glasses", "pink shirt",
                                                accessories=["glasses"], holding=["reader"])]},
            {"t": 1.4, "persons": [person("blonde hair, glasses", "pink t-shirt",
                                                accessories=["glasses"], holding=["keys"])]},
        ]
        people = [e for e in reid_entities.reid(rows)["entities"] if e["type"] == "person"]
        self.assertEqual(len(people), 1)
        holdings = {a["value"] for a in people[0]["attributes"] if a["attr"] == "holding"}
        self.assertEqual(holdings, {"reader", "keys"})


if __name__ == "__main__":
    unittest.main()
