#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from trace_memory.brain import TraceMemoryAgent  # noqa: E402
from trace_memory.store import TraceMemoryStore  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", default="ops/fixtures/world_grounded/synthetic_binder_store.sqlite3")
    parser.add_argument("--questions", default="ops/fixtures/world_grounded/sample_brain_questions.json")
    parser.add_argument("--out", default="ops/fixtures/world_grounded/brain_outputs.json")
    parser.add_argument("--reasoner", default="heuristic", choices=("heuristic", "local-ollama", "frontier"))
    args = parser.parse_args()

    questions = json.loads(Path(args.questions).read_text()).get("questions") or []
    store = TraceMemoryStore(args.store)
    try:
        agent = TraceMemoryAgent(store, reasoner=args.reasoner)
        rows = []
        for question_row in questions:
            answer = agent.answer(str(question_row["question"]))
            rows.append(
                {
                    "question": question_row["question"],
                    "answer": answer.answer,
                    "refused": answer.refused,
                    "confidence": answer.confidence,
                    "reasoner": args.reasoner,
                    "evidence_chain": list(answer.evidence_chain),
                    "expect_subject": question_row.get("expect_subject"),
                    "expect_words": question_row.get("expect_words") or [],
                }
            )
    finally:
        store.close()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote brain fixture answers to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
