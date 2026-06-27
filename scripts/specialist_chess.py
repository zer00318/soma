#!/usr/bin/env python3
"""Deterministic chess specialist for SAN move-list parsing."""
from __future__ import annotations

import re
from typing import Any

# First-moves -> opening name (prefix match on the SAN move list, longest prefix wins).
OPENINGS = [
    (["e4", "d5"], "Scandinavian Defense"),
    (["e4", "c5"], "Sicilian Defense"),
    (["e4", "e5"], "Open Game / King's Pawn"),
    (["e4", "e6"], "French Defense"),
    (["e4", "c6"], "Caro-Kann Defense"),
    (["d4", "d5"], "Queen's Pawn / Closed"),
    (["d4", "Nf6"], "Indian Defense"),
    (["c4"], "English Opening"),
    (["Nf3"], "Reti Opening"),
    (["e4"], "King's Pawn Opening"),
    (["d4"], "Queen's Pawn Opening"),
]

_MOVE_NUMBER_RE = re.compile(r"\b\d+\.(?:\.\.)?")
_SAN_RE = re.compile(
    r"^(?:"
    r"O-O(?:-O)?"
    r"|"
    r"(?:[KQRBN])?(?:[a-h]|[1-8]){0,2}x?[a-h][1-8](?:=[QRBN])?"
    r")$"
)
_RESULT_MARKERS = {"1-0", "0-1", "1/2-1/2", "*"}


def _as_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _clean_token(token: str) -> str:
    cleaned = token.strip()
    cleaned = cleaned.strip("()[]{}<>,;:")
    cleaned = re.sub(r"[!?+#]+$", "", cleaned)
    if cleaned in {"0-0", "0-0-0"}:
        cleaned = cleaned.replace("0", "O")
    return cleaned


def parse_moves(text: str) -> list[str]:
    """Extract cleaned SAN moves from a move-list string."""
    if not text or not text.strip():
        return []

    scrubbed = _MOVE_NUMBER_RE.sub(" ", text)
    moves: list[str] = []
    for raw_token in scrubbed.split():
        token = _clean_token(raw_token)
        if not token or token in _RESULT_MARKERS:
            continue
        if _SAN_RE.fullmatch(token):
            moves.append(token)
    return moves


def identify_opening(moves: list[str]) -> str:
    """Return the longest matching opening prefix for the SAN move list."""
    if not moves:
        return "Unknown opening"

    best_name = "Unknown opening"
    best_length = 0
    for prefix, name in OPENINGS:
        if len(prefix) > len(moves):
            continue
        if moves[: len(prefix)] == prefix and len(prefix) > best_length:
            best_name = name
            best_length = len(prefix)
    return best_name


def _infer_result(text: str) -> str | None:
    lowered = text.lower()
    if "1/2-1/2" in text or re.search(r"\b(draw|stalemate)\b", lowered):
        return "draw"
    if "0-1" in text or re.search(r"\b(lost|defeat|checkmated)\b", lowered):
        return "loss"
    if "1-0" in text or re.search(r"\b(won|victory)\b", lowered):
        return "win"
    if "checkmate" in lowered:
        return "win"
    return None


def _build_summary(opening: str, move_count: int, result: str | None) -> str:
    if move_count == 0:
        summary = "No chess move list found."
    else:
        summary = f"Detected {move_count} SAN moves. Opening: {opening}."
    if result:
        summary += f" Result: {result}."
    return summary


def extract(perception: dict[str, Any]) -> dict[str, Any]:
    """Extract chess facts from OCR text and caption text."""
    texts = _as_text_list(perception.get("texts"))
    caption = str(perception.get("caption") or "").strip()
    combined = " ".join(texts + ([caption] if caption else []))
    moves = parse_moves(combined)
    opening = identify_opening(moves)
    result = _infer_result(combined)
    move_count = len(moves)
    summary = _build_summary(opening, move_count, result)
    return {
        "moves": moves,
        "opening": opening,
        "move_count": move_count,
        "result": result,
        "summary": summary,
    }


def answer(facts: dict[str, Any], question: str) -> dict[str, Any] | None:
    """Answer lightweight chess questions from extracted facts, or return None."""
    lowered = (question or "").lower().strip()
    if not lowered:
        return None

    if "opening" in lowered:
        opening = facts.get("opening") or "Unknown opening"
        refused = opening == "Unknown opening"
        return {"answer": f"The opening was {opening}.", "refused": refused}

    if "move" in lowered and re.search(r"\b(how many|count|number)\b", lowered):
        move_count = int(facts.get("move_count") or 0)
        return {"answer": f"I parsed {move_count} moves.", "refused": False}

    if re.search(r"\b(result|win|won|lose|lost|draw)\b", lowered):
        result = facts.get("result")
        if result is None:
            return {
                "answer": "I couldn't determine the result from the visible chess text.",
                "refused": True,
            }
        return {"answer": f"The result looks like a {result}.", "refused": False}

    return None
