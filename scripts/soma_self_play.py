#!/usr/bin/env python3
"""The 24/7 robot: continuously quiz SOMA's memory with LOCAL AI and log the gaps.

Safe by construction: it MEASURES and mines misses. It never edits code, never
commits. Two auto-graded probes (no human gold needed):

  RECALL probe       -- generate a question whose answer IS a bound fact, ask the
                        engine, pass iff the engine recovers that fact.
  HALLUCINATION probe -- ask about things never perceived; the engine MUST refuse.
                        If it answers, that is a caught hallucination.

Each round appends a JSON line to ops/cockpit/self_play.jsonl, which the cockpit
reads. Every engine answer is a real local-gemma call, so the local model is
working the whole time.

Run:  python3 scripts/soma_self_play.py            (loops forever)
      python3 scripts/soma_self_play.py --once      (one round, for testing)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COCKPIT = ROOT / "ops" / "cockpit"
WALK_MEM = ROOT / "data" / "walks" / "walk_outside_20260614" / "memory"
LOG = COCKPIT / "self_play.jsonl"
sys.path.insert(0, str(ROOT / "src"))

from soma.application.grounding_gate import REFUSAL_TEXT  # noqa: E402
from soma.demo import build_bound_memory, make_recall  # noqa: E402
from soma.domain.query import Query  # noqa: E402

# Plausible-but-never-perceived questions: the honest engine must refuse all.
HALLUCINATION_PROBES = [
    "What was the license plate of the car parked outside?",
    "What was the air temperature in degrees?",
    "What phone number was written on the wall?",
    "How much did the coffee cost?",
    "What was the wifi password shown on screen?",
]


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) >= 3}


def _is_refusal(answer: str) -> bool:
    low = (answer or "").strip().lower()
    return (not low) or low.startswith(REFUSAL_TEXT[:18].lower()) or "don't know" in low or "do not know" in low


def _recall_probes(result: object) -> list[tuple[str, set[str]]]:
    """Templated questions whose gold is a bound fact (subject/object tokens)."""
    probes: list[tuple[str, set[str]]] = []
    labels = {e.entity_id: e.label for e in result.entities}  # type: ignore[attr-defined]
    ranked = sorted(result.bindings, key=lambda b: b.confidence.value, reverse=True)  # type: ignore[attr-defined]
    for binding in ranked:
        label = labels.get(binding.subject_id, "")
        value = binding.object_text or ""
        if binding.predicate == "object" and len(value) >= 3:
            probes.append((f"What did the {value} say or show?", _tokens(label)))
        elif binding.predicate != "present" and len(value) >= 3:
            probes.append((f"What was the {binding.predicate} of the {label}?", _tokens(value)))
        if len(probes) >= 6:
            break
    return probes


def run_round(model: str) -> dict[str, object]:
    result, corpus = build_bound_memory(str(WALK_MEM))
    from soma.adapters.ollama import OllamaReasoner

    recall = make_recall(OllamaReasoner(model=model), result, corpus)
    misses: list[str] = []

    probes = _recall_probes(result)
    rc = 0
    for question, gold_tokens in probes:
        answer = recall.answer(Query(question), str(WALK_MEM)).text
        if not _is_refusal(answer) and gold_tokens & _tokens(answer):
            rc += 1
        else:
            misses.append(f"could not recall: {question}")

    ha = 0
    for question in HALLUCINATION_PROBES:
        answer = recall.answer(Query(question), str(WALK_MEM)).text
        if not _is_refusal(answer):
            ha += 1
            misses.append(f"HALLUCINATED on: {question} -> {answer[:50]}")

    return {
        "epoch": int(time.time()),
        "recall_correct": rc,
        "recall_total": len(probes),
        "halluc_answered": ha,
        "halluc_total": len(HALLUCINATION_PROBES),
        "misses": misses,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="SOMA 24/7 self-play robot")
    parser.add_argument("--model", default="gemma3:12b-it-qat")
    parser.add_argument("--sleep", type=int, default=120, help="seconds between rounds")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    COCKPIT.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            summary = run_round(str(args.model))
            with LOG.open("a") as handle:
                handle.write(json.dumps(summary) + "\n")
            print(
                f"[round] recall {summary['recall_correct']}/{summary['recall_total']} "
                f"halluc {summary['halluc_answered']}/{summary['halluc_total']}",
                flush=True,
            )
        except Exception as exc:  # the robot must never die on one bad round
            print(f"[round-error] {exc}", file=sys.stderr, flush=True)
        if args.once:
            return 0
        time.sleep(max(10, int(args.sleep)))


if __name__ == "__main__":
    raise SystemExit(main())
