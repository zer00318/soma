from __future__ import annotations

import platform
import shutil
import sys
from pathlib import Path


def audio_engine_profiles(root_dir: Path) -> list[dict]:
    system = platform.system().lower()
    script_path = root_dir / "scripts" / "live_asr_macos.swift"
    swift_path = shutil.which("swift")

    profiles = [
        {
            "engine": "stream-stdin",
            "supported": True,
            "kind": "external-transcript",
            "reason": "Pipe transcript lines into TRACE from any external ASR source.",
            "command": "python3 -m trace_hub stream-stdin --data-dir data",
        },
        {
            "engine": "tail-file",
            "supported": True,
            "kind": "external-transcript",
            "reason": "Watch a transcript file and ingest new lines continuously.",
            "command": "python3 -m trace_hub tail-file /tmp/trace-transcript.txt --data-dir data",
        },
    ]

    if system != "darwin":
        profiles.insert(
            0,
            {
                "engine": "live-mic",
                "supported": False,
                "kind": "native-microphone",
                "reason": "The built-in live microphone bridge currently supports macOS only.",
            },
        )
        return profiles

    if swift_path is None:
        profiles.insert(
            0,
            {
                "engine": "live-mic",
                "supported": False,
                "kind": "native-microphone",
                "reason": "Swift is not installed, so the macOS live microphone bridge cannot run.",
            },
        )
        return profiles

    if not script_path.exists():
        profiles.insert(
            0,
            {
                "engine": "live-mic",
                "supported": False,
                "kind": "native-microphone",
                "reason": "The macOS live microphone bridge script is missing.",
            },
        )
        return profiles

    profiles.insert(
        0,
        {
            "engine": "live-mic",
            "supported": True,
            "kind": "native-microphone",
            "reason": "Native macOS microphone transcription is available.",
            "command": [swift_path, str(script_path)],
        },
    )
    return profiles


def live_audio_status(root_dir: Path) -> dict:
    profiles = audio_engine_profiles(root_dir)
    recommended = next((profile for profile in profiles if profile["supported"]), profiles[0])
    return {
        "supported": bool(recommended["supported"]),
        "provider": "macos_live_asr" if recommended["engine"] == "live-mic" else "continuous_audio_transcript",
        "reason": recommended["reason"],
        "platform": platform.system().lower(),
        "recommended_mode": recommended["engine"],
        "fallbacks": [
            {
                "mode": profile["engine"],
                "description": profile["reason"],
                "command": profile.get("command", ""),
            }
            for profile in profiles
            if profile["engine"] != recommended["engine"]
        ],
        "command": recommended.get("command"),
        "engines": profiles,
    }


def resolve_audio_engine(root_dir: Path, requested: str = "auto") -> dict:
    profiles = {profile["engine"]: profile for profile in audio_engine_profiles(root_dir)}
    if requested == "auto":
        if not sys.stdin.isatty():
            return profiles["stream-stdin"]
        if profiles.get("live-mic", {}).get("supported"):
            return profiles["live-mic"]
        return profiles["stream-stdin"]

    if requested not in profiles:
        raise ValueError(f"Unknown audio engine: {requested}")
    return profiles[requested]
