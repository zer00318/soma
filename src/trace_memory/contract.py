"""THE HELPER CONTRACT (ops/CANONICAL_SPEC.md §5, packet P02).

A helper is ANY process that emits observations shaped like this into the hub's ingest
seam. The registry (config/helpers.json) is DATA: adding a helper must never touch the
spine — an unknown-but-valid helper_id ingests fine and simply shows up as unregistered
in the coverage report (L7: the list is never closed; users add their own).

Contract observation (versioned; the hub also still accepts the legacy app shape):
    {
      "contract": 1,
      "helper_id": "mac_screen_ocr",          # required — who perceived this
      "text": "...",                           # required — what the row SAYS
      "t_ms": 1783000000000,                   # required — when (epoch ms)
      "confidence": 0.9,                       # optional [0,1]
      "anchor_id": "arkit:...",                # optional — where (place-anchor hierarchy)
      "pose": {"yaw": .., "world_transform": [..]},  # optional — camera/world pose (P10)
      "grade": "world|session|track|none",     # optional — spatial fidelity self-report (P10)
      "room": "kitchen",                       # optional — ARWorldMap space label (P10)
      "fingerprint": [0.1, ...],               # optional — non-reversible, ≤512 floats (L1)
      "session_id": "walk-20260704-0826",      # optional
      "provenance": {...},                     # optional dict
      "metadata": {...},                       # optional dict (merged, contract keys win)
    }
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONTRACT_VERSION = 1
FINGERPRINT_MAX_FLOATS = 512

# P10: spatial-fidelity grades, honestly self-reported by the emitter, ordered worst→best.
# The observation SAYS which grade it carries, so a degraded fix is never dressed up as a
# world-locked one (spec §2: everything is pinned, but the memory admits how firmly).
#   world   = relocalized against a persistent ARWorldMap → cross-session identity
#   session = valid world coordinates within the current ARKit session only
#   track   = tracking .limited → degraded to a per-track anchor, pose unreliable
#   none    = no spatial fix at all
ANCHOR_GRADE_ORDER = ("none", "track", "session", "world")
ANCHOR_GRADES = frozenset(ANCHOR_GRADE_ORDER)


def is_valid_fingerprint(value: Any) -> bool:
    """P11: a fingerprint is a non-reversible appearance vector (L1) — a bounded list of
    numbers, never an image. One owner so the contract path and the legacy phone shape agree."""
    return (
        isinstance(value, list)
        and 0 < len(value) <= FINGERPRINT_MAX_FLOATS
        and all(isinstance(v, (int, float)) for v in value)
    )


def normalize_fingerprint(value: Any) -> list[float] | None:
    """Coerce a valid fingerprint to a list of floats, else None (drop it — a garbage vector
    must never poison the row, but it must never take the observation down either)."""
    if not is_valid_fingerprint(value):
        return None
    return [float(v) for v in value]


def normalize_grade(value: Any) -> str:
    """Clamp any emitter-supplied grade to the closed vocab. Unknown/blank → 'none': we
    keep the observation (dropping perception over a grade typo lies about coverage) but
    never invent a fidelity we can't stand behind."""
    token = str(value or "").strip().lower()
    return token if token in ANCHOR_GRADES else "none"


def best_grade(*grades: Any) -> str:
    """The highest fidelity ever observed for an anchor (monotone: an anchor never loses a
    grade it once earned — a later .limited frame doesn't downgrade a world-locked pin)."""
    return max((normalize_grade(g) for g in grades), key=ANCHOR_GRADE_ORDER.index, default="none")

# Pillar -> the store `source` column value. hub.ask fences retrieval to these, so a new
# pillar becomes queryable by REGISTRY edit, not code edit.
PILLAR_SOURCES = {
    "phone": "phone_camera",
    "mac": "mac_screen",
    "owner": "owner",
}

_DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "config" / "helpers.json"


def helper_id_from_legacy(source: str) -> str:
    """Map the phone app's per-record `source` string to the canonical helper_id.
    (Moved verbatim from trace_hub.helper_of — same behavior, one owner.)"""
    s = (source or "").lower()
    if s.startswith("fastvlm") or s == "vlm":
        return "vlm_object"
    if "vision" in s or "ocr" in s:
        return "ocr"
    if "speech" in s or "whisper" in s or "asr" in s:
        return "asr"
    if "detector" in s or s == "native":
        return "detector"
    return "vlm_object"


def validate_observation(packet: dict) -> tuple[dict[str, Any] | None, str | None]:
    """Validate + normalize a CONTRACT-shaped packet. Returns (normalized, None) or
    (None, reason). Loud and specific on violation — a silently dropped observation is a
    lie about coverage."""
    if not isinstance(packet, dict):
        return None, "packet is not an object"
    version = packet.get("contract")
    if version != CONTRACT_VERSION:
        return None, f"unsupported contract version {version!r} (expected {CONTRACT_VERSION})"

    helper_id = str(packet.get("helper_id") or "").strip()
    if not helper_id:
        return None, "missing helper_id"
    text = str(packet.get("text") or "").strip()
    if not text:
        return None, "missing text"
    t_ms = packet.get("t_ms")
    if not isinstance(t_ms, int) or t_ms <= 0:
        return None, "t_ms must be a positive epoch-milliseconds integer"

    confidence = packet.get("confidence")
    if confidence is not None:
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            return None, "confidence is not a number"
        if not 0.0 <= confidence <= 1.0:
            return None, "confidence outside [0,1]"

    fingerprint = packet.get("fingerprint")
    if fingerprint is not None and not is_valid_fingerprint(fingerprint):
        return None, f"fingerprint must be a list of ≤{FINGERPRINT_MAX_FLOATS} numbers"

    pose = packet.get("pose")
    if pose is not None and not isinstance(pose, dict):
        return None, "pose is not an object"
    grade = packet.get("grade")
    if grade is not None and not isinstance(grade, str):
        return None, "grade is not a string"
    room = packet.get("room")
    if room is not None and not isinstance(room, str):
        return None, "room is not a string"

    provenance = packet.get("provenance")
    if provenance is not None and not isinstance(provenance, dict):
        return None, "provenance is not an object"
    metadata = packet.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        return None, "metadata is not an object"

    return {
        "helper_id": helper_id,
        "text": text,
        "t_ms": t_ms,
        "confidence": confidence,
        "anchor_id": (str(packet["anchor_id"]) if packet.get("anchor_id") else None),
        "pose": (dict(pose) if pose else None),
        "grade": (normalize_grade(grade) if grade else None),
        "room": (room.strip() if room and room.strip() else None),
        "fingerprint": fingerprint,
        "session_id": (str(packet["session_id"]) if packet.get("session_id") else None),
        "provenance": dict(provenance or {}),
        "metadata": dict(metadata or {}),
    }, None


def load_registry(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Load config/helpers.json -> {helper_id: entry}. Malformed entries are skipped with
    a printed warning, never a crash — a broken registry line must not take capture down."""
    registry_path = Path(path) if path else _DEFAULT_REGISTRY_PATH
    if not registry_path.exists():
        return {}
    try:
        raw = json.loads(registry_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[contract] registry unreadable ({exc}); running with empty registry", flush=True)
        return {}
    registry: dict[str, dict[str, Any]] = {}
    for entry in raw.get("helpers", []):
        helper_id = str(entry.get("id") or "").strip()
        kind = entry.get("kind")
        pillar = entry.get("pillar")
        if not helper_id or kind not in ("standing", "dispatched") or pillar not in PILLAR_SOURCES:
            print(f"[contract] skipping malformed registry entry: {entry!r}", flush=True)
            continue
        registry[helper_id] = {
            "id": helper_id,
            "kind": kind,
            "pillar": pillar,
            "dispatch_hint": entry.get("dispatch_hint"),
            "description": entry.get("description", ""),
        }
    return registry
