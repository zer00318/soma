from __future__ import annotations

import unittest

from soma_hub.graph_audit import GraphAuditor


class GraphAuditTests(unittest.TestCase):
    def test_empty_graph_is_not_ready(self) -> None:
        result = GraphAuditor().audit(
            {
                "entities": 0,
                "events": 0,
                "relations": 0,
                "attributes": 0,
                "observations": 0,
                "places": 0,
                "recent_entities": [],
                "recent_relations": [],
            }
        )

        self.assertEqual(result.grade, "not-ready")
        self.assertIn("No graph entities yet. Run the native POV app with the hub active.", result.issues)

    def test_grounded_graph_scores_usable_or_better(self) -> None:
        result = GraphAuditor().audit(
            {
                "entities": 3,
                "events": 1,
                "relations": 4,
                "attributes": 3,
                "observations": 5,
                "places": 1,
                "recent_entities": [
                    {
                        "label": "visible person",
                        "kind": "person",
                        "status": "current",
                        "observation_count": 4,
                        "confidence": 0.82,
                    }
                ],
                "recent_relations": [],
            },
            [
                {"relation_type": "seen_in_frame_region", "subject": "visible person", "object": "middle center frame", "status": "current"},
                {"relation_type": "foreground_status", "subject": "visible person", "object": "large visible object", "status": "current"},
                {"relation_type": "contains_text", "subject": "transit sign", "object": "Garching", "status": "current"},
                {"relation_type": "located_at", "subject": "transit sign", "object": "Garching-Forschungszentrum", "status": "current"},
            ],
            [
                {
                    "label": "visible person",
                    "kind": "person",
                    "status": "current",
                    "slot_order": ["entity_type", "face.visible", "body.visible", "eyewear"],
                    "missing_slots": ["body.visible"],
                    "slots": {
                        "entity_type": [{"value": "person"}],
                        "face.visible": [{"value": "face or partial face visible"}],
                        "eyewear": [{"value": "glasses"}],
                    },
                },
                {
                    "label": "transit sign",
                    "kind": "text_surface",
                    "status": "current",
                    "slot_order": ["object_type", "text.visible", "located_at"],
                    "missing_slots": [],
                    "slots": {
                        "object_type": [{"value": "transit sign"}],
                        "text.visible": [{"value": "Garching-Forschungszentrum"}],
                        "located_at": [{"value": "Garching"}],
                    },
                },
            ],
        )

        self.assertGreaterEqual(result.score, 85)
        self.assertIn("Detector spatial grounding is present.", result.strengths)
        self.assertIn("Entity attribute slots are accumulating.", result.strengths)
        self.assertIn("Profiles are accumulating multi-slot detail.", result.strengths)
        self.assertIn("Text/sign profiles retain readable OCR text.", result.strengths)
        self.assertEqual(result.issues, [])
        self.assertGreaterEqual(result.profile_quality[0]["present_count"], 3)

    def test_shallow_current_person_profile_is_flagged(self) -> None:
        result = GraphAuditor().audit(
            {
                "entities": 1,
                "events": 0,
                "relations": 4,
                "attributes": 1,
                "observations": 4,
                "places": 1,
                "recent_entities": [
                    {
                        "label": "visible person",
                        "kind": "person",
                        "status": "current",
                        "observation_count": 4,
                        "confidence": 0.78,
                    }
                ],
            },
            [
                {"relation_type": "seen_in_frame_region", "subject": "visible person", "object": "middle center frame", "status": "current"},
                {"relation_type": "foreground_status", "subject": "visible person", "object": "large visible object", "status": "current"},
                {"relation_type": "contains_text", "subject": "transit sign", "object": "Garching", "status": "current"},
                {"relation_type": "located_at", "subject": "visible person", "object": "Garching", "status": "current"},
            ],
            [
                {
                    "label": "visible person",
                    "kind": "person",
                    "status": "current",
                    "slot_order": ["entity_type", "face.visible", "body.visible", "eyewear"],
                    "missing_slots": ["face.visible", "body.visible", "eyewear"],
                    "slots": {"entity_type": [{"value": "person"}]},
                }
            ],
        )

        self.assertIn(
            "Current person profile is still shallow; hold the subject steady to enrich visible slots.",
            result.issues,
        )
        self.assertEqual(result.profile_quality[0]["present_count"], 1)

    def test_retained_text_profile_prevents_false_ocr_failure(self) -> None:
        result = GraphAuditor().audit(
            {
                "entities": 1,
                "events": 0,
                "relations": 3,
                "attributes": 3,
                "observations": 5,
                "places": 1,
                "recent_entities": [
                    {
                        "label": "transit sign",
                        "kind": "text_surface",
                        "status": "provisional",
                        "observation_count": 5,
                        "confidence": 0.78,
                    }
                ],
            },
            [
                {"relation_type": "seen_in_frame_region", "subject": "transit sign", "object": "upper frame", "status": "provisional"},
                {"relation_type": "foreground_status", "subject": "transit sign", "object": "large visible object", "status": "provisional"},
                {"relation_type": "located_at", "subject": "transit sign", "object": "Garching", "status": "provisional"},
            ],
            [
                {
                    "label": "transit sign",
                    "kind": "text_surface",
                    "status": "provisional",
                    "slot_order": ["object_type", "text.visible", "located_at"],
                    "missing_slots": [],
                    "slots": {
                        "object_type": [{"value": "transit sign"}],
                        "text.visible": [{"value": "Max-Planck-Campus"}],
                        "located_at": [{"value": "Garching"}],
                    },
                }
            ],
        )

        self.assertNotIn("No OCR text relations. Point at a sign/board/package and hold steady.", result.issues)
        self.assertIn("Text/sign profiles retain readable OCR text from earlier frames.", result.strengths)


if __name__ == "__main__":
    unittest.main()
