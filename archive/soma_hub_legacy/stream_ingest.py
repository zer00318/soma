from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterable, TextIO

from soma_hub.service import SomaHub


class TranscriptStreamIngestor:
    """Ingest line-delimited transcript segments as audio-derived memory."""

    def __init__(self, hub: SomaHub, provider: str = "continuous_audio_transcript") -> None:
        self.hub = hub
        self.provider = provider

    def ingest_lines(self, lines: Iterable[str], source_name: str = "stdin") -> list[dict]:
        results: list[dict] = []
        for raw in lines:
            payload = self._payload_from_line(raw, source_name)
            if payload is None:
                continue
            results.append(self.hub.ingest_extracted(payload))
        return results

    def ingest_stream(self, stream: TextIO, source_name: str = "stdin") -> None:
        for raw in stream:
            payload = self._payload_from_line(raw, source_name)
            if payload is None:
                continue
            record = self.hub.ingest_extracted(payload)
            print(json.dumps(record, sort_keys=True))

    def tail_file(self, path: Path, poll_interval: float = 0.5) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
        with path.open("r", encoding="utf-8") as stream:
            stream.seek(0, 2)
            while True:
                line = stream.readline()
                if not line:
                    time.sleep(poll_interval)
                    continue
                payload = self._payload_from_line(line, str(path))
                if payload is None:
                    continue
                record = self.hub.ingest_extracted(payload)
                print(json.dumps(record, sort_keys=True))

    def _payload_from_line(self, raw: str, source_name: str) -> dict | None:
        text = raw.strip()
        if not text:
            return None
        return {
            "text": text,
            "source_type": "audio",
            "provider": self.provider,
            "metadata": {"source_name": source_name, "ingest_mode": "continuous_stream"},
        }
