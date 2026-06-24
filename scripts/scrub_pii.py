#!/usr/bin/env python3
"""Small deterministic PII scrubber for local text observations."""

from __future__ import annotations

import re
from collections.abc import Iterable


_EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9.!#$%&'*+/=?^_`{|}~-])"
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+"
    r"(?![A-Za-z0-9-])"
)
_IBAN_RE = re.compile(
    r"(?<![A-Za-z0-9])[A-Z]{2}\d{2}(?: ?[A-Z0-9]){11,30}(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_INTERNATIONAL_PHONE_RE = re.compile(r"(?<![\w])\+\d[\d .()-]{5,}\d(?![\w])")
_GROUPED_PHONE_RE = re.compile(
    r"(?<![\w+])"
    r"(?:\(\d{2,5}\)|\d{2,5})"
    r"(?:[ \t.-]+(?:\(\d{2,5}\)|\d{2,8})){1,3}"
    r"(?![\w])"
)
_LONG_DIGIT_RE = re.compile(r"(?<![A-Za-z0-9])\d{9,}(?![A-Za-z0-9])")
_CREDIT_CARD_RE = re.compile(r"(?<![A-Za-z0-9])\d(?:[ -]?\d){12,15}(?![A-Za-z0-9])")

_SCRUBBED_KEYS = frozenset({"ocr", "caption", "text"})


def _digit_groups(value: str) -> list[str]:
    return re.findall(r"\d+", value)


def _digit_count(value: str) -> int:
    return sum(len(group) for group in _digit_groups(value))


def _valid_iban(value: str) -> bool:
    compact = value.replace(" ", "")
    return 15 <= len(compact) <= 34 and compact[:2].isalpha() and compact[2:4].isdigit()


def _valid_international_phone(value: str) -> bool:
    digits = _digit_count(value)
    return 7 <= digits <= 16


def _valid_grouped_phone(value: str) -> bool:
    groups = _digit_groups(value)
    if not (2 <= len(groups) <= 4):
        return False
    if not (7 <= sum(len(group) for group in groups) <= 16):
        return False

    stripped = value.strip()
    # A hyphen-separated pair that begins with a 4-digit year is a date / plaque
    # range (1898-1970, 1845 - 1923, or a truncated OCR read 1845 - 192) — never a
    # phone number. Protect these: a redacted plaque date silently breaks the product.
    if len(groups) == 2 and re.fullmatch(r"\d{3,4}\s*-\s*\d{2,4}", stripped):
        first = groups[0]
        if len(first) == 4 and 1000 <= int(first) <= 2099:
            return False
    if all(len(group) == 4 for group in groups):
        return False
    return True


def _collect_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []

    for regex in (_EMAIL_RE, _LONG_DIGIT_RE, _CREDIT_CARD_RE):
        spans.extend(match.span() for match in regex.finditer(text))

    spans.extend(match.span() for match in _IBAN_RE.finditer(text) if _valid_iban(match.group(0)))
    spans.extend(
        match.span()
        for match in _INTERNATIONAL_PHONE_RE.finditer(text)
        if _valid_international_phone(match.group(0))
    )
    spans.extend(
        match.span()
        for match in _GROUPED_PHONE_RE.finditer(text)
        if _valid_grouped_phone(match.group(0))
    )

    return _merge_spans(spans)


def _merge_spans(spans: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    ordered = sorted(spans)
    if not ordered:
        return []

    merged = [ordered[0]]
    for start, end in ordered[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def scrub_pii(text: str, *, mask: str = "[redacted]") -> str:
    """Redact obvious personal data from a string, on-device, deterministically.
    Returns text with PII spans replaced by `mask`. Conservative: only redact
    high-confidence PII patterns, never normal words."""

    spans = _collect_spans(text)
    if not spans:
        return text

    out: list[str] = []
    last = 0
    for start, end in spans:
        out.append(text[last:start])
        out.append(mask)
        last = end
    out.append(text[last:])
    return "".join(out)


def _scrub_value(value):
    if isinstance(value, str):
        return scrub_pii(value)
    if isinstance(value, list):
        return [scrub_pii(item) if isinstance(item, str) else item for item in value]
    return value


def scrub_record(rec: dict) -> dict:
    """Return a shallow copy of an Observation/keyframe-style record with any
    'ocr'/'caption'/'text' string fields scrubbed via scrub_pii."""

    scrubbed = dict(rec)
    for key in _SCRUBBED_KEYS & scrubbed.keys():
        scrubbed[key] = _scrub_value(scrubbed[key])
    return scrubbed
