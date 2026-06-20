#!/usr/bin/env python3
"""RAS — Retroactive Answerability Score harness.

The product north-star (thesis locked 2026-06-11): the system perceives the
world BEFORE any prompt exists, so arbitrary post-hoc questions must be
answerable. RAS measures exactly that, and punishes hallucination — the
failure mode that kills trust in a memory product.

Protocol:
  1. After a capture day, the founder writes ~25 questions BLIND (without
     reading any logs) — one per line in a text file, optionally prefixed
     with a category: "text: what dates were on the robotics-week flyer".
     Categories: objects, people, places, text, events, fusion.
  2. `ask` runs every question through the real RecallFirewall:
       python3 evaluation/run_ras.py ask --questions evaluation/ras/day1.txt
     → writes day1.answers.json with empty "verdict" fields.
  3. Founder fills each verdict: "correct" (right AND cited), "wrong"
     (confidently incorrect = hallucination), "miss" (honest don't-know).
     Partial answers: judge by what a stranger would walk away believing.
  4. `score` computes the number:
       python3 evaluation/run_ras.py score --answers evaluation/ras/day1.answers.json

  RAS = (correct - wrong) / total * 100        [honest misses are neutral]
  hallucination rate = wrong / answered        [pitch gate: < 5%]
  Pitch target: RAS >= 60 on a stranger-authored battery.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_CATEGORIES = ("objects", "people", "places", "text", "events", "fusion", "other")


def _load_questions(path: Path) -> list[dict]:
    questions: list[dict] = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        category = "other"
        head, sep, tail = line.partition(":")
        if sep and head.strip().lower() in _CATEGORIES:
            category, line = head.strip().lower(), tail.strip()
        questions.append({"category": category, "question": line})
    return questions


def _answer_fn(args):
    """Return (label, fn) where fn(question) -> result dict. Two engines:
    'firewall' = the graph/RecallFirewall stack (default, comms-graph path);
    'ask_home' = the watch-the-walk VLM-memory pipeline (scripts/ask_home.py),
    so the keyframe pipeline is scored on the SAME north-star and schema."""
    if args.engine == "ask_home":
        sys.path.insert(0, str(ROOT / "scripts"))
        import ask_home
        mem = args.memory
        model = args.model

        def fn(question):
            r = ask_home.ask(question, mem, model=model)
            scenes = r.get("scenes") or []
            return {"answer": r.get("answer", ""), "intent": "ask_home",
                    "citations": [s.get("frame") for s in scenes],
                    "confidence": 1.0 if scenes else 0.0}
        return "ask_home", fn

    from soma_hub.crypto import EncryptedTextCodec
    from soma_hub.graph import RelationalMemoryGraph
    from soma_hub.recall import RecallFirewall
    from soma_hub.storage import MemoryStore
    db = Path(args.db)
    codec = EncryptedTextCodec.from_env_or_file(db.parent)
    firewall = RecallFirewall(MemoryStore(db, codec), RelationalMemoryGraph(db, codec))
    return "firewall", firewall.answer


def cmd_ask(args: argparse.Namespace) -> None:
    engine, answer = _answer_fn(args)

    questions = _load_questions(Path(args.questions))
    if not questions:
        sys.exit(f"no questions found in {args.questions}")

    print(f"engine: {engine}")
    rows: list[dict] = []
    for i, q in enumerate(questions, 1):
        t0 = time.time()
        try:
            result = answer(q["question"])
        except Exception as exc:  # an eval harness must never lose the battery to one crash
            result = {"answer": f"[HARNESS ERROR: {exc}]", "intent": "error",
                      "citations": [], "confidence": 0.0}
        elapsed = time.time() - t0
        cites = result.get("citations") or []
        print(f"[{i}/{len(questions)}] ({elapsed:5.1f}s) {q['question']}")
        if cites:
            print(f"      proof: {cites[0]}")
        rows.append({
            "category": q["category"],
            "question": q["question"],
            "answer": result.get("answer", ""),
            "intent": result.get("intent", ""),
            "confidence": result.get("confidence"),
            "citations": len(result.get("citations") or []),
            "latency_s": round(elapsed, 1),
            "verdict": "",
        })

    out = Path(args.out) if args.out else Path(args.questions).with_suffix(".answers.json")
    out.write_text(json.dumps({
        "asked_at": datetime.now(timezone.utc).isoformat(),
        "engine": engine,
        "source": args.memory if engine == "ask_home" else args.db,
        "answers": rows,
    }, indent=2, ensure_ascii=False))
    print(f"\nwrote {out}")
    print('next: fill each "verdict" with correct | wrong | miss, then:')
    print(f"  python3 evaluation/run_ras.py score --answers {out}")


def cmd_score(args: argparse.Namespace) -> None:
    data = json.loads(Path(args.answers).read_text())
    rows = data["answers"]
    unscored = [r for r in rows if r.get("verdict", "") not in ("correct", "wrong", "miss")]
    if unscored:
        for r in unscored:
            print(f"  unscored: {r['question']!r} (verdict={r.get('verdict', '')!r})")
        sys.exit(f"{len(unscored)}/{len(rows)} answers lack a valid verdict — fill them first")

    total = len(rows)
    correct = sum(1 for r in rows if r["verdict"] == "correct")
    wrong = sum(1 for r in rows if r["verdict"] == "wrong")
    miss = sum(1 for r in rows if r["verdict"] == "miss")
    answered = correct + wrong
    ras = (correct - wrong) / total * 100
    halluc = (wrong / answered * 100) if answered else 0.0
    lat = sorted(r["latency_s"] for r in rows)

    print(f"\nRAS battery: {Path(args.answers).name}  ({total} questions)")
    print(f"  correct (cited): {correct}   wrong (hallucinated): {wrong}   honest miss: {miss}")
    print(f"  RAS                = {ras:6.1f}   (pitch gate: >= 60)")
    print(f"  hallucination rate = {halluc:6.1f}%  (pitch gate: < 5%)")
    print(f"  latency median/max = {lat[len(lat)//2]:.1f}s / {lat[-1]:.1f}s")
    print("  by category:")
    for cat in _CATEGORIES:
        sub = [r for r in rows if r["category"] == cat]
        if not sub:
            continue
        c = sum(1 for r in sub if r["verdict"] == "correct")
        w = sum(1 for r in sub if r["verdict"] == "wrong")
        print(f"    {cat:8s} {c}/{len(sub)} correct, {w} hallucinated")
    # one machine-readable line for tracking RAS over time (the pitch curve)
    print(json.dumps({"ras": round(ras, 1), "hallucination_pct": round(halluc, 1),
                      "total": total, "correct": correct, "wrong": wrong, "miss": miss}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    ask = sub.add_parser("ask", help="run a question battery through recall")
    ask.add_argument("--questions", required=True, help="text file, one question per line")
    ask.add_argument("--engine", choices=("firewall", "ask_home"), default="firewall",
                     help="answer engine: firewall (comms graph) or ask_home (watch-the-walk VLM memory)")
    ask.add_argument("--memory", default="data/walks/home_capture_20260613/memory/memory_full.json",
                     help="ask_home engine: path to the scene-memory JSON")
    ask.add_argument("--model", default="gemma3:12b-it-qat", help="ask_home engine: ollama model")
    ask.add_argument("--db", default=str(ROOT / "data" / "soma_hub.sqlite3"))
    ask.add_argument("--out", default=None, help="output scoring sheet (default: <questions>.answers.json)")
    ask.set_defaults(func=cmd_ask)
    score = sub.add_parser("score", help="compute RAS from a filled scoring sheet")
    score.add_argument("--answers", required=True)
    score.set_defaults(func=cmd_score)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
