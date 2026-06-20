from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from soma_hub.platform_audio import live_audio_status, resolve_audio_engine
from soma_hub.service import SomaHub
from soma_hub.stream_ingest import TranscriptStreamIngestor


class LiveAudioBridge:
    """Bridge a line-emitting ASR process into SOMA's extracted-memory pipeline."""

    def __init__(self, hub: SomaHub, provider: str = "continuous_audio_transcript") -> None:
        self.hub = hub
        self.provider = provider

    def ingest_from_command(self, command: list[str], source_name: str) -> int:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        assert process.stderr is not None

        ingestor = TranscriptStreamIngestor(self.hub, provider=self.provider)
        try:
            ingestor.ingest_stream(process.stdout, source_name=source_name)
        finally:
            return_code = process.wait()
            stderr_output = process.stderr.read().strip()
            if stderr_output:
                print(stderr_output, file=sys.stderr)
        return return_code


def macos_live_transcript_command(root_dir: Path) -> list[str]:
    status = live_audio_status(root_dir)
    if not status["supported"]:
        fallback_hint = ""
        if status.get("fallbacks"):
            fallback_hint = f" Try {status['fallbacks'][0]['command']} instead."
        raise RuntimeError(f"{status['reason']}{fallback_hint}")
    return list(status["command"])


def selected_audio_engine(root_dir: Path, requested: str = "auto") -> dict:
    profile = resolve_audio_engine(root_dir, requested=requested)
    if not profile["supported"] and requested != "auto":
        raise RuntimeError(profile["reason"])
    return profile
