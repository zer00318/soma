#!/usr/bin/env python3
"""Cue-based activity classifier for routing domain specialists."""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

ACTIVITIES = {
    "chess": {
        "cues": [
            "chess",
            "lichess",
            "chess.com",
            "chessboard",
            "pawn",
            "knight",
            "bishop",
            "checkmate",
            "opening",
        ],
        "specialists": ["chess"],
    },
    "cooking": {
        "cues": [
            "bowl",
            "pan",
            "pot",
            "knife",
            "cutting board",
            "ingredient",
            "flour",
            "soya",
            "soy",
            "spice",
            "recipe",
            "stove",
            "measuring",
            "utensil",
            "jar",
            "oil",
        ],
        "specialists": ["cooking"],
    },
    "reading": {
        "cues": ["book", "page", "paragraph", "document", "article", "pdf", "chapter"],
        "specialists": ["document"],
    },
    "coding": {
        "cues": [
            "code",
            "terminal",
            "editor",
            "vscode",
            "function",
            "import",
            "def ",
            "repository",
            "github",
        ],
        "specialists": ["code"],
    },
    "shopping": {
        "cues": ["price", "cart", "checkout", "store", "aisle", "€", "$", "product", "shelf"],
        "specialists": ["shopping"],
    },
}


def _normalize_spaces(text: str) -> str:
    return " ".join(text.casefold().split())


def _compile_cue(cue: str) -> re.Pattern[str]:
    normalized = _normalize_spaces(cue)
    parts = [re.escape(part) for part in normalized.split(" ")]
    body = r"(?:\W|_)+".join(parts)
    prefix = r"(?<!\w)" if normalized[:1].isalnum() or normalized[:1] == "_" else ""
    suffix = r"(?!\w)" if normalized[-1:].isalnum() or normalized[-1:] == "_" else ""
    return re.compile(f"{prefix}{body}{suffix}", re.IGNORECASE)


_COMPILED_CUES = {
    activity: [(cue, _compile_cue(cue)) for cue in config["cues"]]
    for activity, config in ACTIVITIES.items()
}


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return [item for item in value if isinstance(item, str)]
    return []


def _perception_texts(perception: Mapping[str, object]) -> list[str]:
    texts = []
    texts.extend(_string_list(perception.get("objects")))
    texts.extend(_string_list(perception.get("texts")))
    texts.extend(_string_list(perception.get("caption")))
    return [_normalize_spaces(text) for text in texts if isinstance(text, str) and text.strip()]


def identify(perception: Mapping[str, object] | None, min_score: int = 1) -> dict[str, object]:
    """Recognize a likely activity from detector labels, OCR text, and a caption."""
    haystacks = _perception_texts(perception or {})
    hits_by_activity: dict[str, list[str]] = {}
    ranked: list[tuple[str, int]] = []

    for activity, cues in _COMPILED_CUES.items():
        hits = [
            cue
            for cue, pattern in cues
            if any(pattern.search(text) for text in haystacks)
        ]
        if hits:
            hits_by_activity[activity] = hits
            ranked.append((activity, len(hits)))

    ranked.sort(key=lambda item: item[1], reverse=True)
    top_activity = ranked[0][0] if ranked else None
    top_score = ranked[0][1] if ranked else 0
    runner_up = ranked[1][1] if len(ranked) > 1 else 0
    confidence = top_score / (top_score + runner_up + 1) if top_score else 0.0

    if top_activity is None or top_score < min_score:
        activity = "generic"
        specialists: list[str] = []
    else:
        activity = top_activity
        specialists = specialists_for(top_activity)

    return {
        "activity": activity,
        "confidence": confidence,
        "ranked": ranked,
        "specialists": specialists,
        "cues_hit": hits_by_activity.get(top_activity, []) if top_activity else [],
    }


def specialists_for(activity: str) -> list[str]:
    return list(ACTIVITIES.get(activity, {}).get("specialists", []))
