#!/usr/bin/env python3
"""Deterministic cooking specialist for ingredient and amount extraction."""
from __future__ import annotations

import re
from typing import Any

INGREDIENT_WORDS = {
    "soya",
    "soy",
    "flour",
    "rice",
    "sugar",
    "salt",
    "oil",
    "lentil",
    "dal",
    "bean",
    "spice",
    "pepper",
    "onion",
    "garlic",
    "tomato",
    "pasta",
    "nutella",
    "pesto",
    "water",
    "milk",
    "egg",
}
UTENSIL_WORDS = {
    "bowl",
    "cup",
    "spoon",
    "tablespoon",
    "teaspoon",
    "pan",
    "pot",
    "jar",
    "glass",
    "scoop",
    "plate",
    "container",
    "measuring cup",
}
UTENSIL_VOLUME_ML = {
    "teaspoon": 5,
    "tablespoon": 15,
    "cup": 240,
    "glass": 250,
    "bowl": 500,
    "scoop": 60,
    "spoon": 15,
    "jar": 400,
    "pot": 2000,
    "pan": 1500,
}

ACTION_WORDS = {
    "add",
    "bake",
    "boil",
    "chop",
    "cook",
    "fry",
    "knead",
    "mix",
    "pour",
    "saute",
    "simmer",
    "stir",
    "whisk",
}

_EXPLICIT_AMOUNT_RE = re.compile(r"\b\d+(?:\.\d+)?\s?(?:g|kg|ml|l)\b", re.IGNORECASE)
_INGREDIENT_ALIASES = {"soy": "soya"}


def _as_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _canonical_ingredient(name: str) -> str:
    lowered = name.lower().strip()
    return _INGREDIENT_ALIASES.get(lowered, lowered)


def _phrase_pattern(phrase: str) -> str:
    if " " not in phrase:
        return rf"\b{re.escape(phrase)}s?\b"
    head, tail = phrase.rsplit(" ", 1)
    return rf"\b{re.escape(head)}\s+{re.escape(tail)}s?\b"


def _scan_phrases(text: str, phrases: set[str]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    lowered = text.lower()
    for phrase in sorted(phrases, key=len, reverse=True):
        for match in re.finditer(_phrase_pattern(phrase), lowered):
            matches.append(
                {
                    "value": phrase,
                    "start": match.start(),
                    "end": match.end(),
                    "raw": text[match.start() : match.end()],
                }
            )
    matches.sort(key=lambda item: (item["start"], item["end"]))
    return matches


def _segments(perception: dict[str, Any]) -> list[dict[str, Any]]:
    raw_segments: list[tuple[str, int, str]] = []
    for idx, value in enumerate(_as_text_list(perception.get("objects"))):
        raw_segments.append(("object", idx, value))
    for idx, value in enumerate(_as_text_list(perception.get("texts"))):
        raw_segments.append(("text", idx, value))
    caption = str(perception.get("caption") or "").strip()
    if caption:
        raw_segments.append(("caption", 0, caption))

    segments: list[dict[str, Any]] = []
    cursor = 0
    for kind, idx, text in raw_segments:
        segments.append(
            {
                "kind": kind,
                "index": idx,
                "text": text,
                "base": cursor,
            }
        )
        cursor += len(text) + 3
    return segments


def _fill_phrase(fill_fraction: float, utensil: str) -> str:
    if abs(fill_fraction - 0.25) < 0.01:
        return f"~quarter of a {utensil}"
    if abs(fill_fraction - 0.5) < 0.01:
        return f"~half a {utensil}"
    if abs(fill_fraction - 0.75) < 0.01:
        return f"~three-quarters of a {utensil}"
    if abs(fill_fraction - 1.0) < 0.01:
        return f"~a full {utensil}"
    percent = round(fill_fraction * 100)
    return f"~{percent}% of a {utensil}"


def _explicit_amount_to_ml(raw_amount: str) -> int | None:
    match = re.match(r"(?P<number>\d+(?:\.\d+)?)\s?(?P<unit>g|kg|ml|l)$", raw_amount.strip(), re.I)
    if not match:
        return None
    number = float(match.group("number"))
    unit = match.group("unit").lower()
    if unit == "ml":
        return round(number)
    if unit == "l":
        return round(number * 1000)
    return None


def _find_explicit_amounts(text: str) -> list[dict[str, Any]]:
    return [
        {
            "raw": match.group(0).strip(),
            "start": match.start(),
            "end": match.end(),
        }
        for match in _EXPLICIT_AMOUNT_RE.finditer(text)
    ]


def _closest_mention(
    anchor_position: int,
    candidates: list[dict[str, Any]],
    *,
    allowed_kinds: set[str] | None = None,
    same_segment_only: bool = False,
    segment_kind: str | None = None,
    segment_index: int | None = None,
) -> dict[str, Any] | None:
    filtered: list[dict[str, Any]] = []
    for candidate in candidates:
        if allowed_kinds is not None and candidate["kind"] not in allowed_kinds:
            continue
        if same_segment_only:
            if candidate["kind"] != segment_kind or candidate["segment_index"] != segment_index:
                continue
        filtered.append(candidate)
    if not filtered:
        return None
    return min(
        filtered,
        key=lambda candidate: (abs(candidate["position"] - anchor_position), candidate["position"]),
    )


def extract(perception: dict[str, Any], fill_fraction: float = 0.5) -> dict[str, Any]:
    """Extract structured cooking facts from a frame/moment's perception."""
    segments = _segments(perception)
    ingredient_mentions: list[dict[str, Any]] = []
    utensil_mentions: list[dict[str, Any]] = []
    explicit_amount_mentions: list[dict[str, Any]] = []
    actions: list[str] = []

    for segment in segments:
        text = segment["text"]
        for match in _scan_phrases(text, INGREDIENT_WORDS):
            ingredient_mentions.append(
                {
                    "name": _canonical_ingredient(match["value"]),
                    "kind": segment["kind"],
                    "segment_index": segment["index"],
                    "position": segment["base"] + match["start"],
                }
            )
        for match in _scan_phrases(text, UTENSIL_WORDS):
            utensil_mentions.append(
                {
                    "name": match["value"],
                    "kind": segment["kind"],
                    "segment_index": segment["index"],
                    "position": segment["base"] + match["start"],
                }
            )
        for match in _find_explicit_amounts(text):
            if segment["kind"] != "text":
                continue
            explicit_amount_mentions.append(
                {
                    "raw": match["raw"],
                    "kind": segment["kind"],
                    "segment_index": segment["index"],
                    "position": segment["base"] + match["start"],
                }
            )
        for action in sorted(ACTION_WORDS):
            if re.search(_phrase_pattern(action), text.lower()) and action not in actions:
                actions.append(action)

    utensils = list(dict.fromkeys(mention["name"] for mention in utensil_mentions))
    ingredients: list[dict[str, Any]] = []
    seen_ingredients: set[str] = set()
    unique_ingredient_count = len({mention["name"] for mention in ingredient_mentions})

    for mention in ingredient_mentions:
        ingredient_name = mention["name"]
        if ingredient_name in seen_ingredients:
            continue
        seen_ingredients.add(ingredient_name)

        explicit_amount = _closest_mention(
            mention["position"],
            explicit_amount_mentions,
            same_segment_only=True,
            segment_kind=mention["kind"],
            segment_index=mention["segment_index"],
        )
        if explicit_amount is None and unique_ingredient_count == 1:
            explicit_amount = _closest_mention(
                mention["position"],
                explicit_amount_mentions,
                allowed_kinds={"text"},
            )

        utensil = _closest_mention(mention["position"], utensil_mentions)
        utensil_name = utensil["name"] if utensil is not None else None

        amount_ml: int | None = None
        if explicit_amount is not None:
            raw_amount = explicit_amount["raw"]
            amount_ml = _explicit_amount_to_ml(raw_amount)
            amount_hedge = (
                f"text showed {raw_amount}; using the label rather than a visual estimate."
            )
        elif utensil_name in UTENSIL_VOLUME_ML:
            amount_ml = round(UTENSIL_VOLUME_ML[utensil_name] * fill_fraction)
            amount_hedge = (
                f"{_fill_phrase(fill_fraction, utensil_name)} (≈{amount_ml} ml), "
                "rough visual estimate, no scale."
            )
        else:
            amount_hedge = "amount not measurable from what I saw."

        ingredients.append(
            {
                "name": ingredient_name,
                "in": utensil_name,
                "amount_ml": amount_ml,
                "amount_hedge": amount_hedge,
            }
        )

    if ingredients:
        ingredient_bits = []
        for ingredient in ingredients:
            if ingredient["in"]:
                ingredient_bits.append(f"{ingredient['name']} in {ingredient['in']}")
            else:
                ingredient_bits.append(ingredient["name"])
        summary = f"Saw {', '.join(ingredient_bits)}."
    else:
        summary = "No cooking ingredients identified."

    if actions:
        summary += f" Possible action: {', '.join(actions)}."

    return {
        "ingredients": ingredients,
        "utensils": utensils,
        "actions": actions,
        "summary": summary,
    }


def _question_ingredient(question: str) -> str | None:
    matches = _scan_phrases(question, INGREDIENT_WORDS)
    if not matches:
        return None
    return _canonical_ingredient(matches[0]["value"])


def answer(cooking_facts: dict[str, Any], question: str) -> dict[str, Any] | None:
    """Answer a cooking question from extracted facts, or return None."""
    lowered = (question or "").lower()
    if not lowered.strip():
        return None

    if "how much" in lowered:
        ingredient_name = _question_ingredient(lowered)
        if ingredient_name is None:
            return None
        for ingredient in cooking_facts.get("ingredients", []):
            if ingredient.get("name") == ingredient_name:
                answer_text = f"For {ingredient_name}, {ingredient['amount_hedge']}"
                refused = "not measurable" in ingredient["amount_hedge"].lower()
                return {"answer": answer_text, "refused": refused}
        return {"answer": f"I didn't see {ingredient_name}.", "refused": True}

    if re.search(r"\bwhat\b", lowered) and re.search(
        r"\b(cook|use|used|ingredient|ingredients)\b", lowered
    ):
        ingredient_names = [item.get("name") for item in cooking_facts.get("ingredients", []) if item.get("name")]
        if not ingredient_names:
            return {"answer": "I didn't identify any cooking ingredients.", "refused": True}
        unique_names = list(dict.fromkeys(ingredient_names))
        return {
            "answer": f"I saw these ingredients: {', '.join(unique_names)}.",
            "refused": False,
        }

    return None
