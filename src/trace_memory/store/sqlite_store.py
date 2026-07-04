from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from trace_memory.contract import best_grade, normalize_grade
from trace_memory.store.embeddings import TextEmbedder, build_default_embedder
from trace_memory.store.models import (
    AbstractionRecord,
    AnchorRecord,
    CoordinateFrame,
    LinkRecord,
    MemoryNode,
    NeighborRecord,
    SearchHit,
    SearchSlice,
    SpatialAnchor,
    TimeRange,
)

# P11: the same/different cut for appearance fingerprints. This is a SYNTHETIC default — the
# real threshold is measured from the ROC on ≥20 real object pairs during the device walk
# (packet P11) and pasted back. Legislating it before that measurement would be a lie; this
# value only keeps `same_appearance` callable until the walk sets it honestly.
FINGERPRINT_MATCH_THRESHOLD = 0.82

_NODE_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_nodes (
    seq             INTEGER PRIMARY KEY AUTOINCREMENT,
    id              TEXT NOT NULL UNIQUE,
    t_ms            INTEGER NOT NULL,
    node_type       TEXT NOT NULL,
    source          TEXT NOT NULL,
    helper_type     TEXT,
    coordinate_frame_json TEXT NOT NULL DEFAULT '{}',
    time_range_json TEXT NOT NULL DEFAULT '{}',
    spatial_anchor_json TEXT NOT NULL DEFAULT '{}',
    source_support_json TEXT NOT NULL DEFAULT '{}',
    place           TEXT,
    pose_json       TEXT NOT NULL,
    text            TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    metadata_json   TEXT NOT NULL,
    derived         INTEGER NOT NULL,
    immutable_raw   INTEGER NOT NULL DEFAULT 0,
    embedding_json  TEXT NOT NULL
)
"""

_LINK_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_links (
    seq           INTEGER PRIMARY KEY AUTOINCREMENT,
    id            TEXT NOT NULL UNIQUE,
    from_id       TEXT NOT NULL,
    to_id         TEXT NOT NULL,
    link_type     TEXT NOT NULL,
    weight        REAL NOT NULL,
    metadata_json TEXT NOT NULL
)
"""

# P10: the coordinate anchor substrate. One row per pinned spot; additive and idempotent so
# a store full of pre-P10 rows keeps working (those rows simply have no anchor).
_ANCHOR_SCHEMA = """
CREATE TABLE IF NOT EXISTS anchors (
    anchor_id       TEXT PRIMARY KEY,
    room            TEXT,
    first_session   TEXT,
    last_session    TEXT,
    first_seen_ms   INTEGER NOT NULL,
    last_seen_ms    INTEGER NOT NULL,
    grade           TEXT NOT NULL DEFAULT 'none',
    session_count   INTEGER NOT NULL DEFAULT 1,
    sightings       INTEGER NOT NULL DEFAULT 1,
    pose_json       TEXT NOT NULL DEFAULT '{}'
)
"""

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_memory_nodes_type_t ON memory_nodes(node_type, t_ms)",
    "CREATE INDEX IF NOT EXISTS idx_memory_nodes_place ON memory_nodes(place)",
    "CREATE INDEX IF NOT EXISTS idx_memory_nodes_helper ON memory_nodes(helper_type)",
    "CREATE INDEX IF NOT EXISTS idx_memory_links_from ON memory_links(from_id)",
    "CREATE INDEX IF NOT EXISTS idx_memory_links_to ON memory_links(to_id)",
    "CREATE INDEX IF NOT EXISTS idx_memory_links_type ON memory_links(link_type)",
    "CREATE INDEX IF NOT EXISTS idx_anchors_room ON anchors(room)",
    "CREATE INDEX IF NOT EXISTS idx_anchors_grade ON anchors(grade)",
)

_MIGRATION_COLUMNS = {
    "helper_type": "ALTER TABLE memory_nodes ADD COLUMN helper_type TEXT",
    "coordinate_frame_json": "ALTER TABLE memory_nodes ADD COLUMN coordinate_frame_json TEXT NOT NULL DEFAULT '{}'",
    "time_range_json": "ALTER TABLE memory_nodes ADD COLUMN time_range_json TEXT NOT NULL DEFAULT '{}'",
    "spatial_anchor_json": "ALTER TABLE memory_nodes ADD COLUMN spatial_anchor_json TEXT NOT NULL DEFAULT '{}'",
    "source_support_json": "ALTER TABLE memory_nodes ADD COLUMN source_support_json TEXT NOT NULL DEFAULT '{}'",
    "immutable_raw": "ALTER TABLE memory_nodes ADD COLUMN immutable_raw INTEGER NOT NULL DEFAULT 0",
}


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if not left or not right:
        return 0.0
    lv = np.asarray(left, dtype=np.float32)
    rv = np.asarray(right, dtype=np.float32)
    denom = float(np.linalg.norm(lv) * np.linalg.norm(rv))
    if denom <= 0.0:
        return 0.0
    return float(np.dot(lv, rv) / denom)


def _lexical_overlap(query: str, text: str) -> float:
    q = {token for token in query.lower().split() if token}
    t = {token for token in text.lower().split() if token}
    if not q or not t:
        return 0.0
    return len(q & t) / len(q)


def _row_to_node(row: sqlite3.Row) -> MemoryNode:
    coordinate_frame = json.loads(row["coordinate_frame_json"]) if "coordinate_frame_json" in row.keys() else {}
    time_range = json.loads(row["time_range_json"]) if "time_range_json" in row.keys() else {}
    spatial_anchor = json.loads(row["spatial_anchor_json"]) if "spatial_anchor_json" in row.keys() else {}
    source_support = json.loads(row["source_support_json"]) if "source_support_json" in row.keys() else {}
    return MemoryNode(
        id=row["id"],
        t_ms=row["t_ms"],
        node_type=row["node_type"],
        source=row["source"],
        helper_type=row["helper_type"] if "helper_type" in row.keys() else None,
        coordinate_frame=CoordinateFrame.from_value(coordinate_frame) if coordinate_frame else None,
        time_range=TimeRange.from_value(time_range, default_t_ms=row["t_ms"]) if time_range else None,
        spatial_anchor=SpatialAnchor.from_value(spatial_anchor) if spatial_anchor else None,
        source_support=source_support or {},
        place=row["place"],
        pose=json.loads(row["pose_json"]),
        text=row["text"],
        provenance=json.loads(row["provenance_json"]),
        metadata=json.loads(row["metadata_json"]),
        derived=bool(row["derived"]),
        immutable_raw=bool(row["immutable_raw"]) if "immutable_raw" in row.keys() else False,
        embedding=tuple(float(value) for value in json.loads(row["embedding_json"])),
    )


def _row_to_link(row: sqlite3.Row) -> LinkRecord:
    return LinkRecord(
        id=row["id"],
        from_id=row["from_id"],
        to_id=row["to_id"],
        link_type=row["link_type"],
        weight=float(row["weight"]),
        metadata=json.loads(row["metadata_json"]),
    )


class TraceMemoryStore:
    def __init__(self, path: str | Path, *, embedder: TextEmbedder | None = None) -> None:
        self.path = str(path)
        self._embedder = embedder or build_default_embedder()
        # check_same_thread=False: the hub serves requests from ThreadingHTTPServer worker
        # threads and serializes EVERY store access behind one lock (scripts/trace_hub.py).
        # Without this flag each request thread died on sqlite's thread-affinity check and
        # the demo surface answered only its error fallback (caught by the M7 hammer).
        # Any new multi-threaded caller must bring its own serialization.
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # WAL lets a separate READER connection (the hub's answer path) run concurrently with
        # this writer, so a 30s answer never blocks the phone's frame uploads (the demo hang).
        # Best-effort: :memory: and some filesystems reject WAL — fall back silently.
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
        except sqlite3.OperationalError:
            pass
        self._conn.execute(_NODE_SCHEMA)
        self._conn.execute(_LINK_SCHEMA)
        self._conn.execute(_ANCHOR_SCHEMA)
        self._migrate_schema()
        for statement in _INDEXES:
            self._conn.execute(statement)
        self._conn.commit()

    def _migrate_schema(self) -> None:
        existing = {
            str(row["name"])
            for row in self._conn.execute("PRAGMA table_info(memory_nodes)").fetchall()
        }
        for column, statement in _MIGRATION_COLUMNS.items():
            if column not in existing:
                self._conn.execute(statement)

    def close(self) -> None:
        self._conn.close()

    @property
    def retrieval_mode(self) -> str:
        return str(getattr(self._embedder, "mode", "semantic"))

    def write_observation(
        self,
        *,
        text: str,
        t_ms: int,
        source: str,
        provenance: dict[str, Any],
        helper_type: str | None = None,
        coordinate_frame: CoordinateFrame | dict[str, Any] | None = None,
        time_range: TimeRange | dict[str, Any] | None = None,
        spatial_anchor: SpatialAnchor | dict[str, Any] | None = None,
        source_support: dict[str, Any] | None = None,
        place: str | None = None,
        pose: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        node_type: str = "observation",
        derived: bool = False,
        immutable_raw: bool = False,
        node_id: str | None = None,
    ) -> MemoryNode:
        embedding = self._embedder.embed([text])[0]
        node = MemoryNode(
            id=node_id or str(uuid.uuid4()),
            t_ms=t_ms,
            node_type=node_type,
            source=source,
            helper_type=helper_type,
            coordinate_frame=CoordinateFrame.from_value(coordinate_frame) if coordinate_frame is not None else None,
            time_range=TimeRange.from_value(time_range, default_t_ms=t_ms),
            spatial_anchor=SpatialAnchor.from_value(spatial_anchor) if spatial_anchor is not None else None,
            source_support=source_support or {},
            place=place,
            pose=pose,
            text=text,
            provenance=provenance,
            metadata=metadata or {},
            derived=derived,
            immutable_raw=immutable_raw,
            embedding=embedding,
        )
        self._conn.execute(
            """
            INSERT INTO memory_nodes
            (id, t_ms, node_type, source, helper_type, coordinate_frame_json, time_range_json,
             spatial_anchor_json, source_support_json, place, pose_json, text, provenance_json,
             metadata_json, derived, immutable_raw, embedding_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node.id,
                node.t_ms,
                node.node_type,
                node.source,
                node.helper_type,
                _json_dump(node.coordinate_frame.to_dict() if node.coordinate_frame is not None else {}),
                _json_dump(node.time_range.to_dict() if node.time_range is not None else {}),
                _json_dump(node.spatial_anchor.to_dict() if node.spatial_anchor is not None else {}),
                _json_dump(node.source_support),
                node.place,
                _json_dump(node.pose),
                node.text,
                _json_dump(node.provenance),
                _json_dump(node.metadata),
                int(node.derived),
                int(node.immutable_raw),
                _json_dump(list(node.embedding)),
            ),
        )
        self._conn.commit()
        return node

    def write_canonical_observation(
        self,
        *,
        text: str,
        t_ms: int,
        source: str,
        helper_type: str,
        coordinate_frame: CoordinateFrame | dict[str, Any],
        spatial_anchor: SpatialAnchor | dict[str, Any],
        provenance: dict[str, Any],
        source_support: dict[str, Any],
        time_range: TimeRange | dict[str, Any] | None = None,
        place: str | None = None,
        pose: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        node_type: str = "observation",
        derived: bool = False,
        immutable_raw: bool = True,
        node_id: str | None = None,
    ) -> MemoryNode:
        return self.write_observation(
            text=text,
            t_ms=t_ms,
            source=source,
            helper_type=helper_type,
            coordinate_frame=coordinate_frame,
            time_range=time_range,
            spatial_anchor=spatial_anchor,
            provenance=provenance,
            source_support=source_support,
            place=place,
            pose=pose,
            metadata=metadata,
            node_type=node_type,
            derived=derived,
            immutable_raw=immutable_raw,
            node_id=node_id,
        )

    def link(
        self,
        from_id: str,
        to_id: str,
        link_type: str,
        *,
        weight: float = 1.0,
        metadata: dict[str, Any] | None = None,
        link_id: str | None = None,
    ) -> LinkRecord:
        record = LinkRecord(
            id=link_id or str(uuid.uuid4()),
            from_id=from_id,
            to_id=to_id,
            link_type=link_type,
            weight=weight,
            metadata=metadata or {},
        )
        self._conn.execute(
            """
            INSERT INTO memory_links
            (id, from_id, to_id, link_type, weight, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.from_id,
                record.to_id,
                record.link_type,
                record.weight,
                _json_dump(record.metadata),
            ),
        )
        self._conn.commit()
        return record

    # ---- P10: coordinate anchor substrate -------------------------------------------------
    def _row_to_anchor(self, row: sqlite3.Row) -> AnchorRecord:
        return AnchorRecord(
            anchor_id=row["anchor_id"],
            grade=row["grade"],
            room=row["room"],
            first_session=row["first_session"],
            last_session=row["last_session"],
            first_seen_ms=int(row["first_seen_ms"]),
            last_seen_ms=int(row["last_seen_ms"]),
            session_count=int(row["session_count"]),
            sightings=int(row["sightings"]),
            pose=json.loads(row["pose_json"]) if row["pose_json"] else {},
        )

    def record_anchor(
        self,
        anchor_id: str,
        *,
        t_ms: int,
        session_id: str | None = None,
        room: str | None = None,
        grade: str = "none",
        pose: dict[str, Any] | None = None,
    ) -> AnchorRecord:
        """Upsert a place-anchor sighting. First sight inserts; a later sight extends the
        seen-window, keeps the BEST grade (monotone — see contract.best_grade), and counts a
        re-localization when the anchor turns up in a session it wasn't last seen in. Callers
        must serialize this behind the same lock as writes (the hub does)."""
        anchor_id = str(anchor_id or "").strip()
        if not anchor_id:
            raise ValueError("anchor_id must not be empty")
        grade = normalize_grade(grade)
        existing = self._conn.execute(
            "SELECT * FROM anchors WHERE anchor_id = ?", (anchor_id,)
        ).fetchone()
        if existing is None:
            self._conn.execute(
                """
                INSERT INTO anchors
                (anchor_id, room, first_session, last_session, first_seen_ms, last_seen_ms,
                 grade, session_count, sightings, pose_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1, ?)
                """,
                (anchor_id, room, session_id, session_id, int(t_ms), int(t_ms), grade,
                 _json_dump(pose or {})),
            )
        else:
            prev = self._row_to_anchor(existing)
            merged_grade = best_grade(prev.grade, grade)
            # A new session touching this anchor = a re-localization event.
            relocalized = bool(session_id) and session_id != prev.last_session
            session_count = prev.session_count + (1 if relocalized else 0)
            # Keep the pose from the firmest fix we have; only overwrite when this sighting is
            # at least as good and actually carries one.
            keep_pose = prev.pose
            if pose and best_grade(grade, prev.grade) == grade and grade != "none":
                keep_pose = pose
            self._conn.execute(
                """
                UPDATE anchors SET
                    room = COALESCE(?, room),
                    last_session = COALESCE(?, last_session),
                    first_seen_ms = MIN(first_seen_ms, ?),
                    last_seen_ms = MAX(last_seen_ms, ?),
                    grade = ?,
                    session_count = ?,
                    sightings = sightings + 1,
                    pose_json = ?
                WHERE anchor_id = ?
                """,
                (room, session_id, int(t_ms), int(t_ms), merged_grade, session_count,
                 _json_dump(keep_pose), anchor_id),
            )
        self._conn.commit()
        return self.anchor(anchor_id)  # type: ignore[return-value]

    def anchor(self, anchor_id: str) -> AnchorRecord | None:
        row = self._conn.execute(
            "SELECT * FROM anchors WHERE anchor_id = ?", (str(anchor_id),)
        ).fetchone()
        return self._row_to_anchor(row) if row is not None else None

    def anchors(self, *, room: str | None = None) -> tuple[AnchorRecord, ...]:
        if room is None:
            rows = self._conn.execute(
                "SELECT * FROM anchors ORDER BY first_seen_ms ASC"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM anchors WHERE room = ? ORDER BY first_seen_ms ASC", (room,)
            ).fetchall()
        return tuple(self._row_to_anchor(row) for row in rows)

    def anchor_coverage(self, *, session_id: str | None = None) -> dict[str, Any]:
        """P10 Done-when instrument: of the live phone observation rows (optionally one
        session), how many carry an anchor_id, and at what grades. The confirmed-track
        denominator is refined by the capture-analysis script; this is the store-level truth
        the hub can report cheaply. Honest by construction — an empty store reads 0.0, never
        a flattering fraction."""
        total = 0
        with_anchor = 0
        by_grade: dict[str, int] = {}
        for node in self.nodes(node_types=("observation",)):
            meta = node.metadata or {}
            if session_id is not None and meta.get("session_id") != session_id:
                continue
            total += 1
            aid = meta.get("anchor_id")
            if aid:
                with_anchor += 1
                grade = normalize_grade(meta.get("grade"))
                by_grade[grade] = by_grade.get(grade, 0) + 1
        anchors = self.anchors()
        return {
            "rows_total": total,
            "rows_with_anchor": with_anchor,
            "fraction": (with_anchor / total) if total else 0.0,
            "by_grade": by_grade,
            "anchors_total": len(anchors),
            "anchors_relocalized": sum(1 for a in anchors if a.relocalized),
        }

    # ---- P11: appearance fingerprints (things pin to identities) --------------------------
    def fingerprint_of(self, node: MemoryNode) -> tuple[float, ...] | None:
        """The confirmed track's on-device appearance vector, or None. Stored typed in
        metadata (never in text) so retrieval and counting never trip over a wall of floats."""
        fp = (node.metadata or {}).get("fingerprint")
        if isinstance(fp, list) and fp:
            try:
                return tuple(float(v) for v in fp)
            except (TypeError, ValueError):
                return None
        return None

    def fingerprint_similarity(
        self, left: Iterable[float], right: Iterable[float]
    ) -> float:
        """Cosine of two appearance vectors — the 'is this the same thing?' primitive the
        sleep binder and future live binder ask (P12/P32 own the actual merge decision)."""
        return _cosine(tuple(float(v) for v in left), tuple(float(v) for v in right))

    def same_appearance(
        self, left: Iterable[float], right: Iterable[float], *, threshold: float | None = None
    ) -> bool:
        cut = FINGERPRINT_MATCH_THRESHOLD if threshold is None else threshold
        return self.fingerprint_similarity(left, right) >= cut

    def fingerprint_neighbors(
        self,
        vector: Iterable[float],
        *,
        k: int = 5,
        min_similarity: float = 0.0,
        exclude_ids: Iterable[str] = (),
    ) -> tuple[tuple[MemoryNode, float], ...]:
        """The k observations whose fingerprints are most similar to `vector`. Linear scan —
        honest for the prototype's store size; a vector index is a later optimization, not a
        correctness change."""
        vec = tuple(float(v) for v in vector)
        excluded = set(exclude_ids)
        scored: list[tuple[MemoryNode, float]] = []
        for node in self.nodes(node_types=("observation",)):
            if node.id in excluded:
                continue
            fp = self.fingerprint_of(node)
            if fp is None:
                continue
            score = _cosine(vec, fp)
            if score >= min_similarity:
                scored.append((node, score))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return tuple(scored[:k])

    def fingerprint_coverage(self) -> dict[str, Any]:
        """P11 Done-when instrument: of the live observation rows, how many carry a fingerprint.
        The confirmed-track denominator is refined by the capture-analysis script; the real ROC
        needs device crops. Honest by construction — empty store reads 0.0."""
        total = 0
        with_fp = 0
        for node in self.nodes(node_types=("observation",)):
            total += 1
            if self.fingerprint_of(node) is not None:
                with_fp += 1
        return {
            "rows_total": total,
            "rows_with_fingerprint": with_fp,
            "fraction": (with_fp / total) if total else 0.0,
        }

    def reconsider_derived(self, builder: str) -> int:
        """Sleep reconsolidation: remove DERIVED nodes previously authored by `builder` (and
        links touching them) so the next run re-derives them from immutable raw. Raw capture
        (derived=0 / immutable_raw=1) is never touched — the never-delete law protects what
        was observed, not the binder's own reconsiderable output. Returns nodes removed."""
        rows = self._conn.execute(
            "SELECT id FROM memory_nodes WHERE derived = 1 AND immutable_raw = 0 "
            "AND provenance_json LIKE ?",
            (f'%"builder": "{builder}"%',),
        ).fetchall()
        ids = [r["id"] for r in rows]
        for node_id in ids:
            self._conn.execute(
                "DELETE FROM memory_links WHERE from_id = ? OR to_id = ?", (node_id, node_id))
            self._conn.execute("DELETE FROM memory_nodes WHERE id = ?", (node_id,))
        self._conn.commit()
        return len(ids)

    def read_observation(self, node_id: str) -> MemoryNode | None:
        row = self._conn.execute(
            "SELECT * FROM memory_nodes WHERE id = ?",
            (node_id,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_node(row)

    def nodes(
        self,
        *,
        node_types: Iterable[str] | None = None,
        sources: Iterable[str] | None = None,
        exclude_sources: Iterable[str] | None = None,
    ) -> tuple[MemoryNode, ...]:
        clauses: list[str] = []
        params: list[Any] = []
        if node_types is not None:
            types = tuple(node_types)
            clauses.append(f"node_type IN ({','.join('?' for _ in types)})")
            params.extend(types)
        if sources is not None:
            srcs = tuple(sources)
            clauses.append(f"source IN ({','.join('?' for _ in srcs)})")
            params.extend(srcs)
        if exclude_sources:
            ex = tuple(exclude_sources)
            clauses.append(f"source NOT IN ({','.join('?' for _ in ex)})")
            params.extend(ex)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self._conn.execute(
            f"SELECT * FROM memory_nodes{where} ORDER BY t_ms ASC, seq ASC", params
        ).fetchall()
        return tuple(_row_to_node(row) for row in rows)

    def links(self) -> tuple[LinkRecord, ...]:
        rows = self._conn.execute(
            "SELECT * FROM memory_links ORDER BY seq ASC"
        ).fetchall()
        return tuple(_row_to_link(row) for row in rows)

    def node_count(self, *, node_types: Iterable[str] | None = None) -> int:
        return len(self.nodes(node_types=node_types))

    def link_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS n FROM memory_links").fetchone()
        return int(row["n"]) if row is not None else 0

    def search(
        self,
        query: str,
        k: int = 5,
        *,
        node_types: Iterable[str] | None = None,
        sources: Iterable[str] | None = None,
        exclude_sources: Iterable[str] | None = None,
    ) -> SearchSlice:
        query_embedding = self._embedder.embed([query])[0]
        candidates = self.nodes(
            node_types=node_types, sources=sources, exclude_sources=exclude_sources
        )
        scored: list[SearchHit] = []
        for node in candidates:
            cosine = _cosine(query_embedding, node.embedding)
            lexical = _lexical_overlap(query, node.text)
            boost = 0.0
            if node.node_type in {"entity", "entity_memory", "event_memory", "group_memory"}:
                boost = 0.05
            elif node.node_type == "composed_memory":
                boost = 0.1
            score = cosine + (0.2 * lexical) + boost
            scored.append(SearchHit(node=node, score=round(score, 6)))
        scored.sort(key=lambda hit: (-hit.score, hit.node.t_ms, hit.node.id))
        hits = tuple(scored[: max(k, 0)])
        hit_ids = {hit.node.id for hit in hits}
        related_links = tuple(
            link
            for link in self.links()
            if link.from_id in hit_ids or link.to_id in hit_ids
        )
        retrieval_mode = self.retrieval_mode
        return SearchSlice(
            query=query,
            hits=hits,
            links=related_links,
            retrieval_mode=retrieval_mode,
            degraded=retrieval_mode in {"lexical-fallback", "degraded"},
        )

    def neighbors(
        self,
        node_id: str,
        *,
        link_types: Iterable[str] | None = None,
        limit: int = 20,
    ) -> tuple[NeighborRecord, ...]:
        allowed = set(link_types or ())
        neighbors: list[NeighborRecord] = []
        for edge in self.links():
            if allowed and edge.link_type not in allowed:
                continue
            if edge.from_id == node_id:
                node = self.read_observation(edge.to_id)
                if node is not None:
                    neighbors.append(NeighborRecord(edge=edge, node=node, direction="out"))
            elif edge.to_id == node_id:
                node = self.read_observation(edge.from_id)
                if node is not None:
                    neighbors.append(NeighborRecord(edge=edge, node=node, direction="in"))
        neighbors.sort(key=lambda record: (record.node.t_ms, record.edge.link_type, record.node.id))
        return tuple(neighbors[: max(limit, 0)])

    def get_abstractions(self) -> tuple[AbstractionRecord, ...]:
        return tuple(
            AbstractionRecord(node=node)
            for node in self.nodes(
                node_types=("abstraction", "composed_memory", "entity_memory", "event_memory", "group_memory")
            )
        )
