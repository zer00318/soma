"""Tests for Bug 2 (observation dedup) and Bug 4 (real-name resolution).

Bug 2: 60-second dedup window in _insert_observation prevents observation flood.
Bug 4: RecallFirewall resolves real names from graph_attributes, never exposes UUIDs.
"""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from soma_hub.crypto import EncryptedTextCodec
from soma_hub.graph import RelationalMemoryGraph
from soma_hub.recall import RecallFirewall
from soma_hub.storage import MemoryStore

# Stable test key — 32 bytes minimum
_TEST_KEY = b"soma-test-key-for-unit-tests-xyz"


def _make_graph(tmp_path: Path) -> RelationalMemoryGraph:
    codec = EncryptedTextCodec(_TEST_KEY)
    return RelationalMemoryGraph(tmp_path / "soma_hub.sqlite3", codec)


def _make_store(tmp_path: Path) -> MemoryStore:
    codec = EncryptedTextCodec(_TEST_KEY)
    return MemoryStore(tmp_path / "soma_hub.sqlite3", codec)


class TestObservationDedup(unittest.TestCase):
    """Bug 2: _insert_observation deduplicates within 60-second window."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.graph = _make_graph(self.tmp)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _count_observations(self) -> int:
        db_path = self.tmp / "soma_hub.sqlite3"
        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM graph_observations").fetchone()
            return row[0]

    def test_duplicate_packet_within_60s_creates_one_observation(self) -> None:
        """Ingesting the same scene text twice rapidly should yield one observation."""
        text = "OBJECT | visible person | person tracked by local detector; body/upper body visible | detector stream | likely"

        self.graph.ingest_packet({
            "memory_text": text,
            "source_type": "vision",
            "provider": "detector",
            "scene_phase": "active",
            "stability_count": 3,
        })
        self.graph.ingest_packet({
            "memory_text": text,
            "source_type": "vision",
            "provider": "detector",
            "scene_phase": "active",
            "stability_count": 3,
        })

        obs_count = self._count_observations()
        self.assertEqual(
            obs_count, 1,
            f"Expected 1 observation (dedup), got {obs_count}. Bug 2 dedup is not working.",
        )

    def test_different_scene_phases_create_separate_observations(self) -> None:
        """Scene-phase change must create a new observation, not dedup."""
        text = "OBJECT | visible person | person tracked by local detector; body/upper body visible | detector stream | likely"

        self.graph.ingest_packet({
            "memory_text": text,
            "source_type": "vision",
            "provider": "detector",
            "scene_phase": "active",
        })
        self.graph.ingest_packet({
            "memory_text": text,
            "source_type": "vision",
            "provider": "detector",
            "scene_phase": "quiet",  # different phase → new observation
        })

        obs_count = self._count_observations()
        self.assertGreaterEqual(
            obs_count, 2,
            "Different scene phases must produce separate observations.",
        )

    def test_different_entity_labels_create_separate_observations(self) -> None:
        """Two different objects in the same phase must each create their own observation."""
        self.graph.ingest_packet({
            "memory_text": "OBJECT | laptop | detected by local tracker | detector stream | likely",
            "source_type": "vision",
            "provider": "detector",
            "scene_phase": "active",
        })
        self.graph.ingest_packet({
            "memory_text": "OBJECT | coffee mug | detected by local tracker | detector stream | likely",
            "source_type": "vision",
            "provider": "detector",
            "scene_phase": "active",
        })

        obs_count = self._count_observations()
        self.assertGreaterEqual(
            obs_count, 2,
            "Different entity labels must produce separate observations.",
        )


class TestGetEntityAttribute(unittest.TestCase):
    """Bug 4: get_entity_attribute returns stored attributes by key."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.graph = _make_graph(self.tmp)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_returns_none_for_unknown_entity(self) -> None:
        result = self.graph.get_entity_attribute("nonexistent-id", "real_name")
        self.assertIsNone(result)

    def test_returns_none_for_unknown_attribute(self) -> None:
        # Create an entity first
        self.graph.ingest_packet({
            "memory_text": "OBJECT | visible person | person detected by local tracker | detector stream | likely",
            "source_type": "vision",
            "provider": "detector",
            "scene_phase": "active",
        })
        people = self.graph.recent_people(hours=1)
        self.assertTrue(people, "Expected at least one person entity")
        entity_id = people[0]["id"]

        result = self.graph.get_entity_attribute(entity_id, "nonexistent_key")
        self.assertIsNone(result)

    def test_link_person_name_then_get_attribute(self) -> None:
        """link_person_name stores real_name; get_entity_attribute retrieves it."""
        self.graph.ingest_packet({
            "memory_text": "OBJECT | visible person | person tracked by local detector | detector stream | likely",
            "source_type": "vision",
            "provider": "detector",
            "scene_phase": "active",
        })
        people = self.graph.recent_people(hours=1)
        self.assertTrue(people, "No person entity created")

        # The entity label might be 'visible person' or 'person' depending on parser
        entity = people[0]
        label = entity["label"]
        link_result = self.graph.link_person_name(label, "Alice Smith")
        self.assertNotIn("error", link_result, f"link_person_name failed: {link_result}")

        real_name = self.graph.get_entity_attribute(entity["id"], "real_name")
        self.assertEqual(real_name, "Alice Smith")


class TestRecallFirewallRealNames(unittest.TestCase):
    """Bug 4: RecallFirewall resolves real names — never exposes internal entity UUIDs."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.graph = _make_graph(self.tmp)
        self.store = _make_store(self.tmp)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _seed_named_person(self, real_name: str = "Bob Jones") -> dict:
        """Ingest a person observation and link a real name. Returns the entity."""
        self.graph.ingest_packet({
            "memory_text": "OBJECT | visible person | person tracked by local detector | detector stream | likely",
            "source_type": "vision",
            "provider": "detector",
            "scene_phase": "active",
        })
        people = self.graph.recent_people(hours=1)
        self.assertTrue(people, "No person entity was created during seeding")
        entity = people[0]
        result = self.graph.link_person_name(entity["label"], real_name)
        self.assertNotIn("error", result, f"link_person_name failed: {result}")
        return entity

    def test_graph_people_today_returns_real_name(self) -> None:
        """_graph_people_today must return real name, not UUID or 'unknown person'."""
        self._seed_named_person("Carol White")
        firewall = RecallFirewall(self.store, self.graph)
        result = firewall._graph_people_today()

        self.assertIsNotNone(result, "_graph_people_today returned None after seeding")
        answer = result["answer"]
        self.assertIn("Carol White", answer,
                      f"Real name not in answer. Got: {answer!r}")
        # Must never expose raw UUIDs
        self.assertNotRegex(answer, r"[0-9a-f]{8}-[0-9a-f]{4}-",
                            "Answer contains a UUID — internal ID leaked!")

    def test_graph_people_today_unknown_person_when_no_name_linked(self) -> None:
        """Without link_person_name, person appears as 'unknown person', not UUID."""
        self.graph.ingest_packet({
            "memory_text": "OBJECT | visible person | person detected | detector stream | likely",
            "source_type": "vision",
            "provider": "detector",
            "scene_phase": "active",
        })
        firewall = RecallFirewall(self.store, self.graph)
        result = firewall._graph_people_today()

        self.assertIsNotNone(result)
        answer = result["answer"]
        self.assertIn("unknown person", answer,
                      f"Unnamed person should show as 'unknown person', got: {answer!r}")
        # Still must not expose UUID
        self.assertNotRegex(answer, r"[0-9a-f]{8}-[0-9a-f]{4}-",
                            "Answer contains a UUID — internal ID leaked!")

    def test_answer_who_did_i_see_returns_real_name(self) -> None:
        """High-level answer() for 'who did I see' must route through graph and resolve name."""
        self._seed_named_person("Diana Prince")
        firewall = RecallFirewall(self.store, self.graph)
        result = firewall.answer("who did I see today?")

        self.assertIsNotNone(result)
        # The answer should mention the real name
        self.assertIn("Diana Prince", result["answer"],
                      f"Real name not in answer. Got: {result['answer']!r}")

    def test_used_private_memory_flag_is_true(self) -> None:
        """Graph-sourced answers must set used_private_memory=True."""
        self._seed_named_person("Eve Adams")
        firewall = RecallFirewall(self.store, self.graph)
        result = firewall._graph_people_today()

        self.assertIsNotNone(result)
        self.assertTrue(result.get("used_private_memory"),
                        "Graph answers must set used_private_memory=True")


if __name__ == "__main__":
    unittest.main()
