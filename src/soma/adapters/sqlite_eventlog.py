"""Append-only SQLite event-log adapter.

The capture core is event-sourced: every perceiver emission is appended here
as an immutable row, in arrival order. This is the single source of truth that
projections (binder, recall index) are derived from, and it gives provenance,
deterministic replay, and audit for free. The public API has no update or
delete -- events are immutable once written.
"""

from __future__ import annotations

import json
import sqlite3

from soma.domain.confidence import Confidence
from soma.domain.observation import Attribute, Observation
from soma.domain.provenance import Provenance

_SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    seq            INTEGER PRIMARY KEY AUTOINCREMENT,
    kind           TEXT    NOT NULL,
    subject        TEXT    NOT NULL,
    attributes     TEXT    NOT NULL,
    t_ms           INTEGER NOT NULL,
    spatial_anchor TEXT,
    confidence     REAL    NOT NULL,
    event_id       TEXT    NOT NULL,
    source_channel TEXT    NOT NULL,
    captured_at_ms INTEGER NOT NULL,
    refutation_cue TEXT
)
"""

_INSERT = (
    "INSERT INTO observations "
    "(kind, subject, attributes, t_ms, spatial_anchor, confidence, "
    "event_id, source_channel, captured_at_ms, refutation_cue) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


def _encode_attributes(attributes: tuple[Attribute, ...]) -> str:
    return json.dumps([(a.name, a.value) for a in attributes])


def _decode_attributes(raw: str) -> tuple[Attribute, ...]:
    pairs: list[tuple[str, str]] = json.loads(raw)
    return tuple(Attribute(name, value) for name, value in pairs)


def _row_to_observation(row: sqlite3.Row) -> Observation:
    return Observation(
        kind=row["kind"],
        subject=row["subject"],
        attributes=_decode_attributes(row["attributes"]),
        t_ms=row["t_ms"],
        spatial_anchor=row["spatial_anchor"],
        confidence=Confidence(row["confidence"]),
        provenance=Provenance(
            event_id=row["event_id"],
            source_channel=row["source_channel"],
            captured_at_ms=row["captured_at_ms"],
        ),
        refutation_cue=row["refutation_cue"],
    )


class SqliteEventLog:
    """Append-only observation log backed by SQLite. Implements MemoryStore."""

    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def append(self, observation: Observation) -> None:
        prov = observation.provenance
        self._conn.execute(
            _INSERT,
            (
                observation.kind,
                observation.subject,
                _encode_attributes(observation.attributes),
                observation.t_ms,
                observation.spatial_anchor,
                observation.confidence.value,
                prov.event_id,
                prov.source_channel,
                prov.captured_at_ms,
                observation.refutation_cue,
            ),
        )
        self._conn.commit()

    def observations(self) -> tuple[Observation, ...]:
        rows = self._conn.execute("SELECT * FROM observations ORDER BY seq ASC").fetchall()
        return tuple(_row_to_observation(row) for row in rows)

    def close(self) -> None:
        self._conn.close()
