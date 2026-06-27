#!/usr/bin/env python3
"""Annotate-as-you-live eval: score the PRODUCTION agent (trace_memory.brain.TraceMemoryAgent)
against founder-authored gold, and write the real number to evaluation/ras/store_eval.json
(the artifact the honest cockpit reads). No private heuristic — the eval grades the same brain
the demo uses, or the measurement is a lie.

Append gold as you live:
    .venv/bin/python evaluation/annotate_live.py --append --store data/trace_store.sqlite3 \
        --question "how much soya did I use" --true-answer "about half a bowl"

Score the real number (frontier reasoner; falls back to local gemma if no ANTHROPIC_API_KEY):
    .venv/bin/python evaluation/annotate_live.py --store data/trace_store.sqlite3 \
        --reasoner frontier --repeats 3
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

from trace_memory.brain import TraceMemoryAgent
from trace_memory.store import TraceMemoryStore

STORE_EVAL = Path("evaluation/ras/store_eval.json")


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def answer_question(
    store: TraceMemoryStore,
    question: str,
    *,
    reasoner: str,
    model: str,
    host: str,
) -> dict[str, Any]:
    """Route EVERY question through the production agent — the same brain the demo runs.
    'heuristic' (no LLM) refuses honestly; 'local-ollama'/'frontier' do grounded reasoning."""
    restrict = os.environ.get("TRACE_RESTRICT_SOURCES", "").strip()
    restrict_sources = tuple(s.strip() for s in restrict.split(",") if s.strip()) or None
    agent = TraceMemoryAgent(
        store, reasoner=reasoner, ollama_model=model, ollama_host=host,
        restrict_sources=restrict_sources,
    )
    answer = agent.answer(question)
    return {
        "answer": answer.answer,
        "refused": bool(answer.refused),
        "confidence": float(answer.confidence),
        "evidence_ids": [row.get("id") for row in answer.evidence_chain],
        "retrieval_mode": answer.retrieval_mode,
    }


def load_annotations(path: Path) -> list[dict[str, Any]]:
    text = path.read_text().strip()
    if not text:
        return []
    if text.startswith("["):
        return list(json.loads(text))
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def append_annotation(path: Path, question: str, true_answer: str, when: str | None) -> None:
    rows = load_annotations(path) if path.exists() else []
    rows.append({"question": question, "answer": true_answer, "when": when})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")


def judge(truth: str, answer: str, refused: bool) -> str:
    """Deterministic verdict. A refusal is honest (not wrong) unless the truth was a plain
    negative the system should have asserted. Substring/number match for positives."""
    truth_norm = _normalize(truth)
    answer_norm = _normalize(answer)
    if refused:
        if truth_norm in {"no", "there is no"}:
            return "correct"
        return "refused"
    if truth_norm == "yes":
        return "correct" if "yes" in answer_norm else "wrong"
    if truth_norm == "no" or truth_norm.startswith("there is no"):
        return "correct" if "no" in answer_norm else "wrong"
    if truth_norm.isdigit():
        return "correct" if re.search(rf"\b{truth_norm}\b", answer_norm) else "wrong"
    if truth_norm and truth_norm in answer_norm:
        return "correct"
    # Content-word overlap: all significant truth words present, in any order, even with
    # extra words ("white sneakers" matches "white and grey Puma sneakers"). Avoids the
    # false-NEGATIVE a strict contiguous-substring match produced.
    _stop = {"a", "an", "the", "is", "are", "of", "on", "in", "there", "my", "it", "and",
             "with", "near", "to", "i", "was", "were", "side"}
    truth_words = [w for w in truth_norm.split() if w not in _stop and len(w) > 2]
    if truth_words and all(w in answer_norm for w in truth_words):
        return "correct"
    return "wrong"


def score_annotations(
    annotations: list[dict[str, Any]],
    store: TraceMemoryStore,
    *,
    reasoner: str,
    model: str,
    host: str,
    repeats: int,
) -> list[dict[str, Any]]:
    results = []
    for row in annotations:
        question = str(row["question"])
        truth = str(row["answer"])
        attempts = []
        for _ in range(repeats):
            attempt = answer_question(store, question, reasoner=reasoner, model=model, host=host)
            verdict = judge(truth, str(attempt.get("answer", "")), bool(attempt.get("refused")))
            attempts.append({**attempt, "verdict": verdict})
        results.append({"question": question, "truth": truth, "attempts": attempts})
    return results


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    answered = correct = confident_wrong = 0
    for row in results:
        best = row["attempts"][0]
        verdict = best["verdict"]
        if not bool(best.get("refused")):
            answered += 1
        if verdict == "correct":
            correct += 1
        elif verdict == "wrong" and float(best.get("confidence", 0.0)) >= 0.75:
            confident_wrong += 1
    return {"total": total, "answered": answered, "correct": correct,
            "confident_wrong": confident_wrong}


def write_store_eval(summary: dict[str, Any], path: Path = STORE_EVAL) -> dict[str, Any]:
    """Emit the artifact the honest cockpit reads. answered_pct = % answered CORRECTLY;
    halluc_pct = % CONFIDENTLY wrong (the sacred floor metric). Gate = >=75 / <10."""
    total = int(summary.get("total", 0) or 0)
    correct = int(summary.get("correct", 0) or 0)
    confident_wrong = int(summary.get("confident_wrong", 0) or 0)
    payload = {
        "answered_pct": round(correct / total * 100) if total else 0,
        "halluc_pct": round(confident_wrong / total * 100, 1) if total else 0.0,
        "n": total,
        "correct": correct,
        "answered": int(summary.get("answered", 0) or 0),
        "confident_wrong": confident_wrong,
        "gate_met": bool(total and (correct / total) >= 0.75 and (confident_wrong / total) < 0.10),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotations", default="data/phone_captures/live/ground_truth.json")
    parser.add_argument("--store", required=True)
    parser.add_argument("--append", action="store_true")
    parser.add_argument("--question", default="")
    parser.add_argument("--true-answer", default="")
    parser.add_argument("--when", default="")
    parser.add_argument("--reasoner", choices=("heuristic", "local-ollama", "frontier"),
                        default="frontier")
    parser.add_argument("--model", default="gemma3:12b-it-qat")
    parser.add_argument("--host", default="http://127.0.0.1:11434")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    annotations_path = Path(args.annotations)
    if args.append:
        if not args.question or not args.true_answer:
            raise SystemExit("--append requires --question and --true-answer")
        append_annotation(annotations_path, args.question, args.true_answer, args.when or None)
        print(f"appended annotation to {annotations_path}")
        return 0

    annotations = load_annotations(annotations_path)
    store = TraceMemoryStore(args.store)
    try:
        results = score_annotations(annotations, store, reasoner=args.reasoner,
                                    model=args.model, host=args.host, repeats=max(1, args.repeats))
    finally:
        store.close()

    summary = summarize(results)
    payload = write_store_eval(summary)
    print(json.dumps(payload, indent=2))
    for row in results:
        attempt = row["attempts"][0]
        print(f"- {row['question']} => {attempt.get('answer')} "
              f"[{attempt['verdict']}, refused={attempt.get('refused')}, "
              f"conf={attempt.get('confidence')}]")
    if args.out:
        Path(args.out).write_text(
            json.dumps({"summary": payload, "results": results}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
