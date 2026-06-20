"""Grounded RAG recall: deterministic sealed retrieval + constrained LLM.

Contract under test (2026-06-11 direction: recall must handle diverse
questions like an LLM chat, while staying strictly grounded):

- context_bundle never treats sentence-leading grammar words ("What",
  "Where") as person names, finds lowercase name mentions, matches plural
  object terms against singular entity labels, and matches attribute
  VALUES ("white" → the entity with color=white).
- _grounded_answer feeds ONLY retrieved context to the LLM, attaches
  citations, and converts a NOT IN MEMORY reply into an honest-miss answer
  that names what the camera HAS seen.
- Routing: a question naming a known contact must reach the grounded path,
  never the generic recent-conversations dump; generic recency questions
  keep the dump.
- The dead-end "I do not have a reliable stored memory" answer is gone
  from graph-backed paths.

The LLM is stubbed via RecallFirewall._llm_generate — these tests verify
the harness around the model, not the model.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from soma_hub.crypto import EncryptedTextCodec
from soma_hub.graph import RelationalMemoryGraph
from soma_hub.recall import RecallFirewall
from soma_hub.storage import MemoryStore

_TEST_KEY = b"soma-test-key-for-unit-tests-xyz"
_NOW = datetime.now(timezone.utc).isoformat()


class _ScriptedFirewall(RecallFirewall):
    """RecallFirewall with a scripted local LLM."""

    def __init__(self, *args, llm_response: str = "", **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.llm_response = llm_response
        self.prompts: list[str] = []

    def _llm_generate(self, prompt: str, timeout: int = 45) -> str:
        self.prompts.append(prompt)
        return self.llm_response


class GroundedRecallTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        codec = EncryptedTextCodec(_TEST_KEY)
        self.db = self.tmp / "soma_hub.sqlite3"
        self.graph = RelationalMemoryGraph(self.db, codec)
        self.store = MemoryStore(self.db, codec)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _firewall(self, llm_response: str = "") -> _ScriptedFirewall:
        return _ScriptedFirewall(self.store, graph=self.graph, llm_response=llm_response)

    def _seed_entity(self, kind: str, label: str, attrs: dict[str, str], source: str = "import") -> str:
        entity_id = str(uuid.uuid4())
        with sqlite3.connect(self.db) as conn:
            conn.execute(
                """INSERT INTO graph_entities
                   (id, kind, label_norm, label, first_seen_at, last_seen_at,
                    confidence, observation_count, status, metadata_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (entity_id, kind, label.lower(), label, _NOW, _NOW, 0.9, 3,
                 "current", json.dumps({"tier": "B"})),
            )
            for key, value in attrs.items():
                conn.execute(
                    """INSERT INTO graph_attributes
                       (id, entity_id, attribute_key, attribute_value, source,
                        first_seen_at, last_seen_at, confidence,
                        observation_count, status, metadata_json)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (str(uuid.uuid4()), entity_id, key, value, source,
                     _NOW, _NOW, 0.9, 1, "current", "{}"),
                )
        return entity_id

    def _seed_contact(self, label: str) -> str:
        return self._seed_entity(
            "person", label,
            {
                "relationship_source": "whatsapp",
                "last_contact_at": _NOW[:10],
                "message_count": "42",
                "recent_topics": "birthday, munich",
            },
            source="whatsapp",
        )


class TestContextBundleRetrieval(GroundedRecallTestCase):
    def test_question_words_are_not_person_names(self) -> None:
        self._seed_contact("Ziwei Zhang")
        self._seed_contact("Watson Crick")
        bundle = self.graph.context_bundle("What did Ziwei Zhang send me")
        labels = {item["label"] for item in bundle if item["kind"] == "person_facts"}
        self.assertIn("Ziwei Zhang", labels)
        self.assertNotIn("Watson Crick", labels, "'What' must never resolve to a person")

    def test_lowercase_name_mention_is_found(self) -> None:
        self._seed_contact("Ziwei Zhang")
        bundle = self.graph.context_bundle("what did ziwei say recently")
        labels = {item["label"] for item in bundle if item["kind"] == "person_facts"}
        self.assertIn("Ziwei Zhang", labels)

    def test_plural_term_matches_singular_entity(self) -> None:
        self._seed_entity("object", "visible shoe", {"color": "white"}, source="vision")
        bundle = self.graph.context_bundle("where are my white shoes")
        labels = {item["label"] for item in bundle if item["kind"] == "object_facts"}
        self.assertIn("visible shoe", labels)

    def test_attribute_value_match_finds_entity(self) -> None:
        self._seed_entity(
            "object", "visible teddy bear", {"color": "white"}, source="vision"
        )
        bundle = self.graph.context_bundle("which of my things is white")
        labels = {item["label"] for item in bundle if item["kind"] == "object_facts"}
        self.assertIn("visible teddy bear", labels)

    def test_empty_graph_returns_empty_bundle(self) -> None:
        self.assertEqual(self.graph.context_bundle("where are my white shoes"), [])


class TestGroundedAnswer(GroundedRecallTestCase):
    def test_answer_carries_citations_and_context_reaches_llm(self) -> None:
        self._seed_entity("object", "visible teddy bear", {"color": "white"}, source="vision")
        fw = self._firewall(llm_response="The teddy bear is white.")
        result = fw.answer("what color is the teddy bear")
        self.assertEqual(result["intent"], "grounded_answer")
        self.assertEqual(result["answer"], "The teddy bear is white.")
        self.assertTrue(result["citations"], "grounded answers must cite evidence")
        self.assertEqual(len(fw.prompts), 1)
        self.assertIn("color=white", fw.prompts[0], "retrieved fact must reach the LLM")
        self.assertIn("CONTEXT", fw.prompts[0])

    def test_not_in_memory_becomes_honest_helpful_miss(self) -> None:
        # Context that MATCHES the terms but cannot answer the question:
        # a brown shoe rack is retrieved for "white shoes", the LLM
        # correctly refuses, and the refusal must become a helpful miss.
        self._seed_entity("object", "visible shoe rack", {"color": "brown"}, source="vision")
        fw = self._firewall(llm_response="NOT IN MEMORY, no white shoes were ever observed")
        result = fw.answer("where are my white shoes")
        self.assertEqual(result["confidence"], 0.0)
        self.assertEqual(len(fw.prompts), 1, "non-empty bundle must reach the LLM")
        self.assertIn("Not in my memory yet", result["answer"])
        self.assertIn("no white shoes were ever observed", result["answer"])
        self.assertNotIn("do not have a reliable", result["answer"])

    def test_empty_bundle_skips_llm_and_misses_helpfully(self) -> None:
        self._seed_entity("object", "visible bottle", {"color": "steel"}, source="vision")
        fw = self._firewall(llm_response="SHOULD NOT BE CALLED")
        result = fw.answer("where are my white shoes")
        self.assertEqual(result["confidence"], 0.0)
        self.assertEqual(fw.prompts, [], "nothing retrieved → no LLM call")
        self.assertIn("visible bottle", result["answer"],
                       "miss should say what the camera HAS seen")
        self.assertNotIn("do not have a reliable", result["answer"])

    def test_llm_failure_falls_back_to_deterministic_miss(self) -> None:
        self._seed_entity("object", "visible shoe", {"color": "brown"}, source="vision")

        class _BrokenLLM(_ScriptedFirewall):
            def _llm_generate(self, prompt: str, timeout: int = 45) -> str:
                raise OSError("ollama down")

        fw = _BrokenLLM(self.store, graph=self.graph)
        result = fw.answer("where are my white shoes")
        self.assertEqual(result["confidence"], 0.0)
        self.assertNotIn("do not have a reliable", result["answer"])


class TestRouting(GroundedRecallTestCase):
    def test_named_contact_beats_recency_dump(self) -> None:
        self._seed_contact("Ziwei Zhang")
        self._seed_contact("Latheesh Roy")
        fw = self._firewall(llm_response="You discussed her move to Munich.")
        result = fw.answer("what did Ziwei Zhang and I talk about recently")
        self.assertEqual(result["intent"], "grounded_answer")
        self.assertNotIn("Recent conversations:", result["answer"])

    def test_lowercase_named_contact_beats_recency_dump(self) -> None:
        self._seed_contact("Ziwei Zhang")
        fw = self._firewall(llm_response="She mentioned the Gdansk gift.")
        result = fw.answer("what did ziwei say recently")
        self.assertEqual(result["intent"], "grounded_answer")

    def test_generic_recency_question_keeps_contacts_dump(self) -> None:
        self._seed_contact("Ziwei Zhang")
        fw = self._firewall(llm_response="SHOULD NOT BE CALLED")
        result = fw.answer("who have I been talking to lately")
        self.assertEqual(result["intent"], "recent_context")
        self.assertIn("Recent conversations:", result["answer"])
        self.assertEqual(fw.prompts, [], "generic recency must not invoke the LLM")


if __name__ == "__main__":
    unittest.main()


class TestWalk1Lessons(GroundedRecallTestCase):
    """Walk-1 (RAS -8.0) regressions: stale facts must never serve
    time-scoped questions, facts carry observation dates, distance is
    computable from the GPS trail."""

    def _seed_old_entity(self, label: str, attrs: dict[str, str], days_old: int = 3) -> str:
        import sqlite3 as _sq
        from datetime import timedelta
        old = (datetime.now(timezone.utc) - timedelta(days=days_old)).isoformat()
        entity_id = self._seed_entity("object", label, attrs, source="vision")
        with _sq.connect(self.db) as conn:
            conn.execute("UPDATE graph_entities SET first_seen_at=?, last_seen_at=? WHERE id=?",
                         (old, old, entity_id))
            conn.execute("UPDATE graph_attributes SET first_seen_at=?, last_seen_at=? WHERE entity_id=?",
                         (old, old, entity_id))
        return entity_id

    def test_time_scoped_question_excludes_stale_vision_facts(self) -> None:
        self._seed_old_entity("visible headphones", {"color": "gray"}, days_old=3)
        scoped = self.graph.context_bundle(
            "did I wear headphones during my walk",
            since=datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00"),
        )
        self.assertFalse([i for i in scoped if i["kind"] == "object_facts"],
                         "desk-era facts must not serve walk-scoped questions")
        unscoped = self.graph.context_bundle("what color are my headphones")
        self.assertTrue([i for i in unscoped if i["kind"] == "object_facts"],
                        "unscoped questions still see older facts")

    def test_object_facts_carry_observation_dates(self) -> None:
        self._seed_entity("object", "visible bottle", {"color": "steel"}, source="vision")
        bundle = self.graph.context_bundle("what color is the bottle")
        obj = [i for i in bundle if i["kind"] == "object_facts"]
        self.assertTrue(obj)
        self.assertIn("[observed", obj[0]["text"])

    def test_question_since_detects_walk_scope(self) -> None:
        fw = self._firewall()
        self.assertIsNotNone(fw._question_since("did I wear headphones during my walk"))
        self.assertIsNotNone(fw._question_since("what did you see today"))
        self.assertIsNone(fw._question_since("what color are my headphones"))

    def test_distance_from_gps_trail(self) -> None:
        import sqlite3 as _sq
        import uuid as _uuid
        now = datetime.now(timezone.utc)
        # ~111m apart per 0.001 deg latitude: 4 fixes -> ~333m
        with _sq.connect(self.db) as conn:
            for i in range(4):
                conn.execute(
                    """INSERT INTO graph_observations
                       (id, captured_at, source_type, provider, confidence,
                        stability_count, scene_phase, evidence_cipher, metadata_json)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (str(_uuid.uuid4()), now.isoformat(), "vision", "test", 0.9,
                     1, "active", "x",
                     json.dumps({"location_hint": f"GPS {48.262 + i * 0.001:.5f}, 11.67538, accuracy ~5m"})),
                )
        km, fixes = self.graph.distance_covered_km(now.strftime("%Y-%m-%dT00:00:00"))
        self.assertEqual(fixes, 4)
        self.assertAlmostEqual(km, 0.333, delta=0.03)
        fw = self._firewall()
        result = fw.answer("how much distance have we covered today")
        self.assertEqual(result["intent"], "distance")
        self.assertIn("meters", result["answer"])
