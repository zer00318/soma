from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Detection:
    label: str
    confidence: float
    bbox_xyxy: tuple[float, float, float, float]
    track_id: int | None = None
    color: str = "unknown"
    frame_position: str = "visible frame"
    area_ratio: float = 0.0


@dataclass
class TrackState:
    track_id: int
    label: str
    color: str
    confidence: float
    bbox_xyxy: tuple[float, float, float, float]
    first_seen_utc: str
    last_seen_utc: str
    seen_count: int = 1
    frame_position: str = "visible frame"
    area_ratio: float = 0.0
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryEvent:
    event_type: str
    timestamp_utc: str
    summary_text: str
    confidence: float
    category: str
    data: dict[str, Any] = field(default_factory=dict)
