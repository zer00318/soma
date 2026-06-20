"""End-to-end prototype: record -> one command -> ask -> cited, grounded answer.

This is the composition root that wires the clean-architecture pieces into the
North Star V0 loop, running entirely on LOCAL models:

    legacy capture channels --> typed Observations  (adapters.legacy_channels)
        --> Binder (consensus, weak links refused)  --> bound memory
        --> GroundedRecall over a local Ollama reasoner, gated against the
            captured-text corpus so an ungrounded draft is refused, not shipped.

Pure helpers (build_bound_memory / corpus / serialization) are import-safe and
unit-tested; the network (Ollama) is only ever touched inside main().
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from soma.adapters.legacy_channels import load_observations
from soma.adapters.ollama import OllamaReasoner
from soma.application.binder import Binder, BindResult
from soma.application.grounded_recall import GroundedRecall
from soma.domain.binding import Binding
from soma.domain.observation import Observation
from soma.domain.query import Query


def corpus_from_observations(observations: list[Observation]) -> str:
    """The captured-text corpus the grounding gate checks a draft against."""
    parts: list[str] = []
    for obs in observations:
        parts.append(obs.subject)
        parts.extend(attr.value for attr in obs.attributes)
    return " ".join(parts).lower()


def build_bound_memory(memory_dir: str) -> tuple[BindResult, str]:
    observations = load_observations(memory_dir)
    result = Binder().bind(observations)
    return result, corpus_from_observations(observations)


def _binding_dict(binding: Binding, labels: dict[str, str]) -> dict[str, object]:
    return {
        "subject": labels.get(binding.subject_id, binding.subject_id),
        "predicate": binding.predicate,
        "object": binding.object_text,
        "confidence": round(binding.confidence.value, 3),
        "evidence": [
            {"channel": prov.source_channel, "t_ms": prov.captured_at_ms}
            for prov in binding.evidence
        ],
    }


def bound_memory_to_dict(result: BindResult) -> dict[str, object]:
    labels = {entity.entity_id: entity.label for entity in result.entities}
    return {
        "usable": bool(result.bindings),
        "counts": {
            "entities": len(result.entities),
            "bindings": len(result.bindings),
            "refused": len(result.refused),
        },
        "entities": [
            {"id": entity.entity_id, "kind": entity.kind, "label": entity.label}
            for entity in result.entities
        ],
        "bindings": [_binding_dict(binding, labels) for binding in result.bindings],
        "refused": [
            {"subject": link.subject, "attribute": link.attribute, "reason": link.reason}
            for link in result.refused
        ],
    }


def make_recall(reasoner: OllamaReasoner, result: BindResult, corpus: str) -> GroundedRecall:
    return GroundedRecall(reasoner, lambda _ref: result, lambda _ref: corpus)


def _print_report(result: BindResult, answer_text: str, citations: tuple[object, ...]) -> None:
    counts = bound_memory_to_dict(result)["counts"]
    print(f"bound memory: {counts}")
    print(f"\nA: {answer_text}")
    for citation in citations:
        print(f"   cite: {citation}")


def main() -> int:
    parser = argparse.ArgumentParser(description="SOMA end-to-end prototype")
    parser.add_argument("--memory-dir", required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--model", default="gemma3:12b-it-qat")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    result, corpus = build_bound_memory(str(args.memory_dir))
    out_path = Path(args.out) if args.out else Path(args.memory_dir) / "bound_memory_v2.json"
    out_path.write_text(json.dumps(bound_memory_to_dict(result), indent=2) + "\n", encoding="utf-8")

    reasoner = OllamaReasoner(model=str(args.model))
    recall = make_recall(reasoner, result, corpus)
    print(f"Q: {args.question}")
    answer = recall.answer(Query(str(args.question)), str(args.memory_dir))
    _print_report(result, answer.text, answer.citations)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
