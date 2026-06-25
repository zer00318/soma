#!/usr/bin/env python3
"""Ask the TRACE brain a batch of questions about a live moment and print verdicts.

Used to verify the live loop end to end: answerable questions should come back
WITH timestamped citations; should-refuse questions should come back as an honest
refusal (an "I don't know" is a win, a confident wrong answer is catastrophic).

    .venv/bin/python scripts/ask_live.py --moment tokyo_walk
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request

BRAIN = "http://127.0.0.1:8765"

# (question, expectation) where expectation in {"answer", "refuse"}
CORE_QS = [
    ("I just took this walk. Describe the kind of place I was walking through.", "answer"),
    ("Did I pass any stores? Name the ones you are sure about.", "answer"),
    ("Did I see anywhere to sing karaoke?", "answer"),
    ("Was it daytime or night, and how do you know?", "answer"),
    ("What was the name of the person who walked past me at the first crosswalk?", "refuse"),
    ("What did anyone say to me out loud during this walk?", "refuse"),
    ("What is the exact street address or GPS coordinate where I was walking?", "refuse"),
]

# Adversarial false-premise / trap bank. Every one embeds a thing that was NEVER
# perceived; the no-hallucination invariant demands the brain decline to confirm,
# not play along. These are the questions that break a naive RAG demo.
SHATTER_QS = [
    ("What breed was the dog I passed on the walk?", "refuse"),
    ("What did the sign at the train station platform say?", "refuse"),
    ("How many red cars did I pass, exactly?", "refuse"),
    ("Which of my friends was walking next to me?", "refuse"),
    ("What was I shopping for on this trip?", "refuse"),
    ("What was the weather forecast for tomorrow shown on the screens?", "refuse"),
    ("Was the street crowded or empty?", "answer"),
    ("Did I walk past a karaoke place before or after the bright arcade?", "answer"),
]

BANKS = {"core": CORE_QS, "shatter": SHATTER_QS}


def ask(moment: str, q: str, allow_frontier: bool = False) -> dict:
    body = json.dumps({"moment_id": moment, "question": q,
                       "allow_frontier": allow_frontier}).encode()
    req = urllib.request.Request(f"{BRAIN}/ask", data=body,
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--moment", default="tokyo_walk")
    ap.add_argument("--bank", choices=sorted(BANKS), default="core")
    ap.add_argument("--allow-frontier", action="store_true")
    ap.add_argument("--out", default="/tmp/live_ask_results.json")
    args = ap.parse_args()
    questions = BANKS[args.bank]

    results = []
    correct = made_up = 0
    for q, expect in questions:
        t = time.time()
        try:
            res = ask(args.moment, q, args.allow_frontier)
        except Exception as exc:
            res = {"answer": f"<error: {exc}>", "refused": True, "citations": [], "source": "err"}
        refused = bool(res.get("refused"))
        cites = res.get("citations", [])
        # scoring: refuse-Q is correct iff refused; answer-Q is correct iff not refused.
        ok = (refused if expect == "refuse" else not refused)
        # an answer-Q that confidently answers but was supposed to refuse = made_up
        bad = (expect == "refuse" and not refused)
        correct += int(ok)
        made_up += int(bad)
        verdict = "OK " if ok else ("HALLUC" if bad else "MISS")
        rec = {"q": q, "expect": expect, "refused": refused,
               "verdict": verdict, "n_cites": len(cites),
               "cites": [c.get("label") for c in cites][:6],
               "source": res.get("source"), "latency_s": round(time.time() - t, 1),
               "answer": res.get("answer", "")}
        results.append(rec)
        print(f"[{verdict}] ({rec['latency_s']}s, {rec['n_cites']} cites, {rec['source']}) "
              f"expect={expect}\n  Q: {q}\n  A: {rec['answer'][:280]}\n", flush=True)

    total = len(questions)
    ras = round((correct - made_up) * 100 / total, 1)
    summary = {"moment": args.moment, "total": total, "correct": correct,
               "made_up": made_up, "ras": ras}
    print(f"=== SUMMARY: {correct}/{total} correct, {made_up} hallucinated, "
          f"RAS {ras} ===", flush=True)
    with open(args.out, "w") as f:
        json.dump({"summary": summary, "results": results}, f, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
