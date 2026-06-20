from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Query:
    text: str

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("query must not be empty")


@dataclass(frozen=True)
class Citation:
    node_id: str
    t_ms: int | None = None


@dataclass(frozen=True)
class RecallAnswer:
    text: str
    citations: tuple[Citation, ...]
