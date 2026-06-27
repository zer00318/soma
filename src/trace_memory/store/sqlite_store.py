from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from trace_memory.store.embeddings import TextEmbedder, build_default_embedder
from trace_memory.store.models import (
    AbstractionRecord,
    LinkRecord,
    MemoryNode,
    NeighborRecord,
    SearchHit,
    SearchSlice,
)

_NODE_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_nodes (
    seq             INTEGER PRIMARY KEY AUTOINCREMENT,
    id              TEXT NOT NULL UNIQUE,
    t_ms            INTEGER NOT NULL,
    node_type       TEXT NOT NULL,
    source          TEXT NOT NULL,
    place           TEXT,
    pose_json       TEXT NOT NULL,
    text            TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    metadata_json   TEXT NOT NULL,
    derived         INTEGER NOT NULL,
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

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_memory_nodes_type_t ON memory_nodes(node_type, t_ms)",
    "CREATE INDEX IF NOT EXISTS idx_memory_nodes_place ON memory_nodes(place)",
    "CREATE INDEX IF NOT EXISTS idx_memory_links_from ON memory_links(from_id)",
    "CREATE INDEX IF NOT EXISTS idx_memory_links_to ON memory_links(to_id)",
    "CREATE INDEX IF NOT EXISTS idx_memory_links_type ON memory_links(link_type)",
)


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
    return MemoryNode(
        id=row["id"],
        t_ms=row["t_ms"],
        node_type=row["node_type"],
        source=row["source"],
        place=row["place"],
        pose=json.loads(row["pose_json"]),
        text=row["text"],
        provenance=json.loads(row["provenance_json"]),
        metadata=json.loads(row["metadata_json"]),
        derived=bool(row["derived"]),
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
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_NODE_SCHEMA)
        self._conn.execute(_LINK_SCHEMA)
        for statement in _INDEXES:
            self._conn.execute(statement)
        self._conn.commit()

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
        place: str | None = None,
        pose: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        node_type: str = "observation",
        derived: bool = False,
        node_id: str | None = None,
    ) -> MemoryNode:
        embedding = self._embedder.embed([text])[0]
        node = MemoryNode(
            id=node_id or str(uuid.uuid4()),
            t_ms=t_ms,
            node_type=node_type,
            source=source,
            place=place,
            pose=pose,
            text=text,
            provenance=provenance,
            metadata=metadata or {},
            derived=derived,
            embedding=embedding,
        )
        self._conn.execute(
            """
            INSERT INTO memory_nodes
            (id, t_ms, node_type, source, place, pose_json, text, provenance_json, metadata_json, derived, embedding_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node.id,
                node.t_ms,
                node.node_type,
                node.source,
                node.place,
                _json_dump(node.pose),
                node.text,
                _json_dump(node.provenance),
                _json_dump(node.metadata),
                int(node.derived),
                _json_dump(list(node.embedding)),
            ),
        )
        self._conn.commit()
        return node

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

    def read_observation(self, node_id: str) -> MemoryNode | None:
        row = self._conn.execute(
            "SELECT * FROM memory_nodes WHERE id = ?",
            (node_id,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_node(row)

    def nodes(self, *, node_types: Iterable[str] | None = None) -> tuple[MemoryNode, ...]:
        if node_types is None:
            rows = self._conn.execute("SELECT * FROM memory_nodes ORDER BY t_ms ASC, seq ASC").fetchall()
        else:
            types = tuple(node_types)
            placeholders = ",".join("?" for _ in types)
            rows = self._conn.execute(
                f"SELECT * FROM memory_nodes WHERE node_type IN ({placeholders}) ORDER BY t_ms ASC, seq ASC",
                types,
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
    ) -> SearchSlice:
        query_embedding = self._embedder.embed([query])[0]
        candidates = self.nodes(node_types=node_types)
        scored: list[SearchHit] = []
        for node in candidates:
            cosine = _cosine(query_embedding, node.embedding)
            lexical = _lexical_overlap(query, node.text)
            boost = 0.05 if node.node_type == "entity" else 0.0
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
            for node in self.nodes(node_types=("abstraction",))
        )
