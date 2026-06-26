#!/usr/bin/env python3
"""Persistent cross-session memory for the TRACE brain.

Every capture session writes ephemeral kf_memory.json. This module accumulates
facts into a durable SQLite store so the brain can answer from ALL past sessions,
not just the current one.

Design (from the blueprint):
- Never delete. Decay = retrieval cost, not deletion.
- Hot in-memory set for the current session; cold SQLite store for everything.
- Per-fact-type validity: a building plaque is durable, a clock reading is volatile.
- Stale volatile facts demote from "assertable" to "last seen at T".
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL,
    t           REAL    NOT NULL,
    source      TEXT    NOT NULL,
    kind        TEXT    NOT NULL DEFAULT 'observation',
    caption     TEXT    NOT NULL,
    entity      TEXT,
    confidence  REAL    NOT NULL DEFAULT 0.5,
    created_at  REAL    NOT NULL,
    durability  TEXT    NOT NULL DEFAULT 'volatile'
);
CREATE INDEX IF NOT EXISTS idx_facts_entity ON facts(entity);
CREATE INDEX IF NOT EXISTS idx_facts_session ON facts(session_id);
CREATE INDEX IF NOT EXISTS idx_facts_kind ON facts(kind);

CREATE TABLE IF NOT EXISTS entities (
    name        TEXT    PRIMARY KEY,
    kind        TEXT    NOT NULL DEFAULT 'unknown',
    first_seen  REAL    NOT NULL,
    last_seen   REAL    NOT NULL,
    times_seen  INTEGER NOT NULL DEFAULT 1,
    attributes  TEXT    NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id  TEXT    PRIMARY KEY,
    started_at  REAL    NOT NULL,
    ended_at    REAL,
    location    TEXT,
    summary     TEXT,
    fact_count  INTEGER NOT NULL DEFAULT 0
);
"""

_DURABLE_KINDS = {"place", "person", "brand", "building", "sign"}
_VOLATILE_KINDS = {"screen", "time", "weather", "occupancy", "notification"}

_ENTITY_PATTERN = re.compile(
    r'(?:name|brand|label|text)=?"([^"]{2,60})"', re.IGNORECASE
)
_QUOTED_NAME = re.compile(r'"([A-Z][A-Za-z0-9 &\'-]{1,40})"')


def _db_path(data_dir: Path) -> Path:
    return data_dir / "brain_memory.db"


def open_db(data_dir: Path) -> sqlite3.Connection:
    # check_same_thread=False: the brain server opens this connection once and
    # uses it from multiple HTTP handler threads (capture vs ask). WAL + the
    # busy_timeout serialize concurrent access safely for our low-QPS,
    # after-the-moment workload. Without this, cross-thread recall() raised
    # "SQLite objects created in a thread can only be used in that same thread".
    db = sqlite3.connect(str(_db_path(data_dir)), timeout=5, check_same_thread=False)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=3000")
    db.executescript(_SCHEMA)
    return db


def ingest_session(
    db: sqlite3.Connection,
    session_id: str,
    kf_records: list[dict[str, Any]],
    location: str | None = None,
) -> dict[str, Any]:
    """Promote a session's kf_memory records into durable storage."""
    now = time.time()

    db.execute(
        "INSERT OR REPLACE INTO sessions (session_id, started_at, location, fact_count) "
        "VALUES (?, ?, ?, ?)",
        (session_id, now, location, len(kf_records)),
    )

    entities_seen: dict[str, dict[str, Any]] = {}
    facts_inserted = 0

    for rec in kf_records:
        cap = str(rec.get("caption", ""))
        if not cap or len(cap) < 10:
            continue

        t = float(rec.get("t", 0))
        source = str(rec.get("source", "unknown"))
        kind = _classify_kind(cap, source)
        durability = "durable" if kind in _DURABLE_KINDS else "volatile"
        confidence = _estimate_confidence(rec, source)

        entity_names = _extract_entities(cap)

        for entity in entity_names:
            if entity not in entities_seen:
                entities_seen[entity] = {
                    "kind": kind,
                    "first_t": t,
                    "last_t": t,
                    "count": 0,
                }
            entities_seen[entity]["last_t"] = max(entities_seen[entity]["last_t"], t)
            entities_seen[entity]["count"] += 1

        db.execute(
            "INSERT INTO facts (session_id, t, source, kind, caption, entity, "
            "confidence, created_at, durability) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                t,
                source,
                kind,
                cap[:2000],
                "; ".join(entity_names)[:200] if entity_names else None,
                confidence,
                now,
                durability,
            ),
        )
        facts_inserted += 1

    for name, info in entities_seen.items():
        db.execute(
            "INSERT INTO entities (name, kind, first_seen, last_seen, times_seen) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET "
            "last_seen = MAX(last_seen, excluded.last_seen), "
            "times_seen = times_seen + excluded.times_seen",
            (name, info["kind"], now, now, info["count"]),
        )

    db.commit()
    return {
        "session_id": session_id,
        "facts_stored": facts_inserted,
        "entities_found": len(entities_seen),
        "entity_names": list(entities_seen.keys())[:20],
    }


def recall(
    db: sqlite3.Connection,
    question: str,
    limit: int = 12,
    current_session: str | None = None,
) -> list[dict[str, Any]]:
    """Search long-term memory for facts relevant to a question.

    Uses keyword matching against captions and entity names. Returns facts
    sorted by relevance, excluding the current session (which is already
    in kf_memory).
    """
    q_lower = question.lower()
    words = set(re.split(r"\W+", q_lower)) - {
        "", "the", "a", "an", "is", "are", "was", "were", "did", "do",
        "does", "what", "how", "many", "which", "who", "where", "when",
        "my", "i", "me", "you", "your", "we", "there", "any", "on",
        "in", "of", "it", "to", "for", "at", "by", "with", "from",
        "about", "that", "this", "have", "has", "had", "s",
    }
    if not words:
        return []

    like_clauses = " OR ".join(["LOWER(caption) LIKE ?"] * len(words))
    params: list[Any] = [f"%{w}%" for w in words]

    if current_session:
        where = f"({like_clauses}) AND session_id != ?"
        params.append(current_session)
    else:
        where = f"({like_clauses})"

    rows = db.execute(
        f"SELECT session_id, t, source, kind, caption, entity, confidence, "
        f"durability, created_at FROM facts WHERE {where} "
        f"ORDER BY confidence DESC, created_at DESC LIMIT ?",
        params + [limit * 3],
    ).fetchall()

    scored = []
    for row in rows:
        cap_lower = row[4].lower()
        hits = sum(1 for w in words if w in cap_lower)
        score = hits / max(len(words), 1)
        if row[7] == "durable":
            score *= 1.5
        scored.append((score, row))

    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, row in scored[:limit]:
        results.append({
            "session_id": row[0],
            "t": row[1],
            "source": row[2],
            "kind": row[3],
            "caption": row[4],
            "entity": row[5],
            "confidence": row[6],
            "durability": row[7],
            "stored_at": row[8],
            "relevance": round(score, 2),
        })
    return results


def known_entities(db: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    """Return the most-seen entities across all sessions."""
    rows = db.execute(
        "SELECT name, kind, first_seen, last_seen, times_seen "
        "FROM entities ORDER BY times_seen DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        {"name": r[0], "kind": r[1], "first_seen": r[2],
         "last_seen": r[3], "times_seen": r[4]}
        for r in rows
    ]


def session_count(db: sqlite3.Connection) -> int:
    return db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]


def _classify_kind(caption: str, source: str) -> str:
    cap_lower = caption.lower()
    if source == "native_speech":
        return "speech"
    if "display screen" in cap_lower or "on_screen" in cap_lower:
        return "screen"
    for marker, kind in [
        ("speaker", "object"), ("keyboard", "object"), ("laptop", "object"),
        ("person", "person"), ("face", "person"),
        ("street", "place"), ("building", "place"), ("sign", "sign"),
    ]:
        if marker in cap_lower:
            return kind
    if "INSTANCES" in caption[:30]:
        return "scene"
    return "observation"


def _estimate_confidence(rec: dict[str, Any], source: str) -> float:
    if source == "mac_vision":
        return 0.85
    if source == "instance_pipeline":
        return 0.9
    if source == "native_vision":
        return 0.5
    if source == "native_speech":
        return 0.7
    return 0.4


def _extract_entities(caption: str) -> list[str]:
    """Pull entity names from a caption heuristically."""
    entities = set()
    for m in _QUOTED_NAME.finditer(caption):
        name = m.group(1).strip()
        if len(name) > 2 and name.lower() not in {"none", "unknown", "object"}:
            entities.add(name)
    for m in _ENTITY_PATTERN.finditer(caption):
        name = m.group(1).strip()
        if len(name) > 2:
            entities.add(name)
    return sorted(entities)


if __name__ == "__main__":
    import sys

    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/phone_captures")
    db = open_db(data_dir)

    live_kf = data_dir / "live" / "kf_memory.json"
    if live_kf.exists():
        kf = json.load(open(live_kf))
        result = ingest_session(db, f"live_{int(time.time())}", kf)
        print(f"Ingested: {result['facts_stored']} facts, {result['entities_found']} entities")
        print(f"Entities: {result['entity_names']}")
    else:
        print("No live kf_memory.json found")

    print(f"\nTotal sessions: {session_count(db)}")
    print(f"\nKnown entities:")
    for e in known_entities(db, 10):
        print(f"  {e['name']} ({e['kind']}) — seen {e['times_seen']}x")
