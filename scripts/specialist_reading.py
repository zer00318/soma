#!/usr/bin/env python3
"""Deterministic reading/document specialist for OCR-derived facts."""
from __future__ import annotations

import re
from typing import Any

_NUMBER_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s?(?:mg|g|kg|ml|l|%|mph|km|usd|eur)\b|\b\d+(?:\.\d+)?\s?(?:\$|€)",
    re.IGNORECASE,
)
_ENTITY_RE = re.compile(
    r"\b(?:[A-Z][a-z]+|[A-Z]{2,}|[A-Z])"
    r"(?:\s+(?:of|the|and|for|in|on|at|de|van|von))?"
    r"(?:\s+(?:[A-Z][a-z]+|[A-Z]{2,}|[A-Z]))+\b"
)
_ABOUT_RE = re.compile(
    r"\b("
    r"what was (?:it|the article|the paper|the study|the book|the document) about"
    r"|what did i read"
    r"|what was i reading"
    r"|what was that article about"
    r"|what was that paper about"
    r"|gist"
    r"|summary"
    r")\b"
)
_NUMBER_QUERY_RE = re.compile(r"\b(dose|dosage|number|amount|how much)\b")
_ENTITY_QUERY_RE = re.compile(
    r"\b(who was mentioned|what was mentioned|who did it mention|what did it mention|which names|which people|entities)\b"
)
_READING_CONTEXT_RE = re.compile(
    r"\b(read|reading|article|paper|study|document|book|text|page|report|mention|mentioned|say|said)\b"
)
_SENTENCE_PUNCTUATION = ".?!"
_LOWER_TITLE_WORDS = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "of", "on", "or", "the", "to", "with"}


def _as_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _clean_line(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip(" -\t\r\n")


def _candidate_lines(perception: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for value in _as_text_list(perception.get("texts")):
        lines.extend(_clean_line(part) for part in value.splitlines())

    caption = str(perception.get("caption") or "").strip()
    if caption:
        lines.extend(_clean_line(part) for part in caption.splitlines())

    return [line for line in lines if line]


def _word_tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z]+", text)


def _is_title_case(text: str) -> bool:
    words = _word_tokens(text)
    if len(words) < 2:
        return False

    titleish = 0
    for word in words:
        if word.lower() in _LOWER_TITLE_WORDS:
            titleish += 1
        elif word[:1].isupper():
            titleish += 1
    return titleish >= max(2, len(words) - 1)


def _is_all_caps(text: str) -> bool:
    letters = [char for char in text if char.isalpha()]
    return bool(letters) and all(char.isupper() for char in letters)


def _looks_like_sentence(text: str) -> bool:
    words = _word_tokens(text)
    if not words:
        return False
    if text.endswith(_SENTENCE_PUNCTUATION):
        return True
    lowered = text.lower()
    return len(words) > 12 or " the " in f" {lowered} " or " used " in f" {lowered} "


def _title_score(text: str) -> tuple[int, int]:
    score = 0
    word_count = len(_word_tokens(text))
    if 2 <= word_count <= 12:
        score += 2
    if _is_title_case(text):
        score += 4
    if _is_all_caps(text):
        score += 3
    if not _looks_like_sentence(text):
        score += 3
    if len(text) > 8:
        score += 1
    return (score, len(text))


def _pick_title(lines: list[str]) -> str | None:
    non_trivial = [line for line in lines if len(line) >= 4]
    if not non_trivial:
        return None

    title_like = [line for line in non_trivial if _title_score(line)[0] >= 6]
    if title_like:
        return max(title_like, key=_title_score)
    return non_trivial[0]


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def _collect_numbers(text: str) -> list[str]:
    return _dedupe_keep_order(match.group(0).strip() for match in _NUMBER_RE.finditer(text))


def _normalize_entity(entity: str) -> str:
    return re.sub(r"\s+", " ", entity).strip(" ,.;:-")


def _collect_entities(text: str) -> list[str]:
    entities: list[str] = []
    for chunk in text.splitlines():
        for match in _ENTITY_RE.finditer(chunk):
            entity = _normalize_entity(match.group(0))
            if len(entity.split()) > 8:
                continue
            entities.append(entity)
    return _dedupe_keep_order(entities)[:8]


def _gist_from_lines(lines: list[str], title: str | None) -> str:
    body_lines = lines[:]
    if title:
        removed = False
        filtered: list[str] = []
        for line in lines:
            if not removed and line == title:
                removed = True
                continue
            filtered.append(line)
        if filtered:
            body_lines = filtered

    gist = " ".join(body_lines).strip()
    if len(gist) > 200:
        gist = gist[:200].rstrip()
    return gist


def _build_summary(title: str | None, gist: str, numbers: list[str], entities: list[str]) -> str:
    parts: list[str] = []
    if title:
        parts.append(f"Title: {title}.")
    if gist:
        parts.append(f"Gist: {gist}")
    if numbers:
        parts.append(f"Numbers: {', '.join(numbers)}.")
    if entities:
        parts.append(f"Entities: {', '.join(entities)}.")
    if not parts:
        return "No readable document details found."
    return " ".join(parts)


def extract(perception: dict[str, Any]) -> dict[str, Any]:
    """Extract document facts from OCR text and caption text."""
    lines = _candidate_lines(perception)
    title = _pick_title(lines)
    combined = " ".join(lines)
    numbers = _collect_numbers(combined)
    entities = _collect_entities("\n".join(lines))
    gist = _gist_from_lines(lines, title)
    summary = _build_summary(title, gist, numbers, entities)
    return {
        "title": title,
        "numbers": numbers,
        "entities": entities,
        "gist": gist,
        "summary": summary,
    }


def answer(facts: dict[str, Any], question: str) -> dict[str, Any] | None:
    """Answer lightweight reading questions from extracted facts, or return None."""
    lowered = (question or "").lower().strip()
    if not lowered:
        return None

    if _ABOUT_RE.search(lowered):
        title = facts.get("title")
        gist = str(facts.get("gist") or "").strip()
        if not title and not gist:
            return {
                "answer": "I couldn't tell what the reading was about from the captured text.",
                "refused": True,
            }

        if title and gist:
            return {"answer": f"It was about {title}. {gist}", "refused": False}
        if title:
            return {"answer": f"It was about {title}.", "refused": False}
        return {"answer": gist, "refused": False}

    if _ENTITY_QUERY_RE.search(lowered):
        entities = [str(item) for item in facts.get("entities") or [] if str(item).strip()]
        if not entities:
            return {"answer": "I didn't capture any named people or entities from that reading.", "refused": True}
        return {"answer": f"It mentioned {', '.join(entities)}.", "refused": False}

    if _NUMBER_QUERY_RE.search(lowered):
        has_reading_context = bool(_READING_CONTEXT_RE.search(lowered))
        explicit_number_query = "what number" in lowered or "dose" in lowered or "dosage" in lowered or "amount" in lowered
        if not (explicit_number_query or has_reading_context):
            return None

        numbers = [str(item) for item in facts.get("numbers") or [] if str(item).strip()]
        if not numbers:
            return {"answer": "I didn't capture any numeric dose or quantity from that reading.", "refused": True}
        return {"answer": f"It mentioned {', '.join(numbers)}.", "refused": False}

    return None
