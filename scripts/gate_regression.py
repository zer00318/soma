#!/usr/bin/env python3
"""Gate-isolated regression harness for the ask_home grounding gate.

WHY THIS EXISTS (2026-06-22): two grounding-gate cracks surfaced on the live
tokyo_walk shatter test. The fixes live in ask_home's STRUCTURAL gate
(`structural_grounding`) — the deterministic, post-draft gate the assembler
actually runs (the live path goes assembler -> structural_grounding, NOT the
legacy verify_grounded/GATE_PROMPT). To prove a gate edit does NOT raise
hallucination on the held-out clips, we must compare OLD-gate vs NEW-gate on the
*same* answers — otherwise gemma's sampling noise (even at temp 0, across reloads)
muddies the delta.

So this harness splits the pipeline at the gate:

  capture : run the FULL ask_home.ask for every question with `structural_grounding`
            monkeypatched to a pass-through recorder. That yields the exact PRE-GATE
            draft the real gate sees, plus whether the question even reached the gate
            (audio/spatial/structured-recall questions never do, so the gate edit
            cannot affect them). Drafts are cached to JSONL. This is the only step
            that calls the answer model. gemma runs at temperature 0, so the cache is
            stable; capture once, grade many times.

  grade   : for each cached draft, re-apply the CURRENT `structural_grounding`
            (reached_gate questions) or pass the raw answer through (others), then
            grade against the frozen gold (held-out clips) or the answer/refuse
            expectation (live banks). A judge cache keyed by (i, final_answer) means
            only answers that actually CHANGED between runs get re-judged.

Protocol:
  1. `capture` each clip ONCE.
  2. `grade --label before` BEFORE editing the gate  -> baseline hallucination.
  3. edit `structural_grounding` in scripts/ask_home.py.
  4. `grade --label after`  AFTER editing            -> reuses the same draft cache.
  5. confirm hallucination(after) <= hallucination(before) on every clip.

Held-out usage:
  scripts/gate_regression.py capture --clip walk \
      --questions evaluation/ras/walk_outside_20260614.txt \
      --memory data/walks/walk_outside_20260614/memory/world_memory.json \
      --model gemma3:27b-it-qat --cache /tmp/gate_reg/walk.drafts.jsonl
  scripts/gate_regression.py grade --clip walk \
      --questions evaluation/ras/walk_outside_20260614.txt \
      --gold evaluation/ras/walk_outside_20260614.gold.json \
      --cache /tmp/gate_reg/walk.drafts.jsonl --judge-model gemma3:27b-it-qat \
      --label before --out /tmp/gate_reg/walk.before.json

Live-bank usage (tokyo_walk moment; gold is the answer/refuse expectation):
  scripts/gate_regression.py capture --clip tokyo_core \
      --questions live:core \
      --memory data/phone_captures/tokyo_walk/kf_memory.json \
      --model gemma3:27b-it-qat --cache /tmp/gate_reg/tokyo_core.drafts.jsonl
  scripts/gate_regression.py grade --clip tokyo_core --questions live:core \
      --gold live:core --cache /tmp/gate_reg/tokyo_core.drafts.jsonl \
      --label before --out /tmp/gate_reg/tokyo_core.before.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "evaluation"))

import ask_home  # noqa: E402
import auto_score as A  # noqa: E402

# Live banks mirror scripts/ask_live.py exactly (kept in sync by hand; these are the
# canonical tokyo_walk core + shatter expectations). expect in {"answer","refuse"}.
LIVE_BANKS = {
    "core": [
        ("I just took this walk. Describe the kind of place I was walking through.", "answer"),
        ("Did I pass any stores? Name the ones you are sure about.", "answer"),
        ("Did I see anywhere to sing karaoke?", "answer"),
        ("Was it daytime or night, and how do you know?", "answer"),
        ("What was the name of the person who walked past me at the first crosswalk?", "refuse"),
        ("What did anyone say to me out loud during this walk?", "refuse"),
        ("What is the exact street address or GPS coordinate where I was walking?", "refuse"),
    ],
    "shatter": [
        ("What breed was the dog I passed on the walk?", "refuse"),
        ("What did the sign at the train station platform say?", "refuse"),
        ("How many red cars did I pass, exactly?", "refuse"),
        ("Which of my friends was walking next to me?", "refuse"),
        ("What was I shopping for on this trip?", "refuse"),
        ("What was the weather forecast for tomorrow shown on the screens?", "refuse"),
        ("Was the street crowded or empty?", "answer"),
        ("Did I walk past a karaoke place before or after the bright arcade?", "answer"),
    ],
}

_CATEGORIES = ("objects", "people", "places", "text", "events", "fusion", "other")


def _load_questions(spec: str) -> list[dict]:
    """Return [{category, question, expect?}]. `spec` is a .txt path OR 'live:<bank>'."""
    if spec.startswith("live:"):
        bank = spec.split(":", 1)[1]
        return [{"category": "live", "question": q, "expect": e}
                for q, e in LIVE_BANKS[bank]]
    out: list[dict] = []
    for raw in Path(spec).read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        category = "other"
        head, sep, tail = line.partition(":")
        if sep and head.strip().lower() in _CATEGORIES:
            category, line = head.strip().lower(), tail.strip()
        out.append({"category": category, "question": line})
    return out


# --------------------------------------------------------------------------- #
# capture — record pre-gate drafts (the only step that runs the answer model).
# --------------------------------------------------------------------------- #
def cmd_capture(args: argparse.Namespace) -> int:
    questions = _load_questions(args.questions)
    cache = Path(args.cache)
    cache.parent.mkdir(parents=True, exist_ok=True)

    done: dict[int, dict] = {}
    if cache.exists():
        for line in cache.read_text().splitlines():
            line = line.strip()
            if line:
                r = json.loads(line)
                done[int(r["i"])] = r
        print(f"resuming capture: {len(done)}/{len(questions)} cached", flush=True)

    real_gate = ask_home.structural_grounding
    rec: dict = {}

    def _recorder(question, draft, memory_path):
        # Record the exact (question, draft, memory_path) the real gate would see,
        # then pass through so ask() returns the raw pre-gate draft unchanged.
        rec["question"] = question
        rec["draft"] = draft
        rec["memory_path"] = memory_path
        return ("assert", draft)

    try:
        ask_home.structural_grounding = _recorder
        with cache.open("a") as fh:
            for i, q in enumerate(questions, 1):
                if i in done:
                    continue
                rec.clear()
                t0 = time.time()
                try:
                    res = ask_home.ask(q["question"], args.memory,
                                       model=args.model, timeout=args.timeout)
                    answer = res.get("answer", "")
                    reached = "draft" in rec
                    raw = rec.get("draft", answer) if reached else answer
                except Exception as exc:  # never lose the battery to one crash
                    answer, raw, reached = f"[CAPTURE ERROR: {exc}]", "", False
                dt = round(time.time() - t0, 1)
                row = {"i": i, "question": q["question"],
                       "category": q.get("category", "other"),
                       "expect": q.get("expect"), "reached_gate": reached,
                       "raw_answer": raw, "memory": args.memory, "latency_s": dt}
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                fh.flush()
                tag = "GATE " if reached else "direct"
                print(f"[{i}/{len(questions)}] ({dt:5.1f}s {tag}) {q['question'][:54]}\n"
                      f"      draft: {raw[:120]!r}", flush=True)
    finally:
        ask_home.structural_grounding = real_gate
    print("capture complete", flush=True)
    return 0


# --------------------------------------------------------------------------- #
# grade — apply the CURRENT gate over cached drafts, then judge vs gold/expect.
# --------------------------------------------------------------------------- #
def _tally(rows: list[dict]) -> dict:
    c = sum(1 for r in rows if r["verdict"] == "correct")
    w = sum(1 for r in rows if r["verdict"] == "wrong")
    m = sum(1 for r in rows if r["verdict"] == "miss")
    err = sum(1 for r in rows if r["verdict"] in A.UNRESOLVED_VERDICTS)
    hard = [r for r in rows if not r.get("pending") and r["verdict"] in A.FINAL_VERDICTS]
    hc = sum(1 for r in hard if r["verdict"] == "correct")
    hw = sum(1 for r in hard if r["verdict"] == "wrong")
    n = len(hard) or 1
    answered = hc + hw
    return {"n": len(rows), "correct": c, "wrong": w, "miss": m, "unresolved": err,
            "hard_ras": round((hc - hw) / n * 100, 1),
            "halluc": hw, "halluc_pct": round(hw / answered * 100, 1) if answered else 0.0}


def _grade_live(answer: str, expect: str) -> tuple[str, str]:
    """Score against an answer/refuse expectation (ask_live.py semantics).
    refuse-Q: correct iff refused, else WRONG (a hallucination).
    answer-Q: correct iff not refused, else MISS (over-refusal, never a halluc)."""
    refused = ask_home._is_refusal(answer) or not (answer or "").strip()
    if expect == "refuse":
        return ("correct" if refused else "wrong", "live_refuse")
    return ("miss" if refused else "correct", "live_answer")


def cmd_grade(args: argparse.Namespace) -> int:
    cache_rows = {}
    for line in Path(args.cache).read_text().splitlines():
        line = line.strip()
        if line:
            r = json.loads(line)
            cache_rows[int(r["i"])] = r

    live = args.gold.startswith("live:")
    gold = {} if live else json.loads(Path(args.gold).read_text())["items"]

    jcache_path = Path(args.judge_cache) if args.judge_cache else None
    jcache = {}
    if jcache_path and jcache_path.exists():
        jcache = json.loads(jcache_path.read_text())

    rows: list[dict] = []
    for i in sorted(cache_rows):
        cr = cache_rows[i]
        raw = cr["raw_answer"]
        mem = cr["memory"]
        # Re-apply the CURRENT structural gate to the cached pre-gate draft. Questions
        # that never reached the gate keep their answer verbatim (the edit can't touch them).
        if cr.get("reached_gate"):
            try:
                _verdict, final = ask_home.structural_grounding(cr["question"], raw, mem)
            except Exception as exc:
                _verdict, final = "assert", f"[GATE ERROR: {exc}]"
        else:
            final = raw

        if live:
            verdict, method = _grade_live(final, cr.get("expect"))
            grading = {"method": method}
            pending = False
        else:
            g = gold.get(str(i), {})
            pending = bool(g.get("founder_pending"))
            jkey = f"{i}|{final}"
            if g.get("unanswerable"):
                verdict = "correct" if A._is_refusal(final) else "wrong"
                grading = {"method": "structural_unanswerable"}
            elif pending:
                verdict = A._best_guess_pending(final, g.get("accept", []), g.get("reject", []))
                grading = {"method": "structural_pending_best_guess"}
            elif jkey in jcache:
                verdict, grading = jcache[jkey]["verdict"], jcache[jkey]["grading"]
            else:
                dec = A.grade_answer(cr["question"], g.get("gold", ""),
                                     g.get("accept", []), g.get("reject", []),
                                     final, args.judge_model)
                verdict, grading = dec.verdict, dec.metadata()
                if jkey is not None and verdict in A.FINAL_VERDICTS:
                    jcache[jkey] = {"verdict": verdict, "grading": grading}
        rows.append({"i": i, "question": cr["question"], "answer": final,
                     "reached_gate": cr.get("reached_gate"), "verdict": verdict,
                     "pending": pending, "grading": grading})
        flip = "" if not cr.get("reached_gate") or final == raw else "  <gate changed>"
        print(f"[{i:2d}] {verdict:9s} {cr['question'][:50]}{flip}", flush=True)

    if jcache_path:
        jcache_path.parent.mkdir(parents=True, exist_ok=True)
        jcache_path.write_text(json.dumps(jcache, ensure_ascii=False, indent=2))

    t = _tally(rows)
    out = {"clip": args.clip, "label": args.label, "gold": args.gold, "tally": t,
           "rows": rows}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\n=== {args.clip} [{args.label}] === correct={t['correct']} wrong={t['wrong']} "
          f"miss={t['miss']} unresolved={t['unresolved']}  hard_ras={t['hard_ras']:+.1f}  "
          f"HALLUC={t['halluc']} ({t['halluc_pct']:.1f}%)", flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    cap = sub.add_parser("capture")
    cap.add_argument("--clip", required=True)
    cap.add_argument("--questions", required=True)
    cap.add_argument("--memory", required=True)
    cap.add_argument("--model", default="gemma3:27b-it-qat")
    cap.add_argument("--timeout", type=int, default=300)
    cap.add_argument("--cache", required=True)
    cap.set_defaults(func=cmd_capture)

    gr = sub.add_parser("grade")
    gr.add_argument("--clip", required=True)
    gr.add_argument("--questions", required=True)  # kept for symmetry / provenance
    gr.add_argument("--gold", required=True)       # .gold.json OR live:<bank>
    gr.add_argument("--cache", required=True)
    gr.add_argument("--judge-model", default="gemma3:27b-it-qat")
    gr.add_argument("--judge-cache", default=None)
    gr.add_argument("--label", required=True)      # before | after
    gr.add_argument("--out", required=True)
    gr.set_defaults(func=cmd_grade)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
