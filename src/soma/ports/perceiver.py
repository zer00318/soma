from __future__ import annotations

from typing import Protocol

from soma.domain.observation import Observation


class Perceiver(Protocol):
    def perceive(self, _payload: object, captured_at_ms: int) -> tuple[Observation, ...]: ...
