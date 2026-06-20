"""Grounded recall: answer from bound memory, then refuse what wasn't perceived.

The flow is deliberately layered so fluency cannot outrun provenance:

  1. load bound memory (the auditable consensus) and the raw captured corpus;
  2. compress the bindings into a compact dossier and ask a TextReasoner to
     answer ONLY from that dossier;
  3. pass the draft through the deterministic grounding gate, which refuses any
     answer the corpus cannot support;
  4. on assert, attach citations drawn from the provenance of the bindings whose
     content actually surfaced in the answer.

The backend is dependency-inverted: it never touches the filesystem. The caller
supplies how a memory_reference becomes bound memory and a raw-text corpus.
"""

from __future__ import annotations

import re
from typing import Callable

from soma.application.binder import BindResult
from soma.application.grounding_gate import ground
from soma.domain.binding import Binding
from soma.domain.query import Citation, Query, RecallAnswer
from soma.ports.text_reasoner import TextReasoner

_PROMPT_TEMPLATE = (
    "Answer the question using ONLY the facts in MEMORY below. "
    "If the answer is not in MEMORY, say you don't know — do not guess.\n\n"
    "MEMORY:\n{dossier}\n\n"
    "QUESTION: {question}\n\nANSWER:"
)


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


class GroundedRecall:
    """A RecallBackend that grounds a reasoned draft against captured text."""

    def __init__(
        self,
        reasoner: TextReasoner,
        load_memory: Callable[[str], BindResult],
        load_corpus: Callable[[str], str],
    ) -> None:
        self._reasoner = reasoner
        self._load_memory = load_memory
        self._load_corpus = load_corpus

    def answer(self, query: Query, memory_reference: str) -> RecallAnswer:
        memory = self._load_memory(memory_reference)
        corpus = self._load_corpus(memory_reference)
        labels = {entity.entity_id: entity.label for entity in memory.entities}

        dossier = self._dossier(memory.bindings, labels)
        prompt = _PROMPT_TEMPLATE.format(dossier=dossier, question=query.text)
        draft = self._reasoner.reason(prompt)

        decision, text = ground(draft, corpus)
        if decision == "refuse":
            return RecallAnswer(text, ())
        return RecallAnswer(text, self._citations(memory.bindings, labels, draft))

    def _dossier(self, bindings: tuple[Binding, ...], labels: dict[str, str]) -> str:
        lines = [self._dossier_line(binding, labels) for binding in bindings]
        return "\n".join(lines) if lines else "(no bound facts)"

    @staticmethod
    def _dossier_line(binding: Binding, labels: dict[str, str]) -> str:
        label = labels.get(binding.subject_id, binding.subject_id)
        value = binding.object_text or ""
        if binding.predicate == "present":
            body = f"Seen: {label}"
        elif binding.predicate == "object":
            # the adapter stores the surface a text/logo sits on as its "object"
            body = f'On the {value}, text/logo read: "{label}"'
        else:
            body = f"{label} {binding.predicate}: {value}"
        return f"- {body} (conf {binding.confidence.value:.2f})"

    def _citations(
        self,
        bindings: tuple[Binding, ...],
        labels: dict[str, str],
        draft: str,
    ) -> tuple[Citation, ...]:
        draft_tokens = _tokens(draft)
        citations: list[Citation] = []
        seen: set[str] = set()
        for binding in bindings:
            if not self._mentioned(binding, labels, draft_tokens):
                continue
            for prov in binding.evidence:
                node_id = f"{prov.source_channel}@{prov.captured_at_ms}"
                if node_id in seen:
                    continue
                seen.add(node_id)
                citations.append(Citation(node_id=node_id, t_ms=prov.captured_at_ms))
        return tuple(citations)

    @staticmethod
    def _mentioned(binding: Binding, labels: dict[str, str], draft_tokens: set[str]) -> bool:
        label = labels.get(binding.subject_id, "")
        surface = f"{label} {binding.predicate} {binding.object_text or ''}"
        return bool(_tokens(surface) & draft_tokens)
