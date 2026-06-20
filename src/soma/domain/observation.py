from __future__ import annotations

from dataclasses import dataclass

from soma.domain.confidence import Confidence
from soma.domain.provenance import Provenance


@dataclass(frozen=True)
class Attribute:
    name: str
    value: str

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.value.strip():
            raise ValueError("attribute name and value must not be empty")


@dataclass(frozen=True)
class Observation:
    """Open-vocabulary text emitted by an on-device perceiver."""

    kind: str
    subject: str
    attributes: tuple[Attribute, ...]
    t_ms: int
    spatial_anchor: str | None
    confidence: Confidence
    provenance: Provenance
    refutation_cue: str | None = None

    def __post_init__(self) -> None:
        if not self.kind.strip() or not self.subject.strip():
            raise ValueError("kind and subject must not be empty")
        if self.t_ms < 0:
            raise ValueError("t_ms must not be negative")
        if self.t_ms != self.provenance.captured_at_ms:
            raise ValueError("observation time must match provenance time")
