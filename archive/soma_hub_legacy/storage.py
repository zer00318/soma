from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from soma_hub.crypto import EncryptedTextCodec
from soma_hub.models import MemoryInput, MemoryRecord, new_memory_id


class MemoryStore:
    def __init__(self, db_path: Path, codec: EncryptedTextCodec) -> None:
        self.db_path = db_path
        self.codec = codec
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    captured_at TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    category TEXT NOT NULL,
                    sensitivity TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    public_summary TEXT NOT NULL,
                    detailed_text_cipher TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_memories_captured_at
                    ON memories(captured_at DESC);
                CREATE INDEX IF NOT EXISTS idx_memories_category
                    ON memories(category);
                """
            )

    def add(self, memory: MemoryInput, public_summary: str) -> MemoryRecord:
        memory_id = new_memory_id()
        cipher = self.codec.encrypt(memory.detailed_text)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memories (
                    id, captured_at, source_type, category, sensitivity,
                    confidence, public_summary, detailed_text_cipher, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    memory.captured_at,
                    memory.source_type,
                    memory.category,
                    memory.sensitivity,
                    memory.confidence,
                    public_summary,
                    cipher,
                    json.dumps(memory.metadata, sort_keys=True),
                ),
            )
        return MemoryRecord(
            id=memory_id,
            captured_at=memory.captured_at,
            source_type=memory.source_type,
            category=memory.category,
            sensitivity=memory.sensitivity,
            confidence=memory.confidence,
            public_summary=public_summary,
            metadata=memory.metadata,
        )

    def metadata(self, limit: int = 50) -> dict:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            by_category = {
                row["category"]: row["count"]
                for row in conn.execute(
                    "SELECT category, COUNT(*) AS count FROM memories GROUP BY category ORDER BY category"
                )
            }
            by_sensitivity = {
                row["sensitivity"]: row["count"]
                for row in conn.execute(
                    "SELECT sensitivity, COUNT(*) AS count FROM memories GROUP BY sensitivity ORDER BY sensitivity"
                )
            }
            recent = [
                self._public_record(row)
                for row in conn.execute(
                    """
                    SELECT id, captured_at, source_type, category, sensitivity,
                           confidence, public_summary, metadata_json
                    FROM memories
                    ORDER BY captured_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
            ]
        return {
            "total": total,
            "by_category": by_category,
            "by_sensitivity": by_sensitivity,
            "recent": recent,
        }

    def recent_public(self, limit: int = 8, category: str | None = None) -> list[dict]:
        sql = """
            SELECT id, captured_at, source_type, category, sensitivity,
                   confidence, public_summary, metadata_json
            FROM memories
        """
        params: list[object] = []
        if category:
            sql += " WHERE category = ?"
            params.append(category)
        sql += " ORDER BY captured_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            return [self._public_record(row) for row in conn.execute(sql, params)]

    def search_private_for_purpose(self, purpose: str, terms: Iterable[str], limit: int = 8) -> list[dict]:
        allowed = {"where_is", "recent_context", "general_summary"}
        if purpose not in allowed:
            raise PermissionError(f"Purpose {purpose!r} is not allowed to access private memory")

        clean_terms = [term.lower() for term in terms if len(term) >= 2]
        matches: list[dict] = []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, captured_at, source_type, category, sensitivity,
                       confidence, public_summary, detailed_text_cipher, metadata_json
                FROM memories
                ORDER BY captured_at DESC
                LIMIT 200
                """
            ).fetchall()

        for row in rows:
            detailed_text = self.codec.decrypt(row["detailed_text_cipher"])
            lower = detailed_text.lower()
            if clean_terms and not any(term in lower for term in clean_terms):
                continue
            matches.append(
                {
                    "id": row["id"],
                    "captured_at": row["captured_at"],
                    "category": row["category"],
                    "sensitivity": row["sensitivity"],
                    "confidence": row["confidence"],
                    "public_summary": row["public_summary"],
                    "private_excerpt": self._safe_excerpt_for_purpose(purpose, detailed_text),
                }
            )
            if len(matches) >= limit:
                break
        return matches

    def delete_all(self) -> int:
        with self._connect() as conn:
            before = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            conn.execute("DELETE FROM memories")
        return int(before)

    def delete_category(self, category: str) -> int:
        with self._connect() as conn:
            before = conn.execute("SELECT COUNT(*) FROM memories WHERE category = ?", (category,)).fetchone()[0]
            conn.execute("DELETE FROM memories WHERE category = ?", (category,))
        return int(before)

    def delete_time_range(self, start: str, end: str) -> int:
        with self._connect() as conn:
            before = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE captured_at >= ? AND captured_at <= ?",
                (start, end),
            ).fetchone()[0]
            conn.execute(
                "DELETE FROM memories WHERE captured_at >= ? AND captured_at <= ?",
                (start, end),
            )
        return int(before)

    def _public_record(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "captured_at": row["captured_at"],
            "source_type": row["source_type"],
            "category": row["category"],
            "sensitivity": row["sensitivity"],
            "confidence": row["confidence"],
            "summary": row["public_summary"],
            "metadata": json.loads(row["metadata_json"]),
        }

    def _safe_excerpt_for_purpose(self, purpose: str, detailed_text: str) -> str:
        if purpose == "where_is":
            return detailed_text[:240]
        if purpose == "recent_context":
            return detailed_text[:180]
        return detailed_text[:160]
