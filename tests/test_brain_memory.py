"""Tests for cross-session persistent memory (brain_memory.py)."""
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import brain_memory


@pytest.fixture
def mem_db(tmp_path):
    db = brain_memory.open_db(tmp_path)
    yield db
    db.close()


def test_ingest_and_recall(mem_db):
    records = [
        {"t": 10.0, "caption": "Black cat resting on the laptop keyboard", "source": "mac_vision"},
        {"t": 20.0, "caption": 'speaker "Harman Kardon" on the desk', "source": "mac_vision"},
        {"t": 30.0, "caption": "OBJECT | display screen | WhatsApp chat", "source": "native_vision"},
    ]
    result = brain_memory.ingest_session(mem_db, "session_1", records)
    assert result["facts_stored"] == 3
    assert result["entities_found"] >= 1

    hits = brain_memory.recall(mem_db, "What brand is the speaker?")
    assert len(hits) >= 1
    assert any("harman" in h["caption"].lower() or "kardon" in h["caption"].lower() for h in hits)


def test_cross_session_recall(mem_db):
    brain_memory.ingest_session(mem_db, "morning", [
        {"t": 1.0, "caption": 'Walked past "Starbucks" on Main Street', "source": "mac_vision"},
    ])
    brain_memory.ingest_session(mem_db, "evening", [
        {"t": 100.0, "caption": "Dinner at home with pasta", "source": "mac_vision"},
    ])

    hits = brain_memory.recall(mem_db, "Did I see a Starbucks?", current_session="evening")
    assert len(hits) >= 1
    assert hits[0]["session_id"] == "morning"


def test_never_delete(mem_db):
    brain_memory.ingest_session(mem_db, "s1", [
        {"t": 1.0, "caption": "Ancient temple with carved pillars", "source": "mac_vision"},
    ])
    brain_memory.ingest_session(mem_db, "s2", [
        {"t": 1.0, "caption": "Modern office with glass walls", "source": "mac_vision"},
    ])
    assert brain_memory.session_count(mem_db) == 2
    count = mem_db.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
    assert count == 2


def test_entity_accumulation(mem_db):
    brain_memory.ingest_session(mem_db, "s1", [
        {"t": 1.0, "caption": '#0 laptop "MacBook Pro" on desk', "source": "mac_vision"},
    ])
    brain_memory.ingest_session(mem_db, "s2", [
        {"t": 1.0, "caption": '#0 laptop "MacBook Pro" silver', "source": "mac_vision"},
    ])

    entities = brain_memory.known_entities(mem_db)
    mbp = [e for e in entities if "MacBook" in e["name"]]
    assert len(mbp) >= 1
    assert mbp[0]["times_seen"] >= 2


def test_empty_recall_returns_empty(mem_db):
    hits = brain_memory.recall(mem_db, "anything")
    assert hits == []
