from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextEgress:
    """The only payload type permitted to cross the device boundary."""

    text: str
    source_event_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("egress text must not be empty")
        if not self.source_event_ids:
            raise ValueError("egress text requires source provenance")
