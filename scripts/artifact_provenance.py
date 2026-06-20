#!/usr/bin/env python3
"""Source fingerprints for derived memory artifacts.

Derived memories must never be accepted merely because a file with the expected
name exists beside a clip. A fingerprint ties the artifact to the exact capture
channels it summarized and prevents stale/cross-clip memory from entering recall.
"""
from __future__ import annotations

import hashlib
import json
import os


SOURCE_FILES = (
    "kf_memory.json",
    "world_memory.json",
    "screen_memory.json",
    "asr.json",
    "transcript.json",
    "audio_events.json",
    "attributes.json",
    "entity_capture.json",
    "entity_centric.json",
)


def raw_source_sha256(memory_dir):
    """Return the immutable raw-session identity recorded by the evidence pack."""
    path = os.path.join(memory_dir, "evidence_pack.json")
    try:
        with open(path) as source:
            pack = json.load(source)
    except (OSError, ValueError, TypeError):
        return None
    value = (pack.get("source") or {}).get("sha256")
    if not isinstance(value, str) or len(value) != 64:
        return None
    return value.lower()


def source_fingerprint(memory_dir):
    digest = hashlib.sha256()
    found = False
    raw_hash = raw_source_sha256(memory_dir)
    if raw_hash:
        found = True
        digest.update(b"raw_source_sha256\0")
        digest.update(raw_hash.encode("ascii"))
        digest.update(b"\0")
    for name in SOURCE_FILES:
        path = os.path.join(memory_dir, name)
        if not os.path.isfile(path):
            continue
        found = True
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        with open(path, "rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest() if found else None


def provenance_matches(artifact, memory_dir):
    if not isinstance(artifact, dict):
        return False
    recorded = (artifact.get("_provenance") or {}).get("source_fingerprint")
    current = source_fingerprint(memory_dir)
    return bool(recorded and current and recorded == current)
