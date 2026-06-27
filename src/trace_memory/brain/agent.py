from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass
from typing import Any

from trace_memory.store import SearchSlice, TraceMemoryStore

COUNT_RE = re.compile(r"^\s*how many (?P<subject>.+?)\s*\??\s*$", re.IGNORECASE)
EXISTS_RE = re.compile(r"^\s*is there (?P<subject>.+?)\s*\??\s*$", re.IGNORECASE)
ATTRIBUTE_RE = re.compile(
    r"^\s*what (?P<attribute>colour|color|flavour|flavor|brand|name) "
    r"(?:is|are) (?P<subject>.+?)\s*\??\s*$",
    re.IGNORECASE,
)
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "color",
    "colour",
    "flavor",
    "flavour",
    "how",
    "in",
    "is",
    "many",
    "of",
    "on",
    "the",
    "there",
    "what",
}


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


def _tokens(text: str) -> list[str]:
    return [_singularize(token) for token in _normalize(text).split() if token and token not in STOPWORDS]


def _singularize(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _blob(node: Any) -> str:
    normalized = _normalize(
        " ".join(
            (
                node.text,
                json.dumps(node.metadata, ensure_ascii=False),
                json.dumps(node.provenance, ensure_ascii=False),
            )
        )
    )
    return " ".join(_singularize(token) for token in normalized.split())


def _match_subject(
    store: TraceMemoryStore, subject: str, node_types: tuple[str, ...] = ("entity", "observation")
) -> tuple[Any, ...]:
    wanted = _tokens(subject)
    if not wanted:
        return ()
    matched = []
    for node in store.nodes(node_types=node_types):
        blob = _blob(node)
        if all(token in blob for token in wanted):
            matched.append(node)
    return tuple(matched)


def _first_colour(blob: str) -> str | None:
    for colour in ("green", "red", "blue", "brown", "yellow", "black", "white", "silver", "gold"):
        if colour in blob:
            return colour.capitalize()
    return None


def _search_context(
    store: TraceMemoryStore, question: str, max_hops: int, sources=None
) -> SearchSlice:
    search = store.search(question, k=6, sources=sources)
    if not search.hits:
        return search
    if max_hops <= 1:
        return search

    seen_ids = {hit.node.id for hit in search.hits}
    extra_hits = list(search.hits)
    for hit in search.hits:
        for neighbor in store.neighbors(hit.node.id, limit=4):
            if neighbor.node.id in seen_ids:
                continue
            seen_ids.add(neighbor.node.id)
            extra_hits.append(type(hit)(node=neighbor.node, score=hit.score * 0.85))
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
        quick = _search_context(self._store, question, max_hops=1, sources=self._restrict_sources)
        heuristic = self._heuristic_answer(question, quick)
        if heuristic is not None:
            return heuristic

        expanded = _search_context(self._store, question, max_hops=2, sources=self._restrict_sources)
        if self._reasoner == "frontier":
            return self._frontier_answer(question, expanded)
        if self._reasoner == "local-ollama":
            return self._ollama_answer(question, expanded)
        return AgentAnswer(
            answer="I don't know",
            evidence_chain=self._evidence_chain(expanded),
            confidence=0.15,
            refused=True,
            retrieval_mode=expanded.retrieval_mode,
        )

    def _heuristic_answer(self, question: str, search: SearchSlice) -> AgentAnswer | None:
        """REMOVED (T2): the brittle COUNT/EXISTS/ATTRIBUTE regex + hardcoded brand/colour
        fast-path is gone. It short-circuited the grounded reasoner with overfit guesses.
        Every question now flows to precise retrieval + the evidence-only LLM contract,
        which answers from what was actually seen or refuses honestly."""
        return None

    @staticmethod
    def _contract_prompt(question: str, rows: list[dict[str, Any]]) -> str:
        """Strict, terse, grounded contract shared by every reasoner backend. Forces a
        short answer (no rambling), honest refusal on unsupported premises, and machine
        -parseable JSON so the demo never shows a truncated wall of text."""
        return (
            "You answer from TRACE memory. Use ONLY the evidence below — never outside "
            "knowledge. If the evidence does not support an answer, refuse. Stand your "
            "ground on a false premise (say what was actually seen). Keep `answer` to at "
            "most 12 words. Return STRICT JSON, nothing else: "
            '{\"answer\": str, \"refused\": bool, \"confidence\": number 0..1}.\n\n'
            f"QUESTION: {question}\n"
            f"EVIDENCE: {json.dumps(rows, ensure_ascii=False)}"
        )

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
        rows = self._evidence_chain(search)
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
        return AgentAnswer(
            answer=str(parsed.get("answer") or "I don't know"),
            evidence_chain=tuple(rows),
            confidence=float(parsed.get("confidence") or 0.4),
            refused=bool(parsed.get("refused")),
            retrieval_mode=search.retrieval_mode,
        )

    def _ollama_answer(self, question: str, search: SearchSlice) -> AgentAnswer:
        rows = self._evidence_chain(search)
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
        return AgentAnswer(
            answer=str(parsed.get("answer") or "I don't know"),
            evidence_chain=tuple(rows),
            confidence=float(parsed.get("confidence") or 0.4),
            refused=bool(parsed.get("refused")),
            retrieval_mode=search.retrieval_mode,
        )

    def _evidence_chain(
        self,
        search: SearchSlice,
        *,
        preferred_ids: set[str] | None = None,
    ) -> tuple[dict[str, Any], ...]:
        rows = []
        preferred_ids = preferred_ids or set()
        for hit in search.hits:
            if preferred_ids and hit.node.id not in preferred_ids and len(rows) >= 4:
                continue
            rows.append(
                {
                    "id": hit.node.id,
                    "type": hit.node.node_type,
                    "score": hit.score,
                    "text": hit.node.text,
                    "place": hit.node.place,
                }
            )
        return tuple(rows[:6])
