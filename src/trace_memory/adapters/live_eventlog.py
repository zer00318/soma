from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from trace_memory.adapters.sqlite_eventlog import SqliteEventLog
from trace_memory.application.entity_binder import bind_entities
from trace_memory.domain.confidence import Confidence
from trace_memory.domain.observation import Attribute, Observation
from trace_memory.domain.provenance import Provenance

HONEST_REFUSAL = "I don't have that in my memory — I didn't read enough to be sure."

_CERTAINTY_CONFIDENCE = {
    "likely": 0.78,
    "uncertain": 0.42,
    "untrusted": 0.3,
}
_DEFAULT_CONFIDENCE = 0.55
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


@dataclass(frozen=True)
class EventLogAnswer:
    supported: bool
    answer: str
    refused: bool
    citations: tuple[Observation, ...]


def append_perception_observations(
    db_path: str | Path,
    *,
    moment_id: str,
    t_seconds: float,
    memory_text: str,
    ocr_lines: Sequence[str],
) -> int:
    observations = _build_observations(
        moment_id=moment_id,
        t_seconds=t_seconds,
        memory_text=memory_text,
        ocr_lines=ocr_lines,
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


def answer_question(question: str, db_path: str | Path) -> EventLogAnswer:
    parsed = _parse_question(question)
    if parsed is None:
        return EventLogAnswer(supported=False, answer="", refused=False, citations=())

    log = SqliteEventLog(str(db_path))
    try:
        observations = log.observations()
    finally:
        log.close()

    object_matches = _matching_objects(parsed.subject, observations)
    if not object_matches:
        return EventLogAnswer(
            supported=True,
            answer=HONEST_REFUSAL,
            refused=True,
            citations=(),
        )

    if parsed.intent == "count":
        bound_entities = bind_entities(object_matches)
        count = sum(entity.count for entity in bound_entities)
        noun = parsed.subject if count != 1 else _singularize_phrase(parsed.subject)
        if bound_entities and all(entity.confidence == "low" for entity in bound_entities):
            pronoun = "it" if count == 1 else "them"
            return EventLogAnswer(
                supported=True,
                answer=f"I saw at least {count} {noun}, but I can't reliably count {pronoun} yet.",
                refused=False,
                citations=object_matches,
            )
        return EventLogAnswer(
            supported=True,
            answer=f"I saw {count} {noun}.",
            refused=False,
            citations=object_matches,
        )

    if parsed.intent == "exists":
        noun = _singularize_phrase(parsed.subject)
        article = "an" if noun[:1] in "aeiou" else "a"
        return EventLogAnswer(
            supported=True,
            answer=f"Yes, I saw {article} {noun}.",
            refused=False,
            citations=object_matches[:1],
        )

    attribute_value = _attribute_answer(parsed.attribute, object_matches, observations)
    if attribute_value is None:
        return EventLogAnswer(
            supported=True,
            answer=HONEST_REFUSAL,
            refused=True,
            citations=(),
        )
    return EventLogAnswer(
        supported=True,
        answer=f"The {_singularize_phrase(parsed.subject)} is {attribute_value}.",
        refused=False,
        citations=object_matches[:1],
    )


@dataclass(frozen=True)
class _ParsedQuestion:
    intent: str
    subject: str
    attribute: str | None = None


def _build_observations(
    *,
    moment_id: str,
    t_seconds: float,
    memory_text: str,
    ocr_lines: Sequence[str],
) -> tuple[Observation, ...]:
    t_ms = max(0, round(float(t_seconds) * 1000))
    observations: list[Observation] = []
    line_index = 0
    for raw_line in memory_text.splitlines():
        observation = _line_observation(raw_line, moment_id=moment_id, t_ms=t_ms, line_index=line_index)
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
                spatial_anchor=None,
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
    detail, spatial_anchor = _detail_and_anchor(parts, has_certainty=certainty is not None)
    return Observation(
        kind=prefix,
        subject=parts[1],
        attributes=(Attribute("detail", detail),) if detail else (),
        t_ms=t_ms,
        spatial_anchor=spatial_anchor,
        confidence=Confidence(_CERTAINTY_CONFIDENCE.get(certainty or "", _DEFAULT_CONFIDENCE)),
        provenance=Provenance(
            event_id=f"{moment_id}:{t_ms}:{prefix}:{line_index}",
            source_channel="vlm",
            captured_at_ms=t_ms,
        ),
    )


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


def _clean_subject(subject: str) -> str:
    cleaned = re.sub(r"\s+", " ", subject.strip().rstrip("?.!"))
    return re.sub(r"^(?:the|a|an|any)\s+", "", cleaned, flags=re.IGNORECASE)


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
