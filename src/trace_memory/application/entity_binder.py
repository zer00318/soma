from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from trace_memory.domain.observation import Attribute, Observation

_TIME_WINDOW_MS = 2_000
_SUBJECT_SYNONYMS = {
    "drink bottle": "bottle",
    "glass bottle": "bottle",
    "plastic bottle": "bottle",
    "sports bottle": "bottle",
    "thermos": "bottle",
    "water bottle": "bottle",
}


@dataclass(frozen=True)
class BoundEntity:
    subject: str
    count: int
    attributes: tuple[Attribute, ...]
    first_t_ms: int
    last_t_ms: int
    frames_seen: int
    spatial_anchors: frozenset[str]
    confidence: str


def bind_entities(observations: Iterable[Observation]) -> list[BoundEntity]:
    grouped: dict[str, list[Observation]] = {}
    for observation in observations:
        if observation.kind != "object":
            continue
        subject = _normalize_subject(observation.subject)
        grouped.setdefault(subject, []).append(observation)

    entities: list[BoundEntity] = []
    for subject, subject_observations in grouped.items():
        ordered = sorted(subject_observations, key=lambda observation: (observation.t_ms, observation.provenance.event_id))
        anchors, unanchored_windows = _support_groups(ordered)
        count = len(anchors) or int(bool(unanchored_windows))
        frames_seen = len({observation.t_ms for observation in ordered})
        entities.append(
            BoundEntity(
                subject=subject,
                count=count,
                attributes=_merge_attributes(ordered),
                first_t_ms=ordered[0].t_ms,
                last_t_ms=ordered[-1].t_ms,
                frames_seen=frames_seen,
                spatial_anchors=frozenset(anchors),
                confidence=_confidence_tier(frames_seen),
            )
        )
    return sorted(entities, key=lambda entity: (entity.first_t_ms, entity.subject))


def _support_groups(observations: list[Observation]) -> tuple[set[str], list[tuple[int, int]]]:
    anchors: set[str] = set()
    windows: list[tuple[int, int]] = []
    for observation in observations:
        anchor = _normalize_anchor(observation.spatial_anchor)
        if anchor is not None:
            anchors.add(anchor)
            continue
        windows = _merge_time_window(windows, observation.t_ms)
    return anchors, windows


def _merge_time_window(windows: list[tuple[int, int]], t_ms: int) -> list[tuple[int, int]]:
    if not windows:
        return [(t_ms, t_ms)]
    start, end = windows[-1]
    if t_ms - end <= _TIME_WINDOW_MS:
        windows[-1] = (start, t_ms)
        return windows
    windows.append((t_ms, t_ms))
    return windows


def _merge_attributes(observations: list[Observation]) -> tuple[Attribute, ...]:
    merged: list[Attribute] = []
    seen: set[tuple[str, str]] = set()
    for observation in observations:
        for attribute in observation.attributes:
            key = (attribute.name.strip().lower(), attribute.value.strip().lower())
            if key in seen:
                continue
            seen.add(key)
            merged.append(attribute)
    return tuple(merged)


def _normalize_subject(subject: str) -> str:
    normalized = _singularize_phrase(subject)
    return _SUBJECT_SYNONYMS.get(normalized, normalized)


def _normalize_anchor(anchor: str | None) -> str | None:
    if anchor is None:
        return None
    tokens = re.findall(r"[a-z0-9]+", anchor.lower())
    if not tokens:
        return None
    return " ".join(tokens)


def _singularize_phrase(text: str) -> str:
    return " ".join(_singularize_token(token) for token in re.findall(r"[a-z0-9]+", text.lower()))


def _singularize_token(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("ses"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _confidence_tier(frames_seen: int) -> str:
    if frames_seen <= 2:
        return "low"
    if frames_seen <= 4:
        return "medium"
    return "high"
