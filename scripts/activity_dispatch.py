#!/usr/bin/env python3
"""Activity dispatch glue: recognise WHAT the person is doing (activity_identifier)
and run the matching DOMAIN specialists, producing structured domain facts that the
brain can answer from later. This is the layer above the generic helpers.

Specialists are looked up lazily and degrade gracefully if a module isn't present
yet (the society grows over time).
"""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = str(Path(__file__).resolve().parent)
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)


def analyze(perception: dict) -> dict | None:
    """Identify the activity and run its specialists over the moment's perception.

    perception = {"objects":[str], "texts":[str], "caption": str}
    Returns {"activity", "confidence", "specialists", "domain_facts": {name: facts}} or None.
    """
    try:
        import activity_identifier as ai
    except Exception:
        return None
    try:
        ident = ai.identify(perception)
    except Exception:
        return None

    facts: dict[str, dict] = {}
    for spec in ident.get("specialists", []) or []:
        runner = _SPECIALISTS.get(spec)
        if runner is None:
            continue
        try:
            out = runner(perception)
            if out:
                facts[spec] = out
        except Exception:
            continue
    return {
        "activity": ident.get("activity"),
        "confidence": ident.get("confidence"),
        "specialists": ident.get("specialists", []),
        "domain_facts": facts,
    }


def answer_domain(question: str, domain_facts: dict | None) -> dict | None:
    """Route a question to the specialist that can answer it from stored domain facts."""
    if not domain_facts:
        return None
    for spec, facts in domain_facts.items():
        answerer = _ANSWERERS.get(spec)
        if answerer is None:
            continue
        try:
            out = answerer(facts, question)
            if out:
                out.setdefault("source", f"specialist_{spec}")
                return out
        except Exception:
            continue
    return None


def _cooking_extract(perception):
    import specialist_cooking as sc
    return sc.extract(perception)


def _cooking_answer(facts, question):
    import specialist_cooking as sc
    return sc.answer(facts, question)


def _chess_extract(perception):
    import specialist_chess as scz
    return scz.extract(perception)


def _chess_answer(facts, question):
    import specialist_chess as scz
    return scz.answer(facts, question)


def _reading_extract(perception):
    import specialist_reading as sr
    return sr.extract(perception)


def _reading_answer(facts, question):
    import specialist_reading as sr
    return sr.answer(facts, question)


# Registries — extend as specialists are added (code, shopping...).
# Each runner is lazy-imported, so a not-yet-built specialist just no-ops.
# Keys match the specialist names activity_identifier emits.
_SPECIALISTS = {"cooking": _cooking_extract, "chess": _chess_extract,
                "document": _reading_extract}
_ANSWERERS = {"cooking": _cooking_answer, "chess": _chess_answer,
              "document": _reading_answer}
