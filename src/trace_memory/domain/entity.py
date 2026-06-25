from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Entity:
    entity_id: str
    kind: str
    label: str

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.entity_id, self.kind, self.label)):
            raise ValueError("entity fields must not be empty")
