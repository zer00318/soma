#!/usr/bin/env python3
"""CEILING run — the FAIR diagnostic the live44 floor can't give.

live44 captured OCR+speech only (no live VLM captions, too slow on this Mac), so vision/scene
questions were forced to REFUSE -> an artificially low floor. This runs the SAME founder questions
against the caption-RICH offline memories (which DO have scene captions), to measure what the product
can answer WHEN IT HAS ITS EYES (the real phone capability). The gap floor->ceiling = how much of the
low score is "no vision on this Mac" (recoverable on the phone) vs a real brain/capture failure.

Scoring uses the founder's own accept/reject cues (deterministic, no LLM judge):
  refusal -> MISS ; a reject cue present -> WRONG (hallucination) ; an accept cue present -> CORRECT ;
  answered but neither -> MISS (conservative: not credited, not counted a lie).

Resumable (writes after each Q). Local ollama. Run: PYTHONPATH=scripts python3 evaluation/run_ceiling.py
"""
import json, os, re, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import ask_home  # noqa: E402

CLIPS = {
    "day":  (Path(os.environ.get("DAY_MEM", ROOT / "data/walks/day_in_life_20260618/memory/kf_memory.json")),
             ROOT / "evaluation/ras/day_in_life_20260618.gold.json"),
    "walk": (Path(os.environ.get("WALK_MEM", ROOT / "data/walks/walk_outside_20260614/memory/kf_memory.json")),
             ROOT / "evaluation/ras/walk_outside_20260614.gold.json"),
}
OUT = Path(os.environ.get("CEILING_OUT", ROOT / "evaluation/ras/ceiling_run.json"))
STATUS = Path(os.environ.get("CEILING_STATUS", ROOT / "ops/cockpit/eval_ceiling.json"))
MODEL = os.environ.get("ANSWER_MODEL", "gemma3:12b-it-qat")

_REFUSE = re.compile(r"\b(don'?t have|didn'?t see|did not see|no record|not in (my )?memory|can'?t|"
                     r"cannot|unable|no information|don'?t know|couldn'?t|i did not|i didn't see|"
                     r"not sure|no .{0,12}(record|memory|sign|mention))\b", re.I)
def refused(ans: str) -> bool:
    try:
        if getattr(ask_home, "_looks_unsure", None) and ask_home._looks_unsure(ans):
            return True
    except Exception:
        pass
    return bool(_REFUSE.search(ans or ""))

def score(ans: str, item: dict) -> str:
    low = (ans or "").lower()
    if refused(ans):
        return "MISS"
    for r in item.get("reject", []) or []:
        if str(r).lower() in low:
            return "WRONG"
    for a in item.get("accept", []) or []:
        if str(a).lower() in low:
            return "CORRECT"
    return "MISS"

def main() -> int:
    done = {}
    if OUT.exists():
        try:
            done = {r["key"]: r for r in json.load(open(OUT))}
        except Exception:
            done = {}
    results = list(done.values())
    tasks = []
    for clip, (mem, gold) in CLIPS.items():
        items = json.load(open(gold)).get("items", {})
        for qid, item in items.items():
            tasks.append((f"{clip}:{qid}", clip, str(mem), item))
    for key, clip, mem, item in tasks:
        if key in done:
            continue
        q = item.get("q", "")
        t0 = time.time()
        try:
            r = ask_home.ask(q, mem, model=MODEL)
            ans = r.get("answer", "") if isinstance(r, dict) else str(r)
        except Exception as e:
            ans = f"[ERROR {e}]"
        v = score(ans, item)
        results.append({"key": key, "clip": clip, "q": q, "gold": item.get("gold", ""),
                        "channel": item.get("channel", ""), "ans": ans, "verdict": v,
                        "secs": round(time.time() - t0, 1)})
        results.sort(key=lambda r: r["key"])
        json.dump(results, open(OUT, "w"), ensure_ascii=False, indent=2)
        # live status for the cockpit
        c = sum(r["verdict"] == "CORRECT" for r in results)
        w = sum(r["verdict"] == "WRONG" for r in results)
        m = sum(r["verdict"] == "MISS" for r in results)
        json.dump({"state": "running", "done": len(results), "total": len(tasks),
                   "correct": c, "wrong": w, "miss": m, "model": MODEL,
                   "what": "CEILING: same questions vs caption-rich memory (vision ON)"},
                  open(STATUS, "w"))
        print(f"[{len(results)}/{len(tasks)}] {key} {v} ({results[-1]['secs']}s) :: {q[:50]}", flush=True)

    c = sum(r["verdict"] == "CORRECT" for r in results)
    w = sum(r["verdict"] == "WRONG" for r in results)
    m = sum(r["verdict"] == "MISS" for r in results)
    n = len(results); answered = c + w
    summary = {"state": "complete", "n": n, "correct": c, "wrong": w, "miss": m,
               "correct_pc": round(100 * c / n, 1) if n else 0,
               "halluc_pc": round(100 * w / answered, 1) if answered else 0,
               "model": MODEL, "memory": "caption-rich offline (vision ON) — the CEILING",
               "scoring": "founder accept/reject cues (deterministic)"}
    json.dump(summary, open(STATUS, "w"))
    print("\n=== CEILING SUMMARY ===\n" + json.dumps(summary, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
