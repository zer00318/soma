from __future__ import annotations

from typing import Protocol


class Ocr(Protocol):
    def read(self, _pixels: memoryview) -> tuple[str, ...]: ...
