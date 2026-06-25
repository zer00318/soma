from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Provenance:
    event_id: str
    source_channel: str
    captured_at_ms: int

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("event_id must not be empty")
        if not self.source_channel.strip():
            raise ValueError("source_channel must not be empty")
        if self.captured_at_ms < 0:
            raise ValueError("captured_at_ms must not be negative")
