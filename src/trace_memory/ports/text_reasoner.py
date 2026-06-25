from __future__ import annotations

from typing import Protocol


class TextReasoner(Protocol):
    def reason(self, _prompt: str) -> str: ...
