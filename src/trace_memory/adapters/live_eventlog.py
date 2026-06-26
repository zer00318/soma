from __future__ import annotations

import importlib
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from trace_memory.adapters.sqlite_eventlog import SqliteEventLog
from trace_memory.application.entity_binder import BoundEntity, bind_entities, normalize_subject
from trace_memory.domain.confidence import Confidence
from trace_memory.domain.observation import Attribute, Observation
from trace_memory.domain.provenance import Provenance

HONEST_REFUSAL = "I don't have that in my memory — I didn't read enough to be sure."
OPEN_SCENE_REFUSAL = "I didn't capture anything clearly."

_CERTAINTY_CONFIDENCE = {
    "likely": 0.78,
    "uncertain": 0.42,
    "untrusted": 0.3,
}
_DEFAULT_CONFIDENCE = 0.55
_ANGLE_BUCKET_DEGREES = 15
_CONTAINER_WORDS = {
    "bag",
    "bags",
    "bottle",
    "bottles",
    "box",
    "boxes",
    "can",
    "cans",
    "container",
    "containers",
    "jar",
    "jars",
    "pack",
    "packs",
    "packet",
    "packets",
    "tin",
    "tins",
}
_COLOR_WORDS = {
    "black",
    "blue",
    "brown",
    "gold",
    "gray",
    "green",
    "grey",
    "orange",
    "pink",
    "purple",
    "red",
    "silver",
    "tan",
    "white",
    "yellow",
}
_COUNT_RE = re.compile(r"^\s*how many\s+(?P<subject>.+?)\s*\??\s*$", re.IGNORECASE)
_EXISTENCE_RE = re.compile(
    r"^\s*(?:is|are)\s+there\s+(?P<subject>.+?)\s*\??\s*$",
    re.IGNORECASE,
)
_ATTRIBUTE_RE = re.compile(
    r"^\s*what\s+(?P<attribute>colou?r|flavou?r|flavor)\s+"
    r"(?:is|are|was|were)\s+(?P<subject>.+?)\s*\??\s*$",
    re.IGNORECASE,
)
_LABEL_RE = re.compile(
    r"^\s*what\s+(?P<attribute>label|brand|text|name)\s+"
    r"(?:is|are|was|were)\s+(?:on|for)?\s*(?P<subject>.+?)\s*\??\s*$",
    re.IGNORECASE,
)
_OPEN_SCENE_PATTERNS = (
    re.compile(r"^\s*what did i see\s*\??\s*$", re.IGNORECASE),
    re.compile(r"^\s*what(?:'s| is)\s+(?:here|there)\s*\??\s*$", re.IGNORECASE),
    re.compile(r"^\s*what was around\s*\??\s*$", re.IGNORECASE),
    re.compile(r"^\s*describe what i saw\s*\??\s*$", re.IGNORECASE),
    re.compile(r"^\s*what(?:'s| is| was)\s+on\s+the\s+.+?\s*\??\s*$", re.IGNORECASE),
)
_TEMPORAL_FIRST_RE = re.compile(r"^\s*what did i see first\s*\??\s*$", re.IGNORECASE)
_TEMPORAL_ORDER_RE = re.compile(
    r"^\s*in what order(?:\s+did i see(?:\s+(?:things|objects))?)?\s*\??\s*$",
    re.IGNORECASE,
)
_TEMPORAL_RELATIVE_RE = re.compile(
    r"^\s*what came (?P<relation>before|after)\s+(?P<subject>.+?)\s*\??\s*$",
    re.IGNORECASE,
)
_SPATIAL_RELATIVE_RE = re.compile(
    r"^\s*which side was\s+(?P<subject>.+?)\s+relative to\s+(?P<reference>.+?)\s*\??\s*$",
    re.IGNORECASE,
)
_SPATIAL_SIDE_OF_RE = re.compile(
    r"^\s*what was to the\s+(?P<direction>left|right)\s+of\s+(?P<reference>.+?)\s*\??\s*$",
    re.IGNORECASE,
)
_SPATIAL_SIDE_RE = re.compile(r"^\s*which side was\s+(?P<subject>.+?)\s*\??\s*$", re.IGNORECASE)
_SPATIAL_WHERE_RE = re.compile(r"^\s*where was\s+(?P<subject>.+?)\s*\??\s*$", re.IGNORECASE)
_SCENE_CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2}
_YAW_ANCHOR_RE = re.compile(r"(?:^|\|)\s*yaw:(?P<yaw>-?\d+)deg(?:\||$)", re.IGNORECASE)


@dataclass(frozen=True)
class EventLogAnswer:
    supported: bool
    answer: str
    refused: bool
    citations: tuple[Observation, ...]
    personal_evidence: str = ""
    world_context: str = ""


def append_perception_observations(
    db_path: str | Path,
    *,
    moment_id: str,
    t_seconds: float,
    memory_text: str,
    ocr_lines: Sequence[str],
    pose: Mapping[str, Any] | None = None,
    location_hint: str | None = None,
) -> int:
    spatial_anchor = _pose_spatial_anchor(pose, location_hint=location_hint)
    observations = _build_observations(
        moment_id=moment_id,
        t_seconds=t_seconds,
        memory_text=memory_text,
        ocr_lines=ocr_lines,
        spatial_anchor=spatial_anchor,
    )
    if not observations:
        return 0
    log = SqliteEventLog(str(db_path))
    try:
        for observation in observations:
            log.append(observation)
    finally:
        log.close()
    return len(observations)


def answer_question(
    question: str,
    db_path: str | Path,
    *,
    world_knowledge_oracle: Callable[[str], str] | None = None,
) -> EventLogAnswer:
    parsed = _parse_question(question)
    if parsed is None:
        return EventLogAnswer(supported=False, answer="", refused=False, citations=())

    log = SqliteEventLog(str(db_path))
    try:
        observations = log.observations()
    finally:
        log.close()

    if parsed.intent == "open_scene":
        object_observations = tuple(
            observation for observation in observations if observation.kind == "object"
        )
        bound_entities = bind_entities(object_observations)
        return _open_scene_answer(
            bound_entities,
            object_observations,
            world_knowledge_oracle,
        )

    if parsed.intent in {
        "temporal_first",
        "temporal_order",
        "temporal_relative",
        "spatial_where",
        "spatial_side",
        "spatial_relative",
        "spatial_side_of",
    }:
        return _spatial_temporal_answer(parsed, observations)

    object_matches = _matching_objects(parsed.subject, observations)
    if not object_matches:
        return EventLogAnswer(
            supported=True,
            answer=HONEST_REFUSAL,
            refused=True,
            citations=(),
        )

    bound_entities = bind_entities(object_matches)

    if parsed.intent == "count":
        count = sum(entity.count for entity in bound_entities)
        noun = parsed.subject if count != 1 else _singularize_phrase(parsed.subject)
        if bound_entities and all(entity.confidence == "low" for entity in bound_entities):
            pronoun = "it" if count == 1 else "them"
            personal_answer = (
                f"I saw at least {count} {noun}, but I can't reliably count {pronoun} yet."
            )
        else:
            personal_answer = f"I saw {count} {noun}."
        personal_evidence, world_context, answer = _compose_two_zone_answer(
            personal_answer,
            object_matches,
            _entity_referents(object_matches),
            world_knowledge_oracle,
        )
        return EventLogAnswer(
            supported=True,
            answer=answer,
            refused=False,
            citations=object_matches,
            personal_evidence=personal_evidence,
            world_context=world_context,
        )

    if parsed.intent == "exists":
        noun = _singularize_phrase(parsed.subject)
        article = "an" if noun[:1] in "aeiou" else "a"
        personal_evidence, world_context, answer = _compose_two_zone_answer(
            f"Yes, I saw {article} {noun}.",
            object_matches[:1],
            _entity_referents(object_matches),
            world_knowledge_oracle,
        )
        return EventLogAnswer(
            supported=True,
            answer=answer,
            refused=False,
            citations=object_matches[:1],
            personal_evidence=personal_evidence,
            world_context=world_context,
        )

    attribute_value = _attribute_answer(parsed.attribute, object_matches, observations)
    if attribute_value is None:
        return EventLogAnswer(
            supported=True,
            answer=HONEST_REFUSAL,
            refused=True,
            citations=(),
        )
    personal_evidence, world_context, answer = _compose_two_zone_answer(
        f"The {_singularize_phrase(parsed.subject)} is {attribute_value}.",
        object_matches[:1],
        _entity_referents(object_matches),
        world_knowledge_oracle,
    )
    return EventLogAnswer(
        supported=True,
        answer=answer,
        refused=False,
        citations=object_matches[:1],
        personal_evidence=personal_evidence,
        world_context=world_context,
    )


@dataclass(frozen=True)
class _ParsedQuestion:
    intent: str
    subject: str
    attribute: str | None = None
    reference: str | None = None
    direction: str | None = None


@dataclass(frozen=True)
class _ObjectEntitySummary:
    key: str
    display_subject: str
    first_t_ms: int
    first_observation: Observation
    observations: tuple[Observation, ...]
    match_texts: tuple[str, ...]


@dataclass(frozen=True)
class _SpatialFix:
    display_subject: str
    yaw_degrees: int
    observation: Observation


def _build_observations(
    *,
    moment_id: str,
    t_seconds: float,
    memory_text: str,
    ocr_lines: Sequence[str],
    spatial_anchor: str | None,
) -> tuple[Observation, ...]:
    t_ms = max(0, round(float(t_seconds) * 1000))
    observations: list[Observation] = []
    line_index = 0
    for raw_line in memory_text.splitlines():
        observation = _line_observation(
            raw_line,
            moment_id=moment_id,
            t_ms=t_ms,
            line_index=line_index,
            spatial_anchor=spatial_anchor,
        )
        if observation is not None:
            observations.append(observation)
            line_index += 1
    for ocr_index, ocr_line in enumerate(ocr_lines):
        text = str(ocr_line).strip()
        if not text:
            continue
        observations.append(
            Observation(
                kind="text",
                subject="text surface",
                attributes=(Attribute("text", text),),
                t_ms=t_ms,
                spatial_anchor=spatial_anchor,
                confidence=Confidence(_DEFAULT_CONFIDENCE),
                provenance=Provenance(
                    event_id=f"{moment_id}:{t_ms}:ocr:{ocr_index}",
                    source_channel="ocr",
                    captured_at_ms=t_ms,
                ),
            )
        )
    return tuple(observations)


def _line_observation(
    raw_line: str,
    *,
    moment_id: str,
    t_ms: int,
    line_index: int,
    spatial_anchor: str | None,
) -> Observation | None:
    cleaned = " ".join(raw_line.strip().split())
    if not cleaned:
        return None
    parts = [part.strip() for part in cleaned.split("|")]
    if len(parts) < 3:
        return None
    prefix = parts[0].lower()
    if prefix not in {"object", "event"}:
        return None

    certainty = _certainty_token(parts[-1])
    detail, parsed_spatial_anchor = _detail_and_anchor(parts, has_certainty=certainty is not None)
    return Observation(
        kind=prefix,
        subject=parts[1],
        attributes=(Attribute("detail", detail),) if detail else (),
        t_ms=t_ms,
        spatial_anchor=spatial_anchor if spatial_anchor is not None else parsed_spatial_anchor,
        confidence=Confidence(_CERTAINTY_CONFIDENCE.get(certainty or "", _DEFAULT_CONFIDENCE)),
        provenance=Provenance(
            event_id=f"{moment_id}:{t_ms}:{prefix}:{line_index}",
            source_channel="vlm",
            captured_at_ms=t_ms,
        ),
    )


def _pose_spatial_anchor(
    pose: Mapping[str, Any] | None,
    *,
    location_hint: str | None,
) -> str | None:
    if not pose:
        return None
    yaw = _pose_angle_degrees(pose.get("yaw"), pose)
    pitch = _pose_angle_degrees(pose.get("pitch"), pose)
    if yaw is None and pitch is None:
        return None

    parts: list[str] = []
    if yaw is not None:
        parts.append(f"yaw:{_bucket_heading_degrees(yaw)}deg")
    if pitch is not None:
        parts.append(f"pitch:{_bucket_tilt_degrees(pitch)}deg")
    cleaned_location = re.sub(r"\s+", " ", str(location_hint or "").strip())
    if cleaned_location:
        parts.append(cleaned_location)
    return "|".join(parts) or None


def _pose_angle_degrees(value: object, pose: Mapping[str, Any]) -> float | None:
    numeric = _float_or_none(value)
    if numeric is None:
        return None
    if _pose_uses_radians(pose):
        return math.degrees(numeric)
    return numeric


def _pose_uses_radians(pose: Mapping[str, Any]) -> bool:
    if any(_float_or_none(pose.get(key)) is not None for key in ("qw", "qx", "qy", "qz")):
        return True
    angles = [
        abs(value)
        for key in ("yaw", "pitch", "roll")
        if (value := _float_or_none(pose.get(key))) is not None
    ]
    return bool(angles) and max(angles) <= math.pi


def _bucket_heading_degrees(angle_degrees: float) -> int:
    wrapped = angle_degrees % 360.0
    bucket = math.floor((wrapped + (_ANGLE_BUCKET_DEGREES / 2.0)) / _ANGLE_BUCKET_DEGREES)
    return int((bucket * _ANGLE_BUCKET_DEGREES) % 360)


def _bucket_tilt_degrees(angle_degrees: float) -> int:
    clamped = max(-90.0, min(90.0, angle_degrees))
    shifted = clamped + 90.0
    bucket = math.floor((shifted + (_ANGLE_BUCKET_DEGREES / 2.0)) / _ANGLE_BUCKET_DEGREES)
    quantized = int((bucket * _ANGLE_BUCKET_DEGREES) - 90)
    return max(-90, min(90, quantized))


def _float_or_none(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _certainty_token(token: str) -> str | None:
    normalized = token.strip().lower()
    return normalized if normalized in _CERTAINTY_CONFIDENCE else None


def _detail_and_anchor(parts: Sequence[str], *, has_certainty: bool) -> tuple[str, str | None]:
    end = len(parts) - 1 if has_certainty else len(parts)
    body = list(parts[2:end])
    if not body:
        return "", None
    if len(body) == 1:
        return body[0], None
    return " | ".join(body[:-1]), body[-1]


def _parse_question(question: str) -> _ParsedQuestion | None:
    normalized = re.sub(r"\s+", " ", question or "").strip()
    if not normalized:
        return None
    match = _TEMPORAL_FIRST_RE.match(normalized)
    if match:
        return _ParsedQuestion(intent="temporal_first", subject="")
    match = _TEMPORAL_ORDER_RE.match(normalized)
    if match:
        return _ParsedQuestion(intent="temporal_order", subject="")
    match = _TEMPORAL_RELATIVE_RE.match(normalized)
    if match:
        return _ParsedQuestion(
            intent="temporal_relative",
            subject=_clean_subject(match.group("subject")),
            direction=match.group("relation").lower(),
        )
    match = _SPATIAL_RELATIVE_RE.match(normalized)
    if match:
        return _ParsedQuestion(
            intent="spatial_relative",
            subject=_clean_subject(match.group("subject")),
            reference=_clean_subject(match.group("reference")),
        )
    match = _SPATIAL_SIDE_OF_RE.match(normalized)
    if match:
        return _ParsedQuestion(
            intent="spatial_side_of",
            subject="",
            reference=_clean_subject(match.group("reference")),
            direction=match.group("direction").lower(),
        )
    match = _SPATIAL_SIDE_RE.match(normalized)
    if match:
        return _ParsedQuestion(
            intent="spatial_side",
            subject=_clean_subject(match.group("subject")),
        )
    match = _SPATIAL_WHERE_RE.match(normalized)
    if match:
        return _ParsedQuestion(
            intent="spatial_where",
            subject=_clean_subject(match.group("subject")),
        )
    for pattern in _OPEN_SCENE_PATTERNS:
        if pattern.match(normalized):
            return _ParsedQuestion(intent="open_scene", subject="")
    match = _COUNT_RE.match(normalized)
    if match:
        return _ParsedQuestion(intent="count", subject=_clean_subject(match.group("subject")))
    match = _EXISTENCE_RE.match(normalized)
    if match:
        return _ParsedQuestion(intent="exists", subject=_clean_subject(match.group("subject")))
    match = _ATTRIBUTE_RE.match(normalized)
    if match:
        attribute = match.group("attribute").lower()
        if attribute == "color":
            attribute = "colour"
        if attribute == "flavor":
            attribute = "flavour"
        return _ParsedQuestion(
            intent="attribute",
            subject=_clean_subject(match.group("subject")),
            attribute=attribute,
        )
    match = _LABEL_RE.match(normalized)
    if match:
        return _ParsedQuestion(
            intent="attribute",
            subject=_clean_subject(match.group("subject")),
            attribute="label",
        )
    return None


def _compose_two_zone_answer(
    personal_answer: str,
    citations: Sequence[Observation],
    referents: Sequence[str],
    world_knowledge_oracle: Callable[[str], str] | None,
) -> tuple[str, str, str]:
    personal_evidence = _append_time_citations(personal_answer, citations)
    expand_module = _load_inject_expand()
    packet = _world_context_packet(referents, world_knowledge_oracle, expand_module)
    if expand_module is None or packet is None:
        return personal_evidence, "", personal_evidence
    world_context = expand_module.compose("", packet)
    return personal_evidence, world_context, expand_module.compose(personal_evidence, packet)


def _append_time_citations(answer: str, citations: Sequence[Observation]) -> str:
    note = _time_citation_note(citations)
    if not note:
        return answer
    return f"{answer} {note}"


def _time_citation_note(citations: Sequence[Observation]) -> str:
    seen: set[int] = set()
    labels: list[str] = []
    for observation in citations:
        if observation.t_ms in seen:
            continue
        seen.add(observation.t_ms)
        labels.append(f"{observation.t_ms / 1000.0:.1f}s")
    if not labels:
        return ""
    if len(labels) <= 4:
        return f"(seen at {', '.join(labels)})"
    return f"(seen at {', '.join(labels[:4])}, +{len(labels) - 4} more)"


def _open_scene_answer(
    bound_entities: Sequence[BoundEntity],
    observations: Sequence[Observation],
    world_knowledge_oracle: Callable[[str], str] | None,
) -> EventLogAnswer:
    summary_entities = _scene_summary_entities(bound_entities)
    if not summary_entities:
        return EventLogAnswer(
            supported=True,
            answer=OPEN_SCENE_REFUSAL,
            refused=True,
            citations=(),
        )

    personal_answer = f"You saw {_join_scene_items(_scene_item(entity) for entity in summary_entities)}."
    citations = _scene_citations(summary_entities, observations)
    referents = _scene_referents(summary_entities)
    personal_evidence, world_context, answer = _compose_two_zone_answer(
        personal_answer,
        citations,
        referents,
        world_knowledge_oracle,
    )
    return EventLogAnswer(
        supported=True,
        answer=answer,
        refused=False,
        citations=citations,
        personal_evidence=personal_evidence,
        world_context=world_context,
    )


def _scene_summary_entities(bound_entities: Sequence[BoundEntity]) -> list[BoundEntity]:
    visible = [
        entity
        for entity in bound_entities
        if entity.confidence in {"high", "medium"}
    ]
    return sorted(
        visible,
        key=lambda entity: (
            _SCENE_CONFIDENCE_ORDER.get(entity.confidence, 99),
            -entity.last_t_ms,
            -entity.frames_seen,
            entity.subject,
        ),
    )


def _scene_item(entity: BoundEntity) -> str:
    subject = _scene_subject(entity)
    colour = _entity_colour(entity)
    if colour and colour not in subject.split():
        subject = f"{colour} {subject}"
    qualifier = _entity_qualifier(entity, subject)
    if qualifier:
        return f"{subject} ({qualifier})"
    return subject


def _scene_subject(entity: BoundEntity) -> str:
    if entity.source_subjects:
        subject = max(
            entity.source_subjects,
            key=lambda subject: (len(subject.split()), len(subject), subject),
        )
        return _singularize_display_subject(subject)
    return entity.subject


def _singularize_display_subject(subject: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", subject.lower())
    if not tokens:
        return subject
    display: list[str] = []
    for token in tokens:
        if token in _CONTAINER_WORDS:
            display.append(_singularize_token(token))
            continue
        display.append(token)
    return " ".join(display)


def _entity_detail_values(entity: BoundEntity) -> tuple[str, ...]:
    return tuple(
        attribute.value.lower()
        for attribute in entity.attributes
        if attribute.name == "detail"
    )


def _entity_colour(entity: BoundEntity) -> str | None:
    for detail in _entity_detail_values(entity):
        for colour in sorted(_COLOR_WORDS, key=len, reverse=True):
            if re.search(rf"\b{re.escape(colour)}\b", detail):
                return colour
    return None


def _entity_qualifier(entity: BoundEntity, subject: str) -> str | None:
    for detail in _entity_detail_values(entity):
        flavour = _extract_flavour(detail)
        if flavour:
            return flavour
    label = _entity_label(entity)
    if label and _normalized_text(label) not in _normalized_text(subject):
        return label
    return None


def _normalized_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _entity_label(entity: BoundEntity) -> str | None:
    for detail in _entity_detail_values(entity):
        label = _extract_label(detail)
        if label:
            return label
    return None


def _join_scene_items(items: Iterable[str]) -> str:
    labelled = [_with_indefinite_article(item) for item in items if item]
    if not labelled:
        return ""
    if len(labelled) == 1:
        return labelled[0]
    if len(labelled) == 2:
        return f"{labelled[0]} and {labelled[1]}"
    return ", ".join(labelled[:-1]) + f", and {labelled[-1]}"


def _with_indefinite_article(text: str) -> str:
    article = "an" if text[:1].lower() in {"a", "e", "i", "o", "u"} else "a"
    return f"{article} {text}"


def _scene_citations(
    summary_entities: Sequence[BoundEntity],
    observations: Sequence[Observation],
) -> tuple[Observation, ...]:
    grouped: dict[str, list[Observation]] = {}
    for observation in observations:
        grouped.setdefault(normalize_subject(observation.subject), []).append(observation)

    citations: list[Observation] = []
    seen_times: set[int] = set()
    for entity in summary_entities:
        candidates = sorted(
            grouped.get(entity.subject, ()),
            key=lambda observation: (observation.t_ms, observation.provenance.event_id),
            reverse=True,
        )
        for target_t_ms in (entity.last_t_ms, entity.first_t_ms):
            for candidate in candidates:
                if candidate.t_ms != target_t_ms or candidate.t_ms in seen_times:
                    continue
                citations.append(candidate)
                seen_times.add(candidate.t_ms)
                break
            if len(citations) >= 2:
                return tuple(citations)
    return tuple(citations)


def _scene_referents(summary_entities: Sequence[BoundEntity]) -> tuple[str, ...]:
    referents: list[str] = []
    seen: set[str] = set()
    for entity in summary_entities:
        referent = _scene_referent(entity)
        key = referent.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        referents.append(referent)
    return tuple(referents)


def _scene_referent(entity: BoundEntity) -> str:
    subject = _scene_subject(entity)
    label = _entity_label(entity)
    if label and _normalized_text(label) not in _normalized_text(subject):
        return label
    return subject


def _entity_referents(observations: Sequence[Observation]) -> tuple[str, ...]:
    referents: list[str] = []
    seen: set[str] = set()
    for observation in observations:
        subject = observation.subject.strip()
        key = subject.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        referents.append(subject)
    return tuple(referents)


def _load_inject_expand():
    for module_name in ("scripts.inject_expand", "inject_expand"):
        try:
            return importlib.import_module(module_name)
        except Exception:
            continue
    return None


def _world_context_packet(
    referents: Sequence[str],
    world_knowledge_oracle: Callable[[str], str] | None,
    expand_module,
) -> dict[str, list[dict[str, object]]] | None:
    if expand_module is None or world_knowledge_oracle is None:
        return None
    try:
        world_context = []
        for referent in referents[:3]:
            gloss = expand_module.world_gloss(referent, world_knowledge_oracle)
            if gloss is not None:
                world_context.append(gloss)
    except Exception:
        return None
    if not world_context:
        return None
    return {"world_context": world_context}


def _clean_subject(subject: str) -> str:
    cleaned = re.sub(r"\s+", " ", subject.strip().rstrip("?.!"))
    stripped = re.sub(r"^(?:the|a|an|any)\s+", "", cleaned, flags=re.IGNORECASE)
    return stripped or cleaned


def _spatial_temporal_answer(
    parsed: _ParsedQuestion,
    observations: Sequence[Observation],
) -> EventLogAnswer:
    object_observations = tuple(
        observation for observation in observations if observation.kind == "object"
    )
    summaries = _object_entity_summaries(object_observations)
    if parsed.intent == "temporal_first":
        return _temporal_first_answer(summaries)
    if parsed.intent == "temporal_order":
        return _temporal_order_answer(summaries)
    if parsed.intent == "temporal_relative":
        return _temporal_relative_answer(summaries, parsed.subject, parsed.direction or "")
    if parsed.intent == "spatial_where":
        return _spatial_where_answer(summaries, parsed.subject)
    if parsed.intent == "spatial_side":
        return _spatial_side_answer(summaries, parsed.subject)
    if parsed.intent == "spatial_relative":
        return _spatial_relative_answer(summaries, parsed.subject, parsed.reference or "")
    if parsed.intent == "spatial_side_of":
        return _spatial_side_of_answer(summaries, parsed.reference or "", parsed.direction or "")
    return EventLogAnswer(supported=False, answer="", refused=False, citations=())


def _object_entity_summaries(
    object_observations: Sequence[Observation],
) -> tuple[_ObjectEntitySummary, ...]:
    grouped: dict[str, list[Observation]] = {}
    for observation in object_observations:
        grouped.setdefault(normalize_subject(observation.subject), []).append(observation)

    summaries: list[_ObjectEntitySummary] = []
    for entity in bind_entities(object_observations):
        ordered = sorted(
            grouped.get(entity.subject, ()),
            key=lambda observation: (observation.t_ms, observation.provenance.event_id),
        )
        if not ordered:
            continue
        match_texts = tuple(
            text for text in (entity.subject, *entity.source_subjects) if text
        )
        summaries.append(
            _ObjectEntitySummary(
                key=entity.subject,
                display_subject=_scene_subject(entity),
                first_t_ms=entity.first_t_ms,
                first_observation=ordered[0],
                observations=tuple(ordered),
                match_texts=match_texts,
            )
        )
    return tuple(sorted(summaries, key=lambda summary: (summary.first_t_ms, summary.display_subject)))


def _temporal_first_answer(summaries: Sequence[_ObjectEntitySummary]) -> EventLogAnswer:
    if not summaries:
        return _refusal_answer()
    first_t_ms = summaries[0].first_t_ms
    first_subjects = [summary for summary in summaries if summary.first_t_ms == first_t_ms]
    if len(first_subjects) == 1:
        answer = (
            f"The first thing you saw was {first_subjects[0].display_subject} "
            f"at {_format_time_ms(first_t_ms)}."
        )
    else:
        answer = (
            f"The first things you saw were {_join_phrases(summary.display_subject for summary in first_subjects)} "
            f"at {_format_time_ms(first_t_ms)}."
        )
    return _supported_answer(answer, tuple(summary.first_observation for summary in first_subjects))


def _temporal_order_answer(summaries: Sequence[_ObjectEntitySummary]) -> EventLogAnswer:
    if not summaries:
        return _refusal_answer()
    ordered = ", then ".join(
        f"{summary.display_subject} at {_format_time_ms(summary.first_t_ms)}"
        for summary in summaries
    )
    return _supported_answer(
        f"In order, you saw {ordered}.",
        tuple(summary.first_observation for summary in summaries),
    )


def _temporal_relative_answer(
    summaries: Sequence[_ObjectEntitySummary],
    subject: str,
    direction: str,
) -> EventLogAnswer:
    summary = _find_summary(subject, summaries)
    if summary is None:
        return _refusal_answer()
    if direction == "before":
        related = [candidate for candidate in summaries if candidate.first_t_ms < summary.first_t_ms]
        prefix = "Before"
    else:
        related = [candidate for candidate in summaries if candidate.first_t_ms > summary.first_t_ms]
        prefix = "After"
    if not related:
        answer = f"{prefix} {summary.display_subject}, I didn't see any other grounded object."
        return _supported_answer(answer, (summary.first_observation,))
    ordered = ", then ".join(
        f"{candidate.display_subject} at {_format_time_ms(candidate.first_t_ms)}"
        for candidate in related
    )
    citations = tuple(candidate.first_observation for candidate in related)
    return _supported_answer(f"{prefix} {summary.display_subject}, you saw {ordered}.", citations)


def _spatial_where_answer(
    summaries: Sequence[_ObjectEntitySummary],
    subject: str,
) -> EventLogAnswer:
    summary = _find_summary(subject, summaries)
    if summary is None:
        return _refusal_answer()
    fixes = _distinct_spatial_fixes(summary)
    if not fixes:
        return _supported_answer(
            f"I saw {summary.display_subject}, but I didn't track exactly where it was.",
            (summary.first_observation,),
        )
    if len(fixes) == 1:
        fix = fixes[0]
        answer = (
            f"I saw {summary.display_subject} around yaw {fix.yaw_degrees}deg "
            f"at {_format_time_ms(fix.observation.t_ms)}."
        )
        return _supported_answer(answer, (fix.observation,))
    positions = ", then ".join(
        f"yaw {fix.yaw_degrees}deg at {_format_time_ms(fix.observation.t_ms)}"
        for fix in fixes
    )
    return _supported_answer(
        f"I saw {summary.display_subject} at multiple headings: {positions}.",
        tuple(fix.observation for fix in fixes),
    )


def _spatial_side_answer(
    summaries: Sequence[_ObjectEntitySummary],
    subject: str,
) -> EventLogAnswer:
    summary = _find_summary(subject, summaries)
    if summary is None:
        return _refusal_answer()
    subject_fix = _single_spatial_fix(summary)
    if subject_fix is None:
        return _supported_answer(
            f"I saw {summary.display_subject}, but I didn't track exactly where it was.",
            (summary.first_observation,),
        )
    anchored_others = [
        (candidate, fix)
        for candidate in summaries
        if candidate.key != summary.key
        if (fix := _single_spatial_fix(candidate)) is not None
    ]
    if not anchored_others:
        return _supported_answer(
            (
                f"I saw {summary.display_subject} around yaw {subject_fix.yaw_degrees}deg "
                f"at {_format_time_ms(subject_fix.observation.t_ms)}, but I don't have another "
                "anchored object to compare it against."
            ),
            (subject_fix.observation,),
        )
    if len(anchored_others) == 1:
        other_summary, other_fix = anchored_others[0]
        direction = _relative_direction(subject_fix.yaw_degrees, other_fix.yaw_degrees)
        if direction == "same":
            answer = f"{summary.display_subject} was at the same heading as {other_summary.display_subject}."
        else:
            answer = f"{summary.display_subject} was to the {direction} of {other_summary.display_subject}."
        return _supported_answer(answer, (subject_fix.observation, other_fix.observation))
    other_yaws = [fix.yaw_degrees for _, fix in anchored_others]
    if subject_fix.yaw_degrees < min(other_yaws):
        descriptor = "left"
    elif subject_fix.yaw_degrees > max(other_yaws):
        descriptor = "right"
    else:
        descriptor = "between"
    if descriptor == "between":
        answer = f"{summary.display_subject} was between the other anchored objects."
    else:
        answer = f"{summary.display_subject} was on the {descriptor} side of the scene."
    citations = (subject_fix.observation, *(fix.observation for _, fix in anchored_others[:2]))
    return _supported_answer(answer, citations)


def _spatial_relative_answer(
    summaries: Sequence[_ObjectEntitySummary],
    subject: str,
    reference: str,
) -> EventLogAnswer:
    subject_summary = _find_summary(subject, summaries)
    reference_summary = _find_summary(reference, summaries)
    if subject_summary is None or reference_summary is None:
        return _refusal_answer()
    subject_fix = _single_spatial_fix(subject_summary)
    reference_fix = _single_spatial_fix(reference_summary)
    if subject_fix is None or reference_fix is None:
        answer = (
            f"I saw {subject_summary.display_subject} and {reference_summary.display_subject}, "
            "but I didn't track exactly where they were."
        )
        citations = (subject_summary.first_observation, reference_summary.first_observation)
        return _supported_answer(answer, citations)
    direction = _relative_direction(subject_fix.yaw_degrees, reference_fix.yaw_degrees)
    if direction == "same":
        answer = (
            f"{subject_summary.display_subject} was at the same heading as "
            f"{reference_summary.display_subject}."
        )
    else:
        answer = (
            f"{subject_summary.display_subject} was to the {direction} of "
            f"{reference_summary.display_subject}."
        )
    return _supported_answer(answer, (subject_fix.observation, reference_fix.observation))


def _spatial_side_of_answer(
    summaries: Sequence[_ObjectEntitySummary],
    reference: str,
    direction: str,
) -> EventLogAnswer:
    reference_summary = _find_summary(reference, summaries)
    if reference_summary is None:
        return _refusal_answer()
    reference_fix = _single_spatial_fix(reference_summary)
    if reference_fix is None:
        return _supported_answer(
            f"I saw {reference_summary.display_subject}, but I didn't track exactly where it was.",
            (reference_summary.first_observation,),
        )
    matches: list[tuple[_ObjectEntitySummary, _SpatialFix]] = []
    for candidate in summaries:
        if candidate.key == reference_summary.key:
            continue
        candidate_fix = _single_spatial_fix(candidate)
        if candidate_fix is None:
            continue
        if _relative_direction(candidate_fix.yaw_degrees, reference_fix.yaw_degrees) == direction:
            matches.append((candidate, candidate_fix))
    if not matches:
        answer = f"I didn't see any grounded object to the {direction} of {reference_summary.display_subject}."
        return _supported_answer(answer, (reference_fix.observation,))
    ordered = ", then ".join(
        f"{candidate.display_subject} at {_format_time_ms(candidate_fix.observation.t_ms)}"
        for candidate, candidate_fix in matches
    )
    citations = tuple(candidate_fix.observation for _, candidate_fix in matches)
    return _supported_answer(
        f"To the {direction} of {reference_summary.display_subject}, you saw {ordered}.",
        citations,
    )


def _find_summary(
    subject: str,
    summaries: Sequence[_ObjectEntitySummary],
) -> _ObjectEntitySummary | None:
    for summary in summaries:
        if any(_subject_query_matches(subject, text) for text in summary.match_texts):
            return summary
    return None


def _subject_query_matches(query: str, candidate_text: str) -> bool:
    query_tokens = _subject_tokens(query)
    candidate_tokens = _subject_tokens(candidate_text)
    if not query_tokens or not candidate_tokens:
        return False
    if query_tokens.issubset(candidate_tokens):
        return True
    relaxed_query = _relaxed_subject_tokens(query)
    return bool(relaxed_query) and relaxed_query == _relaxed_subject_tokens(candidate_text)


def _distinct_spatial_fixes(summary: _ObjectEntitySummary) -> tuple[_SpatialFix, ...]:
    fixes: list[_SpatialFix] = []
    seen_yaws: set[int] = set()
    for observation in summary.observations:
        yaw_degrees = _spatial_anchor_yaw(observation.spatial_anchor)
        if yaw_degrees is None or yaw_degrees in seen_yaws:
            continue
        seen_yaws.add(yaw_degrees)
        fixes.append(
            _SpatialFix(
                display_subject=summary.display_subject,
                yaw_degrees=yaw_degrees,
                observation=observation,
            )
        )
    return tuple(fixes)


def _single_spatial_fix(summary: _ObjectEntitySummary) -> _SpatialFix | None:
    fixes = _distinct_spatial_fixes(summary)
    if len(fixes) != 1:
        return None
    return fixes[0]


def _spatial_anchor_yaw(anchor: str | None) -> int | None:
    if not anchor:
        return None
    match = _YAW_ANCHOR_RE.search(anchor)
    if not match:
        return None
    return int(match.group("yaw"))


def _relative_direction(subject_yaw: int, reference_yaw: int) -> str:
    if subject_yaw < reference_yaw:
        return "left"
    if subject_yaw > reference_yaw:
        return "right"
    return "same"


def _supported_answer(answer: str, citations: Sequence[Observation]) -> EventLogAnswer:
    return EventLogAnswer(
        supported=True,
        answer=answer,
        refused=False,
        citations=tuple(citations),
        personal_evidence=answer,
        world_context="",
    )


def _refusal_answer() -> EventLogAnswer:
    return EventLogAnswer(
        supported=True,
        answer=HONEST_REFUSAL,
        refused=True,
        citations=(),
        personal_evidence="",
        world_context="",
    )


def _format_time_ms(t_ms: int) -> str:
    return f"{t_ms / 1000.0:.1f}s"


def _join_phrases(items: Iterable[str]) -> str:
    phrases = [item for item in items if item]
    if not phrases:
        return ""
    if len(phrases) == 1:
        return phrases[0]
    if len(phrases) == 2:
        return f"{phrases[0]} and {phrases[1]}"
    return ", ".join(phrases[:-1]) + f", and {phrases[-1]}"


def _matching_objects(subject: str, observations: Iterable[Observation]) -> tuple[Observation, ...]:
    query_tokens = _subject_tokens(subject)
    relaxed_query = _relaxed_subject_tokens(subject)
    matches: list[Observation] = []
    for observation in observations:
        if observation.kind != "object":
            continue
        object_tokens = _subject_tokens(observation.subject)
        if not object_tokens:
            continue
        if query_tokens.issubset(object_tokens):
            matches.append(observation)
            continue
        if relaxed_query and relaxed_query == _relaxed_subject_tokens(observation.subject):
            matches.append(observation)
    return tuple(matches)


def _subject_tokens(text: str) -> set[str]:
    return {_singularize_token(token) for token in re.findall(r"[a-z0-9]+", text.lower())}


def _relaxed_subject_tokens(text: str) -> set[str]:
    return {token for token in _subject_tokens(text) if token not in _CONTAINER_WORDS}


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


def _attribute_answer(
    attribute: str | None,
    object_matches: Sequence[Observation],
    observations: Sequence[Observation],
) -> str | None:
    if attribute == "colour":
        return _colour_value(object_matches)
    if attribute == "flavour":
        return _flavour_value(object_matches, observations)
    if attribute == "label":
        return _label_value(object_matches, observations)
    return None


def _colour_value(object_matches: Sequence[Observation]) -> str | None:
    for observation in object_matches:
        text = _detail_attribute_text(observation)
        for colour in _COLOR_WORDS:
            if re.search(rf"\b{re.escape(colour)}\b", text):
                return colour
    return None


def _flavour_value(
    object_matches: Sequence[Observation],
    observations: Sequence[Observation],
) -> str | None:
    for observation in object_matches:
        detail = _detail_attribute_text(observation)
        value = _extract_flavour(detail)
        if value:
            return value
        for text in _supporting_texts(observation, observations):
            value = _extract_flavour(text)
            if value:
                return value
    return None


def _label_value(
    object_matches: Sequence[Observation],
    observations: Sequence[Observation],
) -> str | None:
    for observation in object_matches:
        detail = _detail_attribute_text(observation)
        value = _extract_label(detail)
        if value:
            return value
        supporting_texts = _supporting_texts(observation, observations)
        if supporting_texts:
            return supporting_texts[0]
    return None


def _extract_flavour(text: str) -> str | None:
    patterns = (
        re.compile(r"\bflavou?r[:=]\s*([a-z0-9&' /-]+)", re.IGNORECASE),
        re.compile(r"\b([a-z0-9&' /-]+?)\s+flavou?r\b", re.IGNORECASE),
    )
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            value = re.sub(r"\s+", " ", match.group(1)).strip(" .,:;/-")
            if value:
                return value
    return None


def _extract_label(text: str) -> str | None:
    patterns = (
        re.compile(r"\b(?:label|brand|name|text)[:=]\s*([a-z0-9&' /-]+)", re.IGNORECASE),
    )
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            value = re.sub(r"\s+", " ", match.group(1)).strip(" .,:;/-")
            if value:
                return value
    return None


def _supporting_texts(observation: Observation, observations: Sequence[Observation]) -> tuple[str, ...]:
    texts: list[str] = []
    for candidate in observations:
        if candidate.kind != "text" or candidate.t_ms != observation.t_ms:
            continue
        for attribute in candidate.attributes:
            if attribute.name == "text":
                texts.append(attribute.value.lower())
    return tuple(texts)


def _detail_text(observation: Observation) -> str:
    values = [_detail_attribute_text(observation)]
    if observation.spatial_anchor:
        values.append(observation.spatial_anchor.lower())
    return " ".join(value for value in values if value)


def _detail_attribute_text(observation: Observation) -> str:
    values = [attribute.value.lower() for attribute in observation.attributes if attribute.name == "detail"]
    return " ".join(values)
