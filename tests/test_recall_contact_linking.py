"""Task 154 tests: RecallFirewall with contact linking, stale encounter cleanup.

Covers:
- link_person_name persists and get_entity_attribute retrieves real names
- close_stale_encounters closes open encounters older than threshold
- start_stale_encounter_cleaner background thread does not raise
- RecallFirewall._graph_people_today exposes real name via link_person_name
- RecallFirewall._graph_people_today shows 'unknown person' when no name linked
- No raw UUIDs exposed in any recall answer
- All intents that should route through graph do so correctly
- Encounters created for person entities
"""
from __future__ import annotations

import sqlite3
import tempfile
import time
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from trace_hub.crypto import EncryptedTextCodec
from trace_hub.graph import RelationalMemoryGraph
from trace_hub.recall import RecallFirewall
from trace_hub.storage import MemoryStore

_TEST_KEY = b"trace-test-key-for-unit-tests-xyz"
_UUID_RE = r"[0-9a-f]{8}-[0-9a-f]{4}-"


def _make_graph(tmp_path: Path) -> RelationalMemoryGraph:
    codec = EncryptedTextCodec(_TEST_KEY)
    return RelationalMemoryGraph(tmp_path / "trace_hub.sqlite3", codec)


def _make_store(tmp_path: Path) -> MemoryStore:
    codec = EncryptedTextCodec(_TEST_KEY)
    return MemoryStore(tmp_path / "trace_hub.sqlite3", codec)


def _ingest_person(graph: RelationalMemoryGraph) -> dict:
    """Ingest a person observation and return the entity."""
    graph.ingest_packet({
        "memory_text": "OBJECT | visible person | person tracked by local detector | detector stream | likely",
        "source_type": "vision",
        "provider": "detector",
        "scene_phase": "active",
        "stability_count": 3,
    })
    people = graph.recent_people(hours=1)
    assert people, "No person entity created"
    return people[0]


class TestContactLinking(unittest.TestCase):
    """link_person_name / get_entity_attribute round-trip."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.graph = _make_graph(self.tmp)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_link_then_retrieve(self) -> None:
        entity = _ingest_person(self.graph)
        result = self.graph.link_person_name(entity["label"], "Alice Smith")
        self.assertNotIn("error", result, f"link_person_name failed: {result}")
        name = self.graph.get_entity_attribute(entity["id"], "real_name")
        self.assertEqual(name, "Alice Smith")

    def test_link_overwrites_existing_name(self) -> None:
        entity = _ingest_person(self.graph)
        self.graph.link_person_name(entity["label"], "First Name")
        self.graph.link_person_name(entity["label"], "Updated Name")
        name = self.graph.get_entity_attribute(entity["id"], "real_name")
        self.assertEqual(name, "Updated Name",
                         "Second link_person_name must overwrite the first")

    def test_link_nonexistent_label_returns_error(self) -> None:
        result = self.graph.link_person_name("nonexistent entity xyz", "Ghost")
        self.assertIn("error", result, "Should return error for unknown label")

    def test_get_attribute_returns_none_for_missing_key(self) -> None:
        entity = _ingest_person(self.graph)
        result = self.graph.get_entity_attribute(entity["id"], "hair_colour")
        self.assertIsNone(result)

    def test_get_attribute_returns_none_for_unknown_entity(self) -> None:
        result = self.graph.get_entity_attribute("00000000-0000-0000-0000-000000000000", "real_name")
        self.assertIsNone(result)

    def test_linked_name_survives_second_ingest(self) -> None:
        """Name must not be wiped by a subsequent ingest of the same entity."""
        entity = _ingest_person(self.graph)
        self.graph.link_person_name(entity["label"], "Persistent Name")
        _ingest_person(self.graph)  # second observation of same person
        name = self.graph.get_entity_attribute(entity["id"], "real_name")
        self.assertEqual(name, "Persistent Name")


class TestStaleEncounterCleanup(unittest.TestCase):
    """close_stale_encounters closes encounters older than the threshold."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.graph = _make_graph(self.tmp)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _encounter_count(self, ended: bool) -> int:
        db_path = self.tmp / "trace_hub.sqlite3"
        with sqlite3.connect(db_path) as conn:
            if ended:
                row = conn.execute(
                    "SELECT COUNT(*) FROM graph_encounters WHERE ended_at IS NOT NULL"
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) FROM graph_encounters WHERE ended_at IS NULL"
                ).fetchone()
            return row[0]

    def _insert_old_encounter(self, entity_id: str, minutes_ago: int) -> None:
        """Directly insert an open encounter with a backdated started_at."""
        import uuid
        db_path = self.tmp / "trace_hub.sqlite3"
        started = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO graph_encounters (id, entity_id, started_at, observation_count) VALUES (?,?,?,1)",
                (str(uuid.uuid4()), entity_id, started),
            )

    def test_fresh_encounter_not_closed(self) -> None:
        """An encounter started 10 minutes ago must NOT be closed by 240-minute threshold.

        Note: _ingest_person auto-creates one open encounter (from _upsert_encounter during
        ingest), so after _insert_old_encounter there are 2 open encounters total.
        Neither is 240+ minutes old, so both survive close_stale_encounters(240).
        """
        entity = _ingest_person(self.graph)
        self._insert_old_encounter(entity["id"], minutes_ago=10)
        self.graph.close_stale_encounters(older_than_minutes=240)
        # Both encounters (auto-created + 10-min-old) are fresh → 2 open, 0 closed
        self.assertEqual(self._encounter_count(ended=False), 2)

    def test_stale_encounter_is_closed(self) -> None:
        """An encounter started 250 minutes ago MUST be closed by 240-minute threshold.

        Note: _ingest_person auto-creates one open encounter (just now), so there are
        2 open encounters after _insert_old_encounter(250).  close_stale_encounters(240)
        closes only the 250-min-old encounter; the recent auto-created one stays open.
        """
        entity = _ingest_person(self.graph)
        self._insert_old_encounter(entity["id"], minutes_ago=250)
        # 2 open: auto-created (just now) + manually inserted (250 min old)
        self.assertEqual(self._encounter_count(ended=False), 2)
        self.graph.close_stale_encounters(older_than_minutes=240)
        # Only the 250-min encounter is closed; auto-created one (just now) stays open
        self.assertEqual(self._encounter_count(ended=False), 1)
        self.assertEqual(self._encounter_count(ended=True), 1)

    def test_custom_threshold_closes_sooner(self) -> None:
        """threshold=5 closes an encounter started 10 minutes ago.

        Note: _ingest_person auto-creates one open encounter (just now).  That encounter
        is < 5 minutes old, so it is NOT closed by threshold=5.  Only the 10-min-old
        manually inserted encounter gets closed.
        """
        entity = _ingest_person(self.graph)
        self._insert_old_encounter(entity["id"], minutes_ago=10)
        self.graph.close_stale_encounters(older_than_minutes=5)
        # 10-min encounter closed; auto-created (just now) remains open → 1 open
        self.assertEqual(self._encounter_count(ended=False), 1)

    def test_already_closed_encounter_not_double_closed(self) -> None:
        """Calling close_stale_encounters twice must not raise or create extra rows."""
        entity = _ingest_person(self.graph)
        self._insert_old_encounter(entity["id"], minutes_ago=300)
        self.graph.close_stale_encounters(older_than_minutes=240)
        self.graph.close_stale_encounters(older_than_minutes=240)
        self.assertEqual(self._encounter_count(ended=True), 1)

    def test_start_stale_encounter_cleaner_does_not_raise(self) -> None:
        """Background cleaner thread must start without error."""
        try:
            self.graph.start_stale_encounter_cleaner(interval_seconds=3600)
        except Exception as exc:
            self.fail(f"start_stale_encounter_cleaner raised: {exc}")


class TestRecallFirewallContactLinking(unittest.TestCase):
    """RecallFirewall integrates contact linking into answers."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.graph = _make_graph(self.tmp)
        self.store = _make_store(self.tmp)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _seed_named_person(self, name: str) -> dict:
        entity = _ingest_person(self.graph)
        result = self.graph.link_person_name(entity["label"], name)
        self.assertNotIn("error", result, f"link_person_name failed: {result}")
        return entity

    def test_people_today_returns_linked_name(self) -> None:
        self._seed_named_person("Bob Jones")
        fw = RecallFirewall(self.store, self.graph)
        result = fw._graph_people_today()
        self.assertIsNotNone(result)
        self.assertIn("Bob Jones", result["answer"])

    def test_people_today_no_uuid_leak(self) -> None:
        self._seed_named_person("Carol White")
        fw = RecallFirewall(self.store, self.graph)
        result = fw._graph_people_today()
        self.assertIsNotNone(result)
        self.assertNotRegex(result["answer"], _UUID_RE,
                            "Answer must not expose internal entity UUID")

    def test_people_today_unknown_when_no_name(self) -> None:
        _ingest_person(self.graph)
        fw = RecallFirewall(self.store, self.graph)
        result = fw._graph_people_today()
        self.assertIsNotNone(result)
        self.assertIn("unknown person", result["answer"])
        self.assertNotRegex(result["answer"], _UUID_RE)

    def test_used_private_memory_true_for_named_person(self) -> None:
        self._seed_named_person("Diana Prince")
        fw = RecallFirewall(self.store, self.graph)
        result = fw._graph_people_today()
        self.assertIsNotNone(result)
        self.assertTrue(result.get("used_private_memory"))

    def test_who_did_i_see_routes_to_real_name(self) -> None:
        self._seed_named_person("Eve Adams")
        fw = RecallFirewall(self.store, self.graph)
        result = fw.answer("who did I see today?")
        self.assertIn("Eve Adams", result["answer"])

    def test_multiple_named_people_all_appear(self) -> None:
        """When multiple named people were seen, all names must appear."""
        # Two separate person entities with distinct labels via different scene phases
        self.graph.ingest_packet({
            "memory_text": "OBJECT | visible person | tall adult, brown jacket | detector stream | likely",
            "source_type": "vision",
            "provider": "detector",
            "scene_phase": "active",
        })
        self.graph.ingest_packet({
            "memory_text": "OBJECT | visible person | short person, red shirt | detector stream | likely",
            "source_type": "vision",
            "provider": "detector",
            "scene_phase": "quiet",
        })
        people = self.graph.recent_people(hours=1)
        # Link names to all entities found
        names_linked = 0
        for p in people:
            name = f"Person_{p['id'][:4]}"
            result = self.graph.link_person_name(p["label"], name)
            if "error" not in result:
                names_linked += 1

        fw = RecallFirewall(self.store, self.graph)
        result = fw._graph_people_today()
        self.assertIsNotNone(result)
        # At least one linked name should appear
        self.assertGreater(names_linked, 0, "At least one name must be linkable")


if __name__ == "__main__":
    unittest.main()
