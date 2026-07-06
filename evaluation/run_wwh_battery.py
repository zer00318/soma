#!/usr/bin/env python3
"""P34 — the WWH battery: is the brain still dumb? Measured, never vibes.

The founder authors questions BLIND (without looking at the store) about his
real day: what was playing, what was queued, which site was X on, what was
where relative to what, what changed. This harness runs every question through
the live brain and writes one artifact with answer + badge + receipts per
question, plus a scoring sheet the founder fills with correct / wrong /
acceptable-refusal. Scores are computed from HIS sheet — the system never
grades itself on relational understanding.

Battery file (founder-authored): evaluation/wwh_battery.jsonl, one per line:
  {"id": "w01", "q": "what was I watching on youtube yesterday evening?",
   "family": "state-play", "note": "optional gold hint for later scoring"}
Families: state-play · container (which site/app/room) · position (where in
the sidebar/on the desk) · relation (next to / in the queue) · change (what
changed) · time (when did X).

Run:      .venv/bin/python evaluation/run_wwh_battery.py
Score:    founder edits verdicts in the produced *_scored.jsonl
Tally:    .venv/bin/python evaluation/run_wwh_battery.py --tally <scored file>
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BATTERY = ROOT / "evaluation" / "wwh_battery.jsonl"
OUT_DIR = ROOT / "evaluation" / "wwh_runs"
HUB = "http://127.0.0.1:8765"


def ask(question: str) -> dict:
    url = f"{HUB}/ask?q={urllib.parse.quote(question)}"
    t0 = time.monotonic()
    with urllib.request.urlopen(url, timeout=300) as resp:
        d = json.load(resp)
    d["latency_s"] = round(time.monotonic() - t0, 2)
    return d


def run() -> int:
    if not BATTERY.exists():
        print(f"NO BATTERY YET: author {BATTERY} first (founder, blind). "
              "Template line:")
        print('  {"id": "w01", "q": "what was I watching on youtube last night?", '
              '"family": "state-play"}')
        return 1
    questions = [json.loads(l) for l in BATTERY.read_text().splitlines() if l.strip()]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = OUT_DIR / f"wwh_{stamp}_scored.jsonl"
    rows = []
    for q in questions:
        try:
            a = ask(q["q"])
        except Exception as exc:  # noqa: BLE001
            a = {"answer": f"HARNESS ERROR: {exc}", "badge": "error",
                 "confidence": 0, "mode": "-", "evidence": [], "latency_s": -1}
        row = {
            "id": q["id"], "family": q.get("family", "?"), "q": q["q"],
            "answer": a.get("answer"), "badge": a.get("badge"),
            "confidence": a.get("confidence"), "mode": a.get("mode"),
            "latency_s": a.get("latency_s"),
            "receipts": [e.get("text", "")[:120] for e in (a.get("evidence") or [])[:4]],
            "verdict": "TODO(correct|wrong|refusal-ok|refusal-bad)",
        }
        rows.append(row)
        print(f"[{q['id']}] {a.get('badge')}@{a.get('confidence')} "
              f"{a.get('latency_s')}s :: {str(a.get('answer'))[:90]}")
    with out.open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    print(f"\nscoring sheet: {out}\nFounder: replace each verdict TODO, then: "
          f"run_wwh_battery.py --tally {out.name}")
    return 0


def tally(name: str) -> int:
    path = OUT_DIR / name if not Path(name).exists() else Path(name)
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    todo = [r for r in rows if str(r["verdict"]).startswith("TODO")]
    if todo:
        print(f"{len(todo)} verdicts still TODO — founder scores first.")
        return 1
    by_family: dict = {}
    for r in rows:
        f = by_family.setdefault(r["family"], {"n": 0, "correct": 0, "wrong": 0,
                                               "refusal_ok": 0, "refusal_bad": 0,
                                               "confident_wrong": 0})
        f["n"] += 1
        v = r["verdict"]
        if v == "correct":
            f["correct"] += 1
        elif v == "wrong":
            f["wrong"] += 1
            if (r.get("confidence") or 0) >= 0.7:
                f["confident_wrong"] += 1
        elif v == "refusal-ok":
            f["refusal_ok"] += 1
        elif v == "refusal-bad":
            f["refusal_bad"] += 1
    total = sum(f["n"] for f in by_family.values())
    correct = sum(f["correct"] for f in by_family.values())
    cw = sum(f["confident_wrong"] for f in by_family.values())
    print(f"WWH: {correct}/{total} correct · CONFIDENT-WRONG {cw}")
    for fam, f in sorted(by_family.items()):
        print(f"  {fam:12s} {f['correct']}/{f['n']} correct, "
              f"{f['refusal_ok']} honest refusals, {f['wrong']} wrong")
    return 0 if cw == 0 else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tally", default=None)
    args = ap.parse_args()
    sys.exit(tally(args.tally) if args.tally else run())
