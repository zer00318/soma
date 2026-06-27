from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MemoryNode:
    id: str
    t_ms: int
    node_type: str
    source: str
    text: str
    provenance: dict[str, Any]
    place: str | None = None
    pose: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    derived: bool = False
    embedding: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("node id must not be empty")
        if not self.node_type.strip():
            raise ValueError("node_type must not be empty")
        if not self.source.strip():
            raise ValueError("source must not be empty")
        if not self.text.strip():
            raise ValueError("text must not be empty")
        if self.t_ms < 0:
            raise ValueError("t_ms must not be negative")


@dataclass(frozen=True)
class LinkRecord:
    id: str
    from_id: str
    to_id: str
    link_type: str
    weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("link id must not be empty")
        if not self.from_id.strip() or not self.to_id.strip():
            raise ValueError("link endpoints must not be empty")
        if not self.link_type.strip():
            raise ValueError("link_type must not be empty")


@dataclass(frozen=True)
class SearchHit:
    node: MemoryNode
    score: float


@dataclass(frozen=True)
class SearchSlice:
    query: str
    hits: tuple[SearchHit, ...]
    links: tuple[LinkRecord, ...]
    retrieval_mode: str = "semantic"
    degraded: bool = False


@dataclass(frozen=True)
class NeighborRecord:
    edge: LinkRecord
    node: MemoryNode
    direction: str


StoredObservation = MemoryNode
GraphLink = LinkRecord


@dataclass(frozen=True)
class AbstractionRecord:
    node: MemoryNode
