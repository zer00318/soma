from __future__ import annotations

from dataclasses import dataclass

from trace_memory.domain.confidence import Confidence
from trace_memory.domain.provenance import Provenance


@dataclass(frozen=True)
class Binding:
    binding_id: str
    subject_id: str
    predicate: str
    object_id: str | None
    object_text: str | None
    confidence: Confidence
    evidence: tuple[Provenance, ...]

    def __post_init__(self) -> None:
        required = (self.binding_id, self.subject_id, self.predicate)
        if not all(value.strip() for value in required):
            raise ValueError("binding identity fields must not be empty")
        if bool(self.object_id) == bool(self.object_text):
            raise ValueError("binding requires exactly one object target")
        if not self.evidence:
            raise ValueError("binding requires provenance")

    def is_usable(self, minimum_confidence: float) -> bool:
        return self.confidence.value >= minimum_confidence
