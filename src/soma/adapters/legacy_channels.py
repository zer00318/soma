from __future__ import annotations

import json
import os
from typing import Any

from soma.domain.confidence import Confidence
from soma.domain.observation import Attribute, Observation
from soma.domain.provenance import Provenance

_KF_FILE = "kf_memory.json"
_ENTITY_FILE = "entity_capture.json"
_DEFAULT_CONFIDENCE = 0.5
_SUBJECT_MAX_LEN = 200


def _clamp(value: float) -> float:
    """Clamp a float into the closed unit interval."""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _confidence_from(row: dict[str, Any]) -> Confidence:
    """Read a numeric confidence/score from a row, defaulting to 0.5."""
    for key in ("confidence", "score"):
        raw = row.get(key)
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            return Confidence(_clamp(float(raw)))
    return Confidence(_DEFAULT_CONFIDENCE)


def _t_ms_from(row: dict[str, Any]) -> int | None:
    """Convert a row's ``t`` seconds value to milliseconds, or None."""
    raw = row.get("t")
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        return None
    t_ms = round(float(raw) * 1000)
    if t_ms < 0:
        return None
    return t_ms


def _clip_subject(text: str) -> str:
    """Trim and length-limit a free-text subject."""
    return text.strip()[:_SUBJECT_MAX_LEN]


def _make_observation(
    *,
    kind: str,
    subject: str,
    event_id: str,
    source_channel: str,
    t_ms: int,
    confidence: Confidence,
    attributes: tuple[Attribute, ...] = (),
) -> Observation | None:
    """Build an Observation, returning None if any invariant rejects it."""
    if not subject.strip():
        return None
    try:
        provenance = Provenance(
            event_id=event_id,
            source_channel=source_channel,
            captured_at_ms=t_ms,
        )
        return Observation(
            kind=kind,
            subject=subject,
            attributes=attributes,
            t_ms=t_ms,
            spatial_anchor=None,
            confidence=confidence,
            provenance=provenance,
        )
    except ValueError:
        return None


def _keyframe_event_id(row: dict[str, Any], t_ms: int) -> str:
    """Derive a stable keyframe event id."""
    frame = row.get("frame")
    if isinstance(frame, str) and frame.strip():
        return f"kf-{frame.strip()}"
    return f"kf-{t_ms}"


def _keyframe_text_observations(
    row: dict[str, Any], t_ms: int, confidence: Confidence
) -> list[Observation]:
    """Emit one text Observation per non-empty OCR string."""
    out: list[Observation] = []
    ocr = row.get("ocr")
    if not isinstance(ocr, list):
        return out
    base = _keyframe_event_id(row, t_ms)
    for idx, item in enumerate(ocr):
        if not isinstance(item, str):
            continue
        subject = _clip_subject(item)
        obs = _make_observation(
            kind="text",
            subject=subject,
            event_id=f"{base}-ocr-{idx}",
            source_channel="ocr",
            t_ms=t_ms,
            confidence=confidence,
        )
        if obs is not None:
            out.append(obs)
    return out


def observations_from_keyframes(rows: list[dict[str, Any]]) -> list[Observation]:
    """Convert keyframe memory rows into text Observations."""
    out: list[Observation] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        t_ms = _t_ms_from(row)
        if t_ms is None:
            continue
        confidence = _confidence_from(row)
        out.extend(_keyframe_text_observations(row, t_ms, confidence))
    return out


def _entity_text_observations(
    row: dict[str, Any], t_ms: int, confidence: Confidence
) -> list[Observation]:
    """Emit text Observations from a row's text_objects."""
    out: list[Observation] = []
    text_objects = row.get("text_objects")
    if not isinstance(text_objects, list):
        return out
    for idx, to in enumerate(text_objects):
        if not isinstance(to, dict):
            continue
        raw = to.get("logo_or_text") or to.get("text")
        if not isinstance(raw, str):
            continue
        subject = _clip_subject(raw)
        attrs = _object_attribute(to.get("object"))
        obs = _make_observation(
            kind="text",
            subject=subject,
            event_id=f"ec-{t_ms}-text-{idx}",
            source_channel="entity_text",
            t_ms=t_ms,
            confidence=confidence,
            attributes=attrs,
        )
        if obs is not None:
            out.append(obs)
    return out


def _object_attribute(obj: Any) -> tuple[Attribute, ...]:
    """Build a single ('object', value) attribute tuple, if present."""
    if isinstance(obj, str) and obj.strip():
        return (Attribute(name="object", value=obj.strip()),)
    return ()


def _entity_object_observations(
    row: dict[str, Any], t_ms: int, confidence: Confidence
) -> list[Observation]:
    """Emit object Observations from a person's holding/object pairs."""
    out: list[Observation] = []
    persons = row.get("persons")
    if not isinstance(persons, list):
        return out
    for p_idx, person in enumerate(persons):
        if not isinstance(person, dict):
            continue
        held = person.get("holding")
        if not isinstance(held, list):
            continue
        for h_idx, item in enumerate(held):
            if not isinstance(item, str) or not item.strip():
                continue
            obs = _make_observation(
                kind="object",
                subject=item.strip(),
                event_id=f"ec-{t_ms}-obj-{p_idx}-{h_idx}",
                source_channel="entity_capture",
                t_ms=t_ms,
                confidence=confidence,
            )
            if obs is not None:
                out.append(obs)
    return out


def observations_from_entity_capture(
    rows: list[dict[str, Any]],
) -> list[Observation]:
    """Convert entity-capture rows into text and object Observations."""
    out: list[Observation] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("parse_ok") is False:
            continue
        t_ms = _t_ms_from(row)
        if t_ms is None:
            continue
        confidence = _confidence_from(row)
        out.extend(_entity_text_observations(row, t_ms, confidence))
        out.extend(_entity_object_observations(row, t_ms, confidence))
    return out


def _load_rows(path: str) -> list[dict[str, Any]]:
    """Load a file as JSON array or NDJSON; return [] on any failure."""
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return []
    return _parse_rows(text)


def _parse_rows(text: str) -> list[dict[str, Any]]:
    """Parse text as a JSON array first, then fall back to NDJSON."""
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [r for r in parsed if isinstance(r, dict)]
        if isinstance(parsed, dict):
            return [parsed]
    except json.JSONDecodeError:
        pass
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def load_observations(memory_dir: str) -> list[Observation]:
    """Load and combine keyframe + entity-capture Observations, sorted by t_ms."""
    kf_rows = _load_rows(os.path.join(memory_dir, _KF_FILE))
    entity_rows = _load_rows(os.path.join(memory_dir, _ENTITY_FILE))
    observations = observations_from_keyframes(kf_rows)
    observations.extend(observations_from_entity_capture(entity_rows))
    observations.sort(key=lambda obs: obs.t_ms)
    return observations
