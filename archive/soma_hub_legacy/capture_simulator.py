from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class CaptureStatus:
    active: bool
    buffered_segments: int
    persisted_raw_media_files: int = 0


class CaptureSimulator:
    """Ephemeral capture-device stand-in.

    It stores only in-memory text segments for tests and development. It never
    writes raw media files.
    """

    def __init__(self, max_segments: int = 64) -> None:
        self._active = False
        self._buffer: deque[str] = deque(maxlen=max_segments)

    def start(self) -> None:
        self._active = True

    def pause(self) -> None:
        self._active = False

    def ingest_segment(self, text: str) -> None:
        if self._active:
            self._buffer.append(text)

    def drain(self) -> list[str]:
        segments = list(self._buffer)
        self._buffer.clear()
        return segments

    def status(self) -> CaptureStatus:
        return CaptureStatus(active=self._active, buffered_segments=len(self._buffer))
