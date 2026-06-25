#!/usr/bin/env python3
"""Real-brain eval at n=48 against HUMAN founder gold (the first fair number near the n>=50 gate).

Runs the production brain (ask_home.ask_with_understanding: consensus + EXPAND) over the 48 founder-gold
questions for the walk_outside_20260614 capture, scores each honestly:
  - REFUSED  : the brain declined (deterministic refusal detector) on an answerable question -> a miss, not a lie.
  - CORRECT  : answer conveys the gold fact (gemma judge), OR a correct refusal/negative on an unanswerable item.
  - WRONG    : answer conflicts with / misses the gold, or asserts presence the gold says is absent -> the lie.
Hallucination% = WRONG / answered. correct% = CORRECT / total.

Writes incrementally to OUT so a mid-run death is resumable (re-run resumes from the partial).
LLM-judged -> spot-check a sample of verdicts by hand before trusting the aggregate. Needs local ollama.

Run: PYTHONPATH=scripts python3 evaluation/run_founder_gold_brain.py
"""
import json, os, re, sys, time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import ask_home  # noqa: E402

MEM   = str(ROOT / "data/walks/walk_outside_20260614/memory/kf_memory.json")
QFILE = ROOT / "evaluation/ras/posthoc_foundergold.json"          # id -> q, gold
GFILE = ROOT / "evaluation/ras/founder_gold_walk_outside.json"     # id -> answerable, gold
OUT   = ROOT / "evaluation/ras/founder_gold_brain_run.json"
HOST  = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
BRAIN_MODEL = os.environ.get("BRAIN_MODEL", "gemma3:27b-it-qat")   # the production consensus brain
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "gemma3:12b-it-qat")   # faster, only grades answered items

_REFUSE = re.compile(r"\b(don'?t have|didn'?t see|did not see|no record|not in (my )?memory|"
                     r"can'?t|cannot|unable|no information|not sure|don'?t know|couldn'?t find|"
                     r"trouble reaching my memory|reach(?:ing)? my memory just now)\b", re.I)
def refused(ans: str) -> bool:
    fn = getattr(ask_home, "_looks_unsure", None)
    try:
        if fn and fn(ans):
            return True
    except Exception:
        pass
    return bool(_REFUSE.search(ans or ""))

def brain(q: str) -> str:
    fn = getattr(ask_home, "ask_with_understanding", ask_home.ask)
    try:
        r = fn(q, MEM, model=BRAIN_MODEL, timeout=240)
    except TypeError:
        r = fn(q, MEM, model=BRAIN_MODEL)
    return (r or {}).get("answer", "") if isinstance(r, dict) else str(r)

_JUDGE = ("You are a strict grader. Compare the SYSTEM ANSWER to the GOLD answer for the question. "
          "Reply with EXACTLY one word: CORRECT or WRONG.\n"
          "- CORRECT if the system answer conveys the same key fact as the gold (wording may differ).\n"
          "- WRONG if it conflicts with, contradicts, or misses the gold's key fact, or asserts the "
          "presence of something the gold says is absent.\n\nQUESTION: {q}\nGOLD: {gold}\n"
          "SYSTEM ANSWER: {ans}\n\nOne word:")
def judge(q: str, gold: str, ans: str) -> str:
    try:
        out = ask_home._ollama(_JUDGE.format(q=q, gold=gold, ans=ans), JUDGE_MODEL, HOST, 60) or ""
    except Exception as e:
        return "WRONG"  # conservative: an ungradeable answer is not counted correct
    return "CORRECT" if out.strip().upper().startswith("CORRECT") else "WRONG"


def score(q: str, gold: str, answerable: bool, ans: str, prior_verdict: Optional[str] = None) -> str:
    ref = refused(ans)
    if answerable:
        if ref:
            return "REFUSED"
    else:
        if ref:
            return "CORRECT"
    if prior_verdict in {"CORRECT", "WRONG"}:
        return prior_verdict
    return judge(q, gold, ans)

def main() -> int:
    qd = {x["id"]: x for x in json.load(open(QFILE))}
    gd = {x["id"]: x for x in json.load(open(GFILE))}
    ids = sorted(set(qd) & set(gd))
    done = {}
    if OUT.exists():
        try:
            loaded = json.load(open(OUT))
            if isinstance(loaded, list):
                for r in loaded:
                    i = r.get("id")
                    if i not in qd or i not in gd:
                        continue
                    q = qd[i].get("q", "")
                    gold = gd[i].get("gold", qd[i].get("gold", ""))
                    answerable = bool(gd[i].get("answerable", True))
                    fixed = dict(r)
                    fixed["verdict"] = score(q, gold, answerable, fixed.get("ans", ""), fixed.get("verdict"))
                    done[i] = fixed
        except Exception:
            done = {}
    results = [done[i] for i in ids if i in done]
    if results:
        json.dump(results, open(OUT, "w"), ensure_ascii=False, indent=2)
    for i in ids:
        if i in done:
            continue
        q = qd[i].get("q", "")
        gold = gd[i].get("gold", qd[i].get("gold", ""))
        answerable = bool(gd[i].get("answerable", True))
        t0 = time.time()
        ans = brain(q)
        verdict = score(q, gold, answerable, ans)
        rec = {"id": i, "q": q, "gold": gold, "answerable": answerable, "ans": ans,
               "verdict": verdict, "secs": round(time.time() - t0, 1)}
        results.append(rec)
        results.sort(key=lambda r: r["id"])
        json.dump(results, open(OUT, "w"), ensure_ascii=False, indent=2)
        print(f"[{len([r for r in results])}/{len(ids)}] id={i} {verdict} ({rec['secs']}s) :: {q[:54]}", flush=True)

    c = sum(r["verdict"] == "CORRECT" for r in results)
    w = sum(r["verdict"] == "WRONG" for r in results)
    rf = sum(r["verdict"] == "REFUSED" for r in results)
    n = len(results)
    answered = c + w
    correct_pc = round(100 * c / n, 1) if n else 0.0
    halluc_pc = round(100 * w / answered, 1) if answered else 0.0
    summary = {"n": n, "correct": c, "wrong": w, "refused": rf,
               "correct_pc": correct_pc, "halluc_pc": halluc_pc,
               "brain": BRAIN_MODEL, "memory": "walk_outside_20260614 kf (caption+OCR, vision-limited)",
               "gold": "founder gold n=48 (human)", "scoring": "deterministic refusal + gemma judge (spot-check!)"}
    json.dump({"summary": summary, "results": results}, open(str(OUT) + ".final", "w"), ensure_ascii=False, indent=2)
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
