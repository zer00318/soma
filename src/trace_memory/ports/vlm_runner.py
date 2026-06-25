from __future__ import annotations

from typing import Protocol


class VlmRunner(Protocol):
    def describe(self, _pixels: memoryview) -> str: ...
