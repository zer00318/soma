from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class MemoryInput:
    detailed_text: str
    source_type: str = "audio"
    category: str = "general"
    sensitivity: str = "normal"
    confidence: float = 0.75
    captured_at: str = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryRecord:
    id: str
    captured_at: str
    source_type: str
    category: str
    sensitivity: str
    confidence: float
    public_summary: str
    metadata: dict[str, Any]


def new_memory_id() -> str:
    return str(uuid4())
