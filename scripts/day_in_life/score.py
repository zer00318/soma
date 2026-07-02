#!/usr/bin/env python3
"""Day-in-life SCORER — run the founder's blind 19-question gold key against the committed
day-in-life store, through the REAL agent. Reproducible; no clip-specific tuning.

Scoring follows the gold key's own contract:
  - accept = correctness cues (ANY one present, by meaning) -> CORRECT
  - reject = plausible-wrong facts; a confident answer containing one and no accept -> WRONG
  - a refusal is a MISS, never wrong.
RAS = correct / total. Halluc = wrong / total. Prints the honest per-question table + the
same headline the demo shows, and the answers WITH their evidence so you can show your work.

    .venv/bin/python scripts/day_in_life/score.py \
        [--store evaluation/day_in_life/day_in_life.sqlite3] \
        [--model gemma3:27b-it-qat] [--out evaluation/day_in_life/score.json]

Default answerer is 27b: ASK-time is off the real-time budget (Q&A is after-the-moment), so
the strongest local reasoner is the legitimate demo answerer. Pass --model gemma3:12b-it-qat
for the live-tier number.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from trace_memory.brain import TraceMemoryAgent  # noqa: E402
from trace_memory.store import TraceMemoryStore  # noqa: E402

GOLD = ROOT / "evaluation/oag/v2/gold/day_in_life_20260618.json"


def _norm(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def judge(item: dict, answer: str, refused: bool) -> str:
    low = _norm(answer)
    if refused or not low:
        return "miss"
    if any(_norm(cue) in low for cue in item.get("accept", [])):
        return "correct"
    if any(_norm(cue) in low for cue in item.get("reject", [])):
        return "wrong"
    return "miss"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", default=str(ROOT / "evaluation/day_in_life/day_in_life.sqlite3"))
    ap.add_argument("--model", default="gemma3:27b-it-qat")
    ap.add_argument("--out", default=str(ROOT / "evaluation/day_in_life/score.json"))
    args = ap.parse_args()

    if not Path(args.store).exists():
        print(f"! store not found: {args.store}\n  build it first: "
              f".venv/bin/python scripts/day_in_life/perceive.py", flush=True)
        return 2

    gold = json.loads(GOLD.read_text())["items"]
    store = TraceMemoryStore(args.store)
    agent = TraceMemoryAgent(store, reasoner="local-ollama", ollama_model=args.model,
                             restrict_sources=("phone_camera",))

    rows, tally = [], {"correct": 0, "wrong": 0, "miss": 0}
    for qid in sorted(gold, key=int):
        item = gold[qid]
        a = agent.answer(item["q"])
        verdict = judge(item, a.answer, a.refused)
        tally[verdict] += 1
        evidence = [str(r.get("text", ""))[:120] for r in a.evidence_chain[:3]]
        rows.append({"id": qid, "q": item["q"], "answer": a.answer,
                     "confidence": a.confidence, "refused": a.refused,
                     "verdict": verdict, "gold": item["gold"][:80],
                     "channel": item.get("channel"), "evidence": evidence})
        mark = {"correct": "✓", "wrong": "✗ HALLUC", "miss": "· miss"}[verdict]
        print(f"[{mark:9}] Q{qid}: {item['q'][:52]}", flush=True)
        print(f"            -> {a.answer[:100]}", flush=True)

    n = len(gold)
    summary = {
        "model": args.model, "n": n,
        "correct": tally["correct"], "wrong": tally["wrong"], "miss": tally["miss"],
        "RAS_pct": round(100 * tally["correct"] / n, 1),
        "halluc_pct": round(100 * tally["wrong"] / n, 1),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({"summary": summary, "rows": rows}, indent=2,
                                         ensure_ascii=False))
    print("\n=== DAY-IN-LIFE (19 blind Qs) ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"  artifact: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
