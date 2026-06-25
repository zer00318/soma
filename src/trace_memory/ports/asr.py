from __future__ import annotations

from typing import Protocol


class Asr(Protocol):
    def transcribe(self, _audio: memoryview) -> str: ...
