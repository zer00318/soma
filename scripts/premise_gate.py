#!/usr/bin/env python3
"""Deterministic guard for clear numeric premise contradictions."""
from __future__ import annotations

import re


_NUMERIC_ANSWER_RE = re.compile(r"\b\d[\d\s.\-]*\d\b")
_NUMERIC_SPAN_RE = re.compile(r"\b\d+(?:[\s.\-]+\d+)*\b")


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def _numeric_spans(value: str) -> list[str]:
    return [m.group(0).strip() for m in _NUMERIC_SPAN_RE.finditer(value or "")]


def _matches_read_value(presupposed: str, answer: str) -> bool:
    q_digits = _digits(presupposed)
    answer_digits = _digits(answer)
    if not q_digits or not answer_digits:
        return False

    if q_digits == answer_digits or answer_digits.startswith(q_digits):
        return True

    # A year/date component inside a supported range is a true partial premise, not
    # a contradiction. Do not treat arbitrary suffixes as matches: 12 != 112.
    return q_digits in re.findall(r"\d+", answer)


def premise_correction(question: str, consensus_result: dict) -> str | None:
    """Return a correction when a numeric premise contradicts OCR consensus."""
    if not isinstance(consensus_result, dict):
        return None
    if consensus_result.get("refused"):
        return None

    try:
        support = int(consensus_result.get("support") or 0)
    except (TypeError, ValueError):
        return None
    if support < 3:
        return None

    answer = str(consensus_result.get("answer") or "").strip()
    if not answer or not _NUMERIC_ANSWER_RE.search(answer):
        return None

    question_numbers = _numeric_spans(question)
    if len(question_numbers) != 1:
        return None

    presupposed = question_numbers[0]
    if _matches_read_value(presupposed, answer):
        return None

    return f"Not {presupposed} \u2014 I read {answer} ({support} frames agree)."
