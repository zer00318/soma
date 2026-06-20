"""The grounding gate: refuse draft claims the captured corpus cannot support.

This generalizes the legacy "G4 floor". A fluent reasoner will happily narrate
detail it never perceived; the gate is a deterministic, model-free check that an
asserted answer is *anchored* in the raw captured text. It does not judge truth,
only provenance: every distinctive content word in the draft should echo a word
that was actually captured. When too many do not, honest refusal beats confident
fabrication, so the draft is replaced with a refusal instead of being returned.

The check is intentionally crude (stem-prefix overlap, not semantics): a crude
check that is auditable and never hallucinates is worth more here than a clever
one that might.
"""

from __future__ import annotations

import re

REFUSAL_TEXT = "I don't have that in my memory — I didn't perceive it."

# Narration scaffolding and grammar words carry no captured content, so they
# must not count toward (or against) grounding. Kept small and explicit.
_STOPWORDS = frozenset(
    """
    about above after again against because before being below between both
    cannot could does doing done down during each either every from have having
    here into itself just more most much must never only other over same some
    such than that them then there these they this those through under until
    very were what when where which while will with would your yours
    seems seen says said tell told show shown will would maybe perhaps likely
    probably appears looks looked thing things stuff something anything nothing
    """.split()
)

_MIN_TOKEN_LEN = 4
_MIN_DISTINCTIVE = 3
_MAX_UNGROUNDED_FRACTION = 0.5


def _content_tokens(text: str) -> list[str]:
    """Lowercase alpha words >= 4 chars, minus the stopword/narration set."""
    raw = re.findall(r"[a-z]+", text.lower())
    return [tok for tok in raw if len(tok) >= _MIN_TOKEN_LEN and tok not in _STOPWORDS]


def _stem(token: str) -> str:
    return token[: max(_MIN_TOKEN_LEN, len(token) - 2)]


def _corpus_stems(corpus: str) -> set[str]:
    return {_stem(tok) for tok in _content_tokens(corpus)}


def _is_grounded(token: str, corpus_stems: set[str]) -> bool:
    stem = _stem(token)
    return any(stem == cs or stem in cs or cs in stem for cs in corpus_stems)


def ground(draft: str, corpus: str) -> tuple[str, str]:
    """Return ("assert", draft) if anchored in corpus, else ("refuse", REFUSAL_TEXT)."""
    if not draft.strip():
        return ("refuse", REFUSAL_TEXT)

    distinctive = dict.fromkeys(_content_tokens(draft))
    if len(distinctive) < _MIN_DISTINCTIVE:
        return ("assert", draft)

    corpus_stems = _corpus_stems(corpus)
    ungrounded = sum(1 for tok in distinctive if not _is_grounded(tok, corpus_stems))
    if ungrounded / len(distinctive) >= _MAX_UNGROUNDED_FRACTION:
        return ("refuse", REFUSAL_TEXT)
    return ("assert", draft)
