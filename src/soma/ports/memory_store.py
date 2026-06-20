from __future__ import annotations

from typing import Protocol

from soma.domain.observation import Observation


class MemoryStore(Protocol):
    def append(self, _observation: Observation) -> None: ...

    def observations(self) -> tuple[Observation, ...]: ...
