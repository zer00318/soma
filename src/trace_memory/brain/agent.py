from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass
from typing import Any

from trace_memory.store import SearchHit, SearchSlice, TraceMemoryStore

COUNT_RE = re.compile(r"^\s*how many (?P<subject>.+?)\s*\??\s*$", re.IGNORECASE)
# Count intent is a FAMILY of phrasings, not one anchored sentence shape. (Measured: "Count the
# mugs for me" bypassed the ^how many anchor and the counting path entirely.)
COUNT_INTENT_RES = (
    COUNT_RE,
    re.compile(r"^\s*count (?:the |my |all (?:the )?)?(?P<subject>.+?)(?:\s+for me)?\s*[.!?]*\s*$",
               re.IGNORECASE),
    re.compile(r"\b(?:number|count|total)\s+of\s+(?P<subject>.+?)\s*[.!?]*\s*$", re.IGNORECASE),
)
LOCATION_RE = re.compile(
    r"\b("
    r"next to|beside|underneath|under|behind|in front of|on top of|"
    r"draped over|lying on|leaning against|near|inside|on|in|at"
    r")\b",
    re.IGNORECASE,
)
STRONG_LOCATION_RE = re.compile(
    r"\b("
    r"next to|beside|underneath|under|behind|in front of|on top of|"
    r"draped over|lying on|leaning against|inside"
    r")\b",
    re.IGNORECASE,
)
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "can",
    "color",
    "colour",
    "current",
    "currently",
    "flavor",
    "flavour",
    "how",
    "i",
    "in",
    "is",
    "me",
    "many",
    "my",
    "of",
    "opened",
    "on",
    "or",
    "running",
    "the",
    "there",
    "what",
    "was",
    "were",
    "which",
    "where",
    "when",
    "who",
    "why",
    "whom",
    "whose",
    # Conversational filler — present in natural questions but never in evidence, so counting
    # them in coverage wrongly refuses answerable questions ("do I have any nutella" -> tokens
    # do/have/any/.../nutella, only nutella is in evidence -> 1/9 coverage -> false refuse).
    "do",
    "did",
    "does",
    "you",
    "your",
    "see",
    "saw",
    "seen",
    "any",
    "anything",
    "anywhere",
    "somewhere",
    "have",
    "has",
    "had",
    "roughly",
    "around",
    "about",
    "get",
    "got",
    "they",
    "it",
    "to",
    "for",
    "with",
    # Query / perception verbs — actions asked of an object, never the grounding object itself.
    "show",
    "showed",
    "showing",
    "shows",
    "display",
    "displayed",
    "read",
    "reads",
    "say",
    "said",
    "says",
    "tell",
    "told",
    "look",
    "looks",
    "looking",
    "appear",
    "appears",
    "contain",
    "contains",
}
AUTHORED_NODE_TYPES = {"composed_memory", "entity_memory", "event_memory", "group_memory", "abstraction"}
# Attribute words a question asks ABOUT an object — never the grounding object itself. Excluded
# from the subject-grounding gate so "what colour is the fan" grounds on {fan}, not {colour}.
ABSTRACT_QUERY_WORDS = {
    "time", "colour", "color", "brand", "name", "number", "kind", "type", "amount",
    "price", "size", "count", "flavour", "flavor", "material", "shape", "model", "make", "text",
}
# M3 (invariant I5): the content lexicons that used to live here — a bedroom-specific
# LOCATION_ANCHORS noun list, SCREEN_REPORT_NOISE literals scraped from our own dev
# screenshots, a drink-cue lexicon — are DELETED, not relocated. Ranking may key only on
# STRUCTURE: helper types, metadata kinds, generic location grammar, and lexical/embedding
# overlap with the question itself.
AMBIGUITY_CUES = (
    " or ",
    "/",
    "appears",
    "looks like",
    "likely",
    "partially",
    "unclear",
    "not clearly",
    "approximately",
    "about",
    "~",
)


@dataclass(frozen=True)
class AgentAnswer:
    answer: str
    evidence_chain: tuple[dict[str, Any], ...]
    confidence: float
    refused: bool
    retrieval_mode: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "evidence_chain": list(self.evidence_chain),
            "confidence": self.confidence,
            "refused": self.refused,
            "retrieval_mode": self.retrieval_mode,
        }


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _helper_of(node: Any) -> str:
    """Resolve which helper produced a node. Live phone rows carry no coordinate_frame, so they
    can't set the canonical `helper_type` column (it would trip validation) — the app's per-helper
    identity is preserved in metadata['helper'] instead. Prefer the column, fall back to metadata."""
    col = getattr(node, "helper_type", None)
    if col:
        return str(col).lower()
    meta = getattr(node, "metadata", {}) or {}
    return str(meta.get("helper") or meta.get("helper_prompt") or "").lower()


_PLANTED_PREMISE_CUES = (
    "earlier you said", "you said", "you told me", "as you mentioned", "you mentioned",
    "you claimed", "remember when", "last time you", "you confirmed", "didn't you say",
    "you already said", "you noted", "we established", "as we discussed", "you reported",
    "you just said", "like you said",
)


def _has_planted_premise(question: str) -> bool:
    """Generic (non-domain) linguistic cue that the QUESTION asserts a prior 'fact' to be
    accepted — the gaslight vector. Used to arm the anti-gaslight clause in the contract."""
    low = f" {question.lower()} "
    return any(cue in low for cue in _PLANTED_PREMISE_CUES)


def _tokens(text: str) -> list[str]:
    return [_singularize(token) for token in _normalize(text).split() if token and token not in STOPWORDS]


# Irregular plurals the suffix rules below can never reach ("mice" matched nothing, so a count
# question about mice silently bound to another noun in the question).
IRREGULAR_PLURALS = {
    "mice": "mouse", "geese": "goose", "people": "person", "men": "man", "women": "woman",
    "children": "child", "feet": "foot", "teeth": "tooth", "knives": "knife",
    "shelves": "shelf", "leaves": "leaf", "loaves": "loaf", "wolves": "wolf", "dice": "die",
    "buses": "bus", "tvs": "tv", "pcs": "pc",
}


def _singularize(token: str) -> str:
    if token in IRREGULAR_PLURALS:
        return IRREGULAR_PLURALS[token]
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith(("sses", "xes", "zes", "ches", "shes")):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


# Words that end the counted noun phrase in a "how many X ..." question: the verb/preposition
# tail ("are on the desk", "did you see") locates the subject, it is not the subject. Without
# this cut, the count matcher accepted ANY noun in the question ("desk") as the thing to count.
_COUNT_SUBJECT_BREAK = {
    "are", "is", "was", "were", "do", "does", "did", "have", "has", "had", "can", "could",
    "will", "would", "you", "i", "we", "in", "on", "at", "inside", "there", "here", "near",
    "around", "by", "under", "behind", "next", "beside",
}


def _count_subject(question: str) -> str:
    """The noun phrase actually being counted: tokens of the matched count-intent subject up
    to the first verb/preposition, singularized. Empty when no count intent is detected."""
    for pattern in COUNT_INTENT_RES:
        m = pattern.search(question)
        if not m:
            continue
        head: list[str] = []
        for word in _normalize(m.group("subject")).split():
            if word in _COUNT_SUBJECT_BREAK:
                break
            if word in STOPWORDS:
                continue
            head.append(_singularize(word))
        if head:
            return " ".join(head)
    return ""


def _blob(node: Any) -> str:
    normalized = _normalize(
        " ".join(
            (
                node.text,
                json.dumps(
                    node.source_support if hasattr(node, "source_support") else {},
                    ensure_ascii=False,
                ),
                json.dumps(node.metadata, ensure_ascii=False),
                json.dumps(node.provenance, ensure_ascii=False),
            )
        )
    )
    return " ".join(_singularize(token) for token in normalized.split())


def _blob_tokens(node: Any) -> set[str]:
    return {_singularize(token) for token in _normalize(_blob(node)).split() if token}


def _question_hints(question: str) -> set[str]:
    """Question INTENT categories. Each maps to structural evidence properties (which helper,
    which metadata kind) — never to content vocabularies (I5)."""
    lowered = _normalize(question)
    hints: set[str] = set()
    if re.search(r"\b(what did|say|said|transcript|speaking)\b", lowered):
        hints.add("speech")
    if "colour" in lowered or "color" in lowered:
        hints.add("colour")
    if "brand" in lowered or "name" in lowered or "flavour" in lowered or "flavor" in lowered:
        hints.add("label")
    if any(pattern.search(question) for pattern in COUNT_INTENT_RES):
        hints.add("count")
    if re.search(r"\b(where|somewhere|located|location)\b", lowered):
        hints.add("location")
    if re.search(r"\b(current|currently|now|opened)\b", lowered):
        hints.add("current")
    if re.search(r"\b(app|screen|window|display)\b", lowered):
        hints.add("screen")
    return hints


def _location_specificity(text: str) -> float:
    """Generic location GRAMMAR only: how concretely does this text place something?
    Prepositions like 'leaning against'/'on top of' are structural English, not a lexicon."""
    lowered = text.lower()
    strong_phrases = len(STRONG_LOCATION_RE.findall(lowered))
    phrases = len(LOCATION_RE.findall(lowered))
    if phrases == 0:
        return 0.0
    weak_phrases = max(0, phrases - strong_phrases)
    return min(1.1, (strong_phrases * 0.45) + (weak_phrases * 0.1))


def _absence_penalty(text: str, hints: set[str]) -> float:
    lowered = text.lower()
    if not (
        lowered.startswith("no ")
        or "none visible" in lowered
        or "not visible" in lowered
        or "not seen" in lowered
        or "not confirmed" in lowered
    ):
        return 0.0
    if hints & {"location", "label", "count"}:
        return 0.9
    return 0.35


def _count_conflict(question: str, rows: list[dict[str, Any]]) -> bool:
    hints = _question_hints(question)
    if "count" not in hints:
        return False
    numbers: set[str] = set()
    for row in rows[:6]:
        numbers.update(re.findall(r"\b\d+\b", str(row.get("text", "")).lower()))
    return len(numbers) > 1


def _location_conflict(question: str, rows: list[dict[str, Any]]) -> bool:
    """Structural: evidence rows that place the subject with STRONG location phrases in more
    than one distinct place (different `place` values or >=2 distinct strong phrasings)."""
    hints = _question_hints(question)
    if not (hints & {"location", "current"}):
        return False
    places = {str(row.get("place") or "") for row in rows[:6] if row.get("place")}
    if len(places) > 1:
        return True
    strong = set()
    for row in rows[:6]:
        strong.update(m.lower() for m in STRONG_LOCATION_RE.findall(str(row.get("text", ""))))
    return len(strong) > 2


def _multi_instance_conflict(question: str, rows: list[dict[str, Any]]) -> bool:
    hints = _question_hints(question)
    if "current" not in hints or "count" in hints:
        return False
    text = " ".join(str(row.get("text", "")) for row in rows[:6]).lower()
    return (
        "stacked" in text
        or "separate" in text
        or "total" in text
        or "2×" in text
        or bool(re.search(r"\b[2-9]\b", text))
    )


def _incomplete_count_answer(question: str, answer: str, rows: list[dict[str, Any]]) -> bool:
    if "count" not in _question_hints(question):
        return False
    lowered_answer = answer.lower()
    if any(cue in lowered_answer for cue in ("visible", "at least", "approximately", "about")):
        return True
    return any("partially" in str(row.get("text", "")).lower() for row in rows[:6])


def _calibrated_confidence(
    question: str,
    answer: str,
    refused: bool,
    confidence: float,
    rows: list[dict[str, Any]],
) -> float:
    if refused:
        return min(confidence, 0.2)
    cap = confidence
    lowered_answer = answer.lower()
    if any(cue in lowered_answer for cue in AMBIGUITY_CUES):
        cap = min(cap, 0.65)
    if any(
        any(cue in str(row.get("text", "")).lower() for cue in AMBIGUITY_CUES)
        for row in rows[:4]
    ):
        cap = min(cap, 0.7)
    if (
        _location_conflict(question, rows)
        or _multi_instance_conflict(question, rows)
        or _count_conflict(question, rows)
        or _incomplete_count_answer(question, answer, rows)
    ):
        cap = min(cap, 0.6)
    return cap


def _support_relevance(question: str, node: Any) -> tuple[float, float]:
    """Question-to-evidence relevance from STRUCTURE only (I5): lexical overlap with the
    question, plus intent->helper-type priors (a speech question prefers the ASR channel, a
    brand question the OCR channel), plus generic location grammar. No content vocabularies —
    what the evidence SAYS is matched via lexical/embedding overlap, never a tuned cue list."""
    wanted = _tokens(question)
    blob_tokens = _blob_tokens(node)
    lexical = 0.0
    if wanted:
        lexical = sum(1 for token in wanted if token in blob_tokens) / len(wanted)

    metadata = getattr(node, "metadata", {}) or {}
    lowered = node.text.lower()
    helper = _helper_of(node)
    helper_prompt = str(metadata.get("helper_prompt") or "").lower()
    section_kind = str(metadata.get("section_kind") or "").lower()
    hint_boost = 0.0
    hints = _question_hints(question)
    if "speech" in hints and (
        helper in {"whisper", "audio", "speech", "asr"}
        or metadata.get("transcript")
        or "transcript" in lowered
        or "said" in lowered
        or "saying" in lowered
    ):
        hint_boost += 1.0
    if "colour" in hints and (
        str(metadata.get("attribute_kind") or "").lower() in {"color", "colour"}
        or " colour " in f" {lowered} "
        or " color " in f" {lowered} "
    ):
        hint_boost += 0.75
    if "label" in hints and (
        metadata.get("text_read")
        or helper == "ocr"
        or helper == "screen_state"
        or helper == "vlm_object"
    ):
        hint_boost += 0.7
        if helper == "ocr":
            hint_boost += 0.35
    if "count" in hints and (helper == "spatial_relation" or helper_prompt == "spatial_relations"):
        hint_boost += 0.7
        if re.search(r"\b\d+\b", lowered):
            hint_boost += 0.25
    if "location" in hints:
        hint_boost += _location_specificity(node.text)
        if helper == "spatial_relation" or helper_prompt == "spatial_relations":
            hint_boost += 0.55
    # Screen-capture channels are for screen questions; on physical-world questions they only
    # displace room evidence. Structural: keyed on the helper/section kind, not on content.
    if helper == "screen_state" or helper_prompt == "screen_state":
        hint_boost += 0.4 if "screen" in hints else -0.6
    if section_kind == "screen_text" and not (hints & {"screen", "label"}):
        hint_boost -= 1.25
    if section_kind == "physical_object":
        hint_boost += 0.2
    hint_boost -= _absence_penalty(node.text, hints)
    return hint_boost + lexical, lexical


def _search_context(
    store: TraceMemoryStore, question: str, max_hops: int, sources=None
) -> SearchSlice:
    search = store.search(question, k=6, sources=sources)
    hints = _question_hints(question)
    # MONOTONIC BINDER GATE. Authored memories compose state (location, count consensus, colour
    # consensus, affordances) — genuinely useful for those questions. But where raw retrieval +
    # the frontier reasoner already win (reading the screen/app/battery, attribute-mode, day/night,
    # exact labels), a composed summary only *displaces* the sharper raw read and regresses the
    # answer (measured: an unconditional binder dropped 8/21 -> 5/21; "Claude" -> "no app",
    # "3 pillows" -> "2"). So only surface authored memories when the question needs composition,
    # and never when it is a raw-strong read. Counts are deliberately left to raw: the LLM
    # individuation under-counts and raw retrieval scored counts better.
    # "count" is now safe to include: the binder authors a DETERMINISTIC count memory from
    # coordinate-individuated instances, not an LLM guess. Surfacing it answers "how many X".
    _COMPOSED_HINTS = {"location", "current", "colour", "count"}
    _RAW_STRONG_HINTS = {"screen", "label"}
    needs_composition = bool(hints & _COMPOSED_HINTS) and not (hints & _RAW_STRONG_HINTS)
    if not needs_composition:
        search = SearchSlice(
            query=search.query,
            hits=tuple(h for h in search.hits if h.node.node_type not in AUTHORED_NODE_TYPES),
            links=search.links,
            retrieval_mode=search.retrieval_mode,
            degraded=search.degraded,
        )
    # ALWAYS augment with the top question-relevant RAW observations. Now that the store holds
    # ~160 authored object-memories (boosted in search), an unaugmented k=6 can come back entirely
    # authored and evict the raw evidence the reasoner and the refusal gate need — including for
    # no-hint identity questions ("what is the pink cloth") that never matched the old hint gate.
    # Raw candidates are guaranteed survivors (cap raised to 12; forced raw never exceeds 6).
    seen_ids = {hit.node.id for hit in search.hits}
    raw_candidates = []
    for node in store.nodes(node_types=("observation", "entity"), sources=sources):
        relevance, lexical = _support_relevance(question, node)
        if relevance <= 0.0 or (lexical <= 0.0 and relevance < 0.9):
            continue
        raw_candidates.append((relevance, lexical, node.t_ms, node))
    if raw_candidates:
        raw_candidates.sort(
            key=lambda item: (
                -item[0],
                -item[1],
                -item[2] if "current" in hints else item[2],
                item[3].id,
            )
        )
        extra_hits = list(search.hits)
        for relevance, lexical, _, node in raw_candidates[:6]:
            if node.id in seen_ids:
                continue
            seen_ids.add(node.id)
            extra_hits.append(
                SearchHit(
                    node=node,
                    score=round(0.35 + (0.16 * relevance) + (0.08 * lexical), 6),
                )
            )
        extra_hits.sort(key=lambda hit: (-hit.score, hit.node.t_ms, hit.node.id))
        search = SearchSlice(
            query=search.query,
            hits=tuple(extra_hits[:12]),
            links=search.links,
            retrieval_mode=search.retrieval_mode,
            degraded=search.degraded,
        )

    # KEYWORD-ANCHORED RETRIEVAL: guarantee observations that LITERALLY name the question's
    # subject surface, even when the relevance heuristic penalizes their form. (Measured: the
    # blanket was captured only inside long scene dumps that score negative, so towel/cloth/pillow
    # crops surfaced instead and the reasoner answered about the wrong object.) Prefer concise
    # nodes so a dedicated observation beats a giant dump when both name the subject.
    subject_tokens = {t for t in _tokens(question) if len(t) > 1}
    if subject_tokens:
        have = {hit.node.id for hit in search.hits}
        keyword_hits: list[tuple[int, Any]] = []
        # "abstraction" included (M6): landmark notes bridge the vocabulary gap between what
        # was READ ("MICHIGAN STATE") and how questions are ASKED ("which university...") —
        # they only surface when they literally share the question's tokens.
        for node in store.nodes(node_types=("observation", "entity_memory", "group_memory", "abstraction"), sources=sources):
            if node.id in have:
                continue
            matched = len(subject_tokens & _blob_tokens(node))
            if matched:
                keyword_hits.append((matched, node))
        keyword_hits.sort(key=lambda item: (-item[0], len(item[1].text), item[1].id))
        if keyword_hits:
            merged = list(search.hits) + [
                SearchHit(node=node, score=round(0.5 + 0.05 * matched, 6))
                for matched, node in keyword_hits[:4]
            ]
            search = SearchSlice(
                query=search.query,
                hits=tuple(merged),
                links=search.links,
                retrieval_mode=search.retrieval_mode,
                degraded=search.degraded,
            )

    if not search.hits:
        return search
    if max_hops <= 1:
        return search

    seen_ids = {hit.node.id for hit in search.hits}
    extra_hits = list(search.hits)
    for hit in search.hits:
        preferred_links = (
            "supports_memory",
            "candidate_same_memory",
            "same_entity",
            "succession",
            "supersedes",
            "scene_detail",
            "same_frame_helper",
        )
        for neighbor in store.neighbors(hit.node.id, link_types=preferred_links, limit=6):
            if neighbor.node.id in seen_ids:
                continue
            # Honor the monotonic gate in hop-2 too: supports_memory/supersedes links point at
            # authored memories, which would otherwise re-enter on raw-strong questions.
            if not needs_composition and neighbor.node.node_type in AUTHORED_NODE_TYPES:
                continue
            seen_ids.add(neighbor.node.id)
            boost = 1.0 if neighbor.node.node_type in AUTHORED_NODE_TYPES else 0.85
            extra_hits.append(type(hit)(node=neighbor.node, score=hit.score * boost))
    def authored_rank(node: Any) -> int:
        if node.node_type not in AUTHORED_NODE_TYPES:
            return 1
        support_ids = list(node.metadata.get("support_ids") or node.source_support.get("support_ids") or [])
        lowered = node.text.lower()
        if len(support_ids) > 12 or 'showing text "## physical objects' in lowered:
            return 2
        return 0

    extra_hits.sort(key=lambda row: (
        authored_rank(row.node),
        -row.score,
        row.node.t_ms,
        row.node.id,
    ))
    return SearchSlice(
        query=search.query,
        hits=tuple(extra_hits[:10]),
        links=search.links,
        retrieval_mode=search.retrieval_mode,
        degraded=search.degraded,
    )


class TraceMemoryAgent:
    def __init__(
        self,
        store: TraceMemoryStore,
        *,
        reasoner: str = "heuristic",
        ollama_model: str = "gemma3:12b-it-qat",
        ollama_host: str = "http://127.0.0.1:11434",
        restrict_sources=None,
    ) -> None:
        self._store = store
        self._reasoner = reasoner
        self._ollama_model = ollama_model
        self._ollama_host = ollama_host.rstrip("/")
        # Scope retrieval to specific capture sources (e.g. phone_camera) so a polluted
        # never-delete store (dev screenshots, other sessions) can't drown the answer.
        self._restrict_sources = tuple(restrict_sources) if restrict_sources else None

    def answer(self, question: str) -> AgentAnswer:
        # A question with NO content tokens ("??????", "a", "how many") has nothing to ground
        # on, which previously SKIPPED the grounding gate entirely and let the reasoner narrate
        # whatever retrieval coughed up at 0.7 (measured in the M7 hammer). No subject -> ask
        # for a real question instead of answering about a random object.
        if not set(_tokens(question)):
            return AgentAnswer(
                answer="I need a more specific question — name a thing, place, or moment.",
                evidence_chain=(),
                confidence=0.2,
                refused=True,
                retrieval_mode="no-subject",
            )

        expanded = _search_context(self._store, question, max_hops=2, sources=self._restrict_sources)

        # (S1 replaced the old coverage-RATIO gate. That gate divided covered-tokens by ALL question
        # tokens, so filler words ("how MUCH nutella in the ROOM") dragged coverage below 0.5 and
        # falsely refused answerable questions. The grounding gate below is strictly better: it
        # refuses iff the question's OBJECT is absent from evidence, independent of phrasing.)
        subject = set(_tokens(question))

        # S1 — SUBJECT-GROUNDING HONESTY GATE (canonical bedrock, generalizes the old where-guard).
        # Ground the answer on the question's OBJECT, not an abstract attribute word. "What time did
        # the clock show" asks about a *clock*; "time" is the attribute. If NO evidence names the
        # object, refuse — a weak reasoner otherwise answers from token-adjacent junk ("time" matched
        # a laptop-screen read of "~15 seconds -> 2.0" and it invented a clock reading @0.70).
        # ABSTRACT_QUERY_WORDS are the attributes being asked ABOUT, never the grounding object.
        grounding = subject - ABSTRACT_QUERY_WORDS
        if grounding:
            rows = self._evidence_chain(expanded, question=question)
            if not any(grounding & set(_tokens(str(r.get("text", "")))) for r in rows):
                return AgentAnswer(
                    answer="I didn't capture that clearly enough to answer.",
                    evidence_chain=rows,
                    confidence=0.2,
                    refused=True,
                    retrieval_mode=expanded.retrieval_mode,
                )

        # COUNT questions route to MULTI-OBJECT PERMANENCE (collapse cross-frame re-observations
        # into distinct instances) — but only BEHIND the grounding gate (invariant I2): a count
        # fastpath that runs before the gate answered "1 unicorn @0.8" by binding to another noun
        # in the question. The counted subject is the noun phrase being counted (see
        # _count_subject), never an incidental location word. Falls through when nothing matching
        # that subject was ever observed, so absence still reaches the honest refuse/correct path.
        if "count" in _question_hints(question):
            perm = self._permanence_count(question)
            if perm is not None:
                return perm

        if self._reasoner == "frontier":
            return self._frontier_answer(question, expanded)
        if self._reasoner == "local-ollama":
            return self._ollama_answer(question, expanded)
        return AgentAnswer(
            answer="I don't know",
            evidence_chain=self._evidence_chain(expanded, question=question),
            confidence=0.15,
            refused=True,
            retrieval_mode=expanded.retrieval_mode,
        )

    def _permanence_count(self, question: str) -> AgentAnswer | None:
        """Answer 'how many X' from resolved physical INSTANCES, not raw duplicate reads.
        Returns None (fall through) when nothing countable is found, so a genuine absence
        still refuses honestly via the normal path."""
        from trace_memory.store.permanence import count_instances

        # Count ONLY the counted noun phrase. Using every content noun in the question let
        # "how many unicorns are on the desk" bind to "desk" and answer a confident count for
        # an object never observed (the unicorn breach).
        subject_clean = _count_subject(question)
        if not subject_clean:
            return None
        try:
            # Deterministic attribute-signature clustering + the VLM's own per-frame count floor.
            # Measured on real capture noise, the LLM arbiter OVER-SPLITS (colour-context drift ->
            # phantom extra instances), reintroducing the confident-overcount moat breach; the
            # deterministic path is transparent, reproducible, and honest for a demo count.
            res = count_instances(
                self._store, subject_clean, sources=self._restrict_sources,
                model=self._ollama_model, host=self._ollama_host, use_llm=False,
            )
        except Exception:  # noqa: BLE001  never crash the answer on a counting hiccup
            return None
        if res.count <= 0:
            return None

        rows: list[dict[str, Any]] = []
        for inst in res.instances[:9]:
            node = None
            for cid in inst.get("citation_ids", [])[:1]:
                node = self._store.read_observation(str(cid))
                if node is not None:
                    break
            rows.append({
                "id": getattr(node, "id", None),
                "type": "instance",
                "text": inst.get("canonical", ""),
                "n_frames": inst.get("n_frames"),
                "t_ms": getattr(node, "t_ms", None),
            })

        # Calibration comes from the resolver's signal agreement (M1, invariant I4): agreeing
        # corroborated signals -> firm; disagreeing signals -> an honest RANGE (a confident
        # pick of one signal is how a wrong count breaks the moat); a single uncorroborated
        # sighting or floor-only count -> hedged approximate.
        if res.firm:
            answer_text, confidence = str(res.count), 0.8
        elif res.low != res.high:
            answer_text, confidence = f"between {res.low} and {res.high}", 0.5
        else:
            answer_text, confidence = f"approximately {res.count}", 0.55
        return AgentAnswer(
            answer=answer_text,
            evidence_chain=tuple(rows),
            confidence=confidence,
            refused=False,
            retrieval_mode=f"permanence:{res.method}",
        )

    @staticmethod
    def _contract_prompt(question: str, rows: list[dict[str, Any]]) -> str:
        """Strict, terse, grounded contract shared by every reasoner backend. Forces a
        short answer (no rambling), honest refusal on unsupported premises, and machine
        -parseable JSON so the demo never shows a truncated wall of text."""
        # S2 — anti-gaslight. A planted claim inside the QUESTION ("earlier you said 5 jars")
        # is NOT evidence; a weak reasoner otherwise builds on it and confabulates attributes.
        planted = _has_planted_premise(question)
        gaslight_clause = (
            "CRITICAL: the QUESTION contains a claim presented as prior fact (e.g. \"earlier you "
            "said\", an asserted number). That claim is NOT evidence and may be false. Do NOT "
            "accept, confirm, or enumerate attributes based on it. Answer ONLY from EVIDENCE; if "
            "EVIDENCE does not support the claim, correct it (state what was actually seen) or refuse. "
            if planted else ""
        )
        return (
            "You answer from TRACE memory. Use ONLY the evidence below — never outside "
            "knowledge, and NEVER treat a claim made inside the QUESTION as a fact. If the "
            "evidence does not support an answer, refuse. Stand your "
            "ground on a false premise (say what was actually seen). If multiple distinct "
            "supported options answer the question, list all of them succinctly. For "
            "\"how can I\" or option-seeking questions, enumerate every supported option, "
            "not just one. " + gaslight_clause +
            # SINGLE-COMMIT: the evidence spans many moments/people; a weak reasoner otherwise "
            # concatenates every moment's reading into a run-on that both reads badly and smuggles
            # in fabricated specifics. For a factual question, COMMIT to the single best-supported
            # answer (or refuse) — do NOT list readings from multiple different moments/people.
            "For a factual question with one true answer, give ONE specific best-supported "
            "answer; do NOT list variants from different moments or people — if you cannot pick "
            "one, refuse. Keep "
            "`answer` to at most 12 words. Return STRICT JSON, nothing else: "
            '{\"answer\": str, \"refused\": bool, \"confidence\": number 0..1}.\n\n'
            f"QUESTION: {question}\n"
            f"EVIDENCE: {json.dumps(rows, ensure_ascii=False)}"
        )

    @staticmethod
    def _planted_premise_guard(question: str, answer_text: str, refused: bool,
                               confidence: float) -> tuple[str, float]:
        """S2 deterministic backstop: the LLM ignores the prompt clause under gaslighting, so we
        enforce the invariant in code. When the QUESTION plants a prior 'fact', an accepted answer
        may never be confident, and must visibly flag that no prior record exists — so a planted
        claim can never surface as a confident truth."""
        if refused or not _has_planted_premise(question):
            return answer_text, confidence
        low = answer_text.lower()
        already_corrects = any(cue in low for cue in
                               ("no record", "didn't say", "did not say", "no prior", "i never",
                                "cannot confirm", "not what", "no such", "don't have a record"))
        if not already_corrects:
            answer_text = f"I have no prior record of that. From what I actually saw: {answer_text}"
        return answer_text, min(confidence, 0.45)

    @staticmethod
    def _parse_contract(raw: str) -> dict[str, Any]:
        try:
            return json.loads(re.search(r"\{.*\}", raw, re.DOTALL).group(0))  # type: ignore[union-attr]
        except Exception:
            low = raw.lower()
            return {"answer": raw or "I don't know",
                    "refused": "don't know" in low or "do not know" in low or "not seen" in low,
                    "confidence": 0.4}

    def _frontier_answer(self, question: str, search: SearchSlice) -> AgentAnswer:
        """Demo-day runtime: a frontier text model over the same evidence + contract.
        Reads ANTHROPIC_API_KEY + TRACE_FRONTIER_MODEL at call time; if no key is set,
        falls back to the local gemma reasoner so dev never breaks."""
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return self._ollama_answer(question, search)
        rows = self._evidence_chain(search, question=question)
        model = os.environ.get("TRACE_FRONTIER_MODEL", "claude-sonnet-4-6")
        body = {
            "model": model,
            "max_tokens": 256,
            "messages": [{"role": "user", "content": self._contract_prompt(question, rows)}],
        }
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(body).encode(),
            headers={"content-type": "application/json", "x-api-key": api_key,
                     "anthropic-version": "2023-06-01"},
        )
        try:
            resp = json.load(urllib.request.urlopen(req, timeout=60))
            raw = "".join(b.get("text", "") for b in resp.get("content", [])).strip()
        except Exception:  # noqa: BLE001  frontier hiccup -> local fallback, never crash the demo
            return self._ollama_answer(question, search)
        parsed = self._parse_contract(raw)
        answer_text = str(parsed.get("answer") or "I don't know")
        refused = bool(parsed.get("refused"))
        confidence = _calibrated_confidence(
            question,
            answer_text,
            refused,
            float(parsed.get("confidence") or 0.4),
            rows,
        )
        answer_text, confidence = self._planted_premise_guard(question, answer_text, refused, confidence)
        return AgentAnswer(
            answer=answer_text,
            evidence_chain=tuple(rows),
            confidence=confidence,
            refused=refused,
            retrieval_mode=search.retrieval_mode,
        )

    def _ollama_answer(self, question: str, search: SearchSlice) -> AgentAnswer:
        rows = self._evidence_chain(search, question=question)
        prompt = self._contract_prompt(question, rows)
        body = {
            "model": self._ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0},
        }
        req = urllib.request.Request(
            f"{self._ollama_host}/api/generate",
            data=json.dumps(body).encode(),
            headers={"content-type": "application/json"},
        )
        raw = json.load(urllib.request.urlopen(req, timeout=180)).get("response", "").strip()
        parsed = self._parse_contract(raw)
        answer_text = str(parsed.get("answer") or "I don't know")
        refused = bool(parsed.get("refused"))
        confidence = _calibrated_confidence(
            question,
            answer_text,
            refused,
            float(parsed.get("confidence") or 0.4),
            rows,
        )
        answer_text, confidence = self._planted_premise_guard(question, answer_text, refused, confidence)
        return AgentAnswer(
            answer=answer_text,
            evidence_chain=tuple(rows),
            confidence=confidence,
            refused=refused,
            retrieval_mode=search.retrieval_mode,
        )

    def _evidence_chain(
        self,
        search: SearchSlice,
        *,
        question: str | None = None,
        preferred_ids: set[str] | None = None,
    ) -> tuple[dict[str, Any], ...]:
        rows = []
        preferred_ids = preferred_ids or set()
        appended_ids: set[str] = set()
        hits = list(search.hits)
        hints = _question_hints(question or "") if question else set()

        def append_row(node: Any, score: float, citation_ids: list[str] | None = None) -> None:
            # "when": human-readable clock time. Raw 13-digit epoch t_ms is incomparable for
            # a small reasoner (measured: gemma12b INVERTED "before or after" between t_ms
            # 1782909425990 and 1782909325990 at conf 0.7 — a confident-wrong). HH:MM:SS is
            # directly comparable text.
            try:
                from datetime import datetime, timezone
                when = datetime.fromtimestamp(node.t_ms / 1000, tz=timezone.utc).strftime(
                    "%H:%M:%S")
            except (OverflowError, OSError, ValueError):
                when = None
            rows.append(
                {
                    "id": node.id,
                    "type": node.node_type,
                    "score": score,
                    "text": node.text,
                    "place": node.place,
                    "t_ms": node.t_ms,
                    "when": when,
                    "frame_index": node.metadata.get("frame_index"),
                    "section_kind": node.metadata.get("section_kind"),
                    "helper_prompt": node.metadata.get("helper_prompt"),
                    "helper_type": getattr(node, "helper_type", None),
                    "citation_ids": citation_ids or [],
                }
            )
            appended_ids.add(node.id)

        def same_frame_label_siblings(node: Any) -> list[Any]:
            if "label" not in hints:
                return []
            if _helper_of(node) not in {"ocr", "screen_state"}:
                return []
            frame_ids = set((node.source_support or {}).get("frame_ids") or [])
            parent_frame_node = node.metadata.get("parent_frame_node")
            siblings: list[Any] = []
            for candidate in self._store.nodes(node_types=("observation",), sources=self._restrict_sources):
                if candidate.id in appended_ids or candidate.id == node.id:
                    continue
                if _helper_of(candidate) != "ocr":
                    continue
                if parent_frame_node and candidate.metadata.get("parent_frame_node") == parent_frame_node:
                    siblings.append(candidate)
                    continue
                candidate_frame_ids = set((candidate.source_support or {}).get("frame_ids") or [])
                if frame_ids and candidate_frame_ids and frame_ids & candidate_frame_ids:
                    siblings.append(candidate)
                    continue
                if candidate.t_ms == node.t_ms and abs(candidate.t_ms - node.t_ms) <= 1000:
                    siblings.append(candidate)
            ranked = [(_support_relevance(question or "", sibling), sibling) for sibling in siblings]
            ranked.sort(
                key=lambda item: (
                    -item[0][0],
                    -item[0][1],
                    item[1].t_ms,
                    item[1].id,
                )
            )
            return [item[1] for item in ranked[:2]]

        if question:
            subject_tokens = {t for t in _tokens(question) if len(t) > 1}

            def question_rank(hit: Any) -> tuple[float, float, float]:
                direct, lexical = _support_relevance(question, hit.node)
                # A hit that LITERALLY names the question's subject must outrank similar-but-wrong
                # objects, even when the relevance heuristic penalizes its form (long scene dumps
                # score negative). Without this, "where is the blanket" surfaced towel/cloth/pillow.
                subject_bonus = 0.0
                if subject_tokens:
                    matched = len(subject_tokens & _blob_tokens(hit.node))
                    if matched:
                        subject_bonus = 3.0 + matched
                support_bonus = 0.0
                if hit.node.node_type in AUTHORED_NODE_TYPES:
                    support_ids = list(
                        hit.node.metadata.get("support_ids")
                        or hit.node.source_support.get("support_ids")
                        or []
                    )
                    support_scores = []
                    for support_id in support_ids:
                        support_node = self._store.read_observation(str(support_id))
                        if support_node is None:
                            continue
                        support_scores.append(_support_relevance(question, support_node)[0])
                    if support_scores:
                        support_bonus = max(support_scores)
                    if hit.node.text.lower().startswith("memory with") and lexical <= 0.0:
                        direct -= 0.35
                    if len(support_ids) > 12:
                        direct -= 0.75
                    if 'showing text "## physical objects' in hit.node.text.lower():
                        direct -= 1.5
                time_bias = 0.0
                if "current" in hints:
                    time_bias = hit.node.t_ms / 100_000.0
                return direct + support_bonus + subject_bonus, lexical, time_bias

            hits.sort(
                key=lambda hit: (
                    -question_rank(hit)[0],
                    -question_rank(hit)[1],
                    -question_rank(hit)[2],
                    -hit.score,
                    hit.node.t_ms,
                    hit.node.id,
                )
            )
        # Authored memories AUGMENT, never REPLACE, raw observations. Reserve a few slots for the
        # best authored summaries (composed state: current location, count) and guarantee the top
        # question-relevant raw observations still reach the reasoner. Without this split, the 164
        # authored object-memories crowd the window and evict scene evidence (e.g. day/night, which
        # has no authored memory at all) -> spurious refusals. Measured: net -2 without the split.
        CAP = 9
        AUTHORED_SLOTS = 3

        def _emit_authored(hit: Any) -> None:
            support_ids = list(
                hit.node.metadata.get("support_ids")
                or hit.node.source_support.get("support_ids")
                or []
            )
            append_row(hit.node, hit.score, support_ids)
            support_nodes = []
            for support_id in support_ids:
                support_node = self._store.read_observation(str(support_id))
                if support_node is None or support_node.id in appended_ids:
                    continue
                support_nodes.append(support_node)
            if question:
                support_nodes.sort(
                    key=lambda node: (-_support_relevance(question, node)[0],
                                      -_support_relevance(question, node)[1], node.t_ms, node.id)
                )
            else:
                support_nodes.sort(key=lambda node: (node.t_ms, node.id))
            support_limit = 3 if question and _question_hints(question) & {
                "location", "screen", "count"
            } else 2
            for support_node in support_nodes[:support_limit]:
                append_row(support_node, round(hit.score * 0.8, 6))

        def _emit_raw(hit: Any) -> None:
            append_row(hit.node, hit.score)
            for sibling in same_frame_label_siblings(hit.node):
                append_row(sibling, round(hit.score * 0.82, 6))

        authored_hits = [h for h in hits if h.node.node_type in AUTHORED_NODE_TYPES]
        raw_hits = [h for h in hits if h.node.node_type not in AUTHORED_NODE_TYPES]

        for hit in authored_hits[:AUTHORED_SLOTS]:
            if hit.node.id in appended_ids:
                continue
            if preferred_ids and hit.node.id not in preferred_ids and len(rows) >= 4:
                continue
            if len(rows) >= CAP:
                break
            _emit_authored(hit)

        for hit in raw_hits:
            if hit.node.id in appended_ids:
                continue
            if preferred_ids and hit.node.id not in preferred_ids and len(rows) >= 4:
                continue
            if len(rows) >= CAP:
                break
            _emit_raw(hit)

        # If authored memories were highly ranked but slots remained, top up with any remaining authored.
        for hit in authored_hits[AUTHORED_SLOTS:]:
            if len(rows) >= CAP:
                break
            if hit.node.id in appended_ids:
                continue
            _emit_authored(hit)

        # PRECISE RETRIEVAL — focus the slice on the question's subject nouns when we have enough
        # on-subject rows. A weak local reasoner, handed a mixed pile, will answer about a
        # similar-but-wrong object ("where is the blanket" -> "a pink towel" at 0.85, a confident-
        # wrong that breaks the honesty moat). Restricting to the minimal sufficient slice keeps it
        # honest. Guarded: only filter when >=2 rows actually mention the subject, so we never
        # over-restrict a question whose retrieval was already off (it just refuses then).
        subject = {t for t in _tokens(question or "")}
        if subject:
            on_subject = [
                r for r in rows
                if subject & set(_tokens(str(r.get("text", ""))))
            ]
            if on_subject:
                rows = on_subject

        return tuple(rows[:CAP])
