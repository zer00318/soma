#!/usr/bin/env python3
"""The (A)/(B) diagnosis backbone, automated (ROADMAP s.3).

Every miss must be mechanically diagnosed, not guessed:
  (A) MISSING CHANNEL  — the fact was never captured/derived into ANY channel
                          -> earns a NEW channel/feature (the only thing that does).
  (B) BRAIN            — the fact IS in some stored channel, but the brain didn't
                          reach/bind/reason over it -> a navigation/reasoning fix.

Method: for each gold question, search every stored memory channel (ASR, captions,
OCR, screen, world inventory, attributes, bound graph) for the gold's accept-cues.
If a cue is present somewhere but the engine got it wrong/missed -> (B). If no cue
is present anywhere -> (A). Correct answers are passed through.

This is deliberately blunt (substring presence), so it OVER-counts (B) if anything
(a fact half-present still flags brain). That bias is the safe one: it stops us
inventing channels for facts we already captured (the roadmap's anti-diversion law).

Run:
  .venv/bin/python scripts/diagnose_ab.py \
      --memory-dir data/walks/<slug>/memory \
      --gold evaluation/ras/<slug>.gold.json \
      --scoreboard <checkpoint.jsonl> [--out ops/cockpit/diagnosis.json]
"""
from __future__ import annotations
import argparse, json, os, sys

CHANNELS = ["asr.json", "transcript.txt", "kf_memory.json", "kf_memory.json.ckpt.ndjson",
            "screen_memory.json", "world_memory.json", "attributes.json",
            "bound_memory.json", "audio_events.json", "egomotion_visual.json"]


def _raw(path):
    try:
        return open(path, encoding="utf-8", errors="replace").read().lower()
    except Exception:
        return ""


def _rows(path):
    out = {}
    try:
        for line in open(path, encoding="utf-8", errors="replace"):
            line = line.strip()
            if line:
                r = json.loads(line)
                out[int(r["i"])] = r
    except Exception:
        pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--memory-dir", required=True)
    ap.add_argument("--gold", required=True)
    ap.add_argument("--scoreboard", required=True)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    gold = json.load(open(args.gold))["items"]
    rows = _rows(args.scoreboard)
    chan_text = {c: _raw(os.path.join(args.memory_dir, c)) for c in CHANNELS}
    chan_text = {c: t for c, t in chan_text.items() if t}

    results = []
    for k in sorted(gold, key=lambda x: int(x)):
        g = gold[k]
        i = int(k)
        row = rows.get(i, {})
        verdict = row.get("verdict", "n/a")
        cues = [c.lower() for c in g.get("accept", [])]
        found = {}  # cue -> [channels]
        for cue in cues:
            hits = [c.replace(".json", "").replace("kf_memory.ckpt.ndjson", "kf")
                    for c, t in chan_text.items() if cue in t]
            if hits:
                found[cue] = sorted(set(hits))
        captured = bool(found)

        if verdict == "correct":
            diag = "correct"
        elif verdict in ("wrong", "miss"):
            diag = "(B) brain" if captured else "(A) channel"
        else:
            diag = "?"
        results.append({
            "i": i, "q": g.get("q", ""), "verdict": verdict, "diagnosis": diag,
            "expected_channel": g.get("channel", ""),
            "cues_found_in": found,
            "engine_answer": (row.get("answer", "") or "")[:160],
            "gold": (g.get("gold", "") or "")[:120],
        })

    n = len(results)
    correct = sum(1 for r in results if r["diagnosis"] == "correct")
    a_miss = [r for r in results if r["diagnosis"] == "(A) channel"]
    b_miss = [r for r in results if r["diagnosis"] == "(B) brain"]
    summary = {
        "n": n, "correct": correct,
        "A_missing_channel": len(a_miss), "B_brain": len(b_miss),
        "A_questions": [{"i": r["i"], "q": r["q"], "expected_channel": r["expected_channel"]} for r in a_miss],
        "B_questions": [{"i": r["i"], "q": r["q"], "found_in": r["cues_found_in"]} for r in b_miss],
    }

    print("=" * 78)
    print("(A)/(B) DIAGNOSIS  —  %d Q | %d correct | %d (A) missing-channel | %d (B) brain"
          % (n, correct, len(a_miss), len(b_miss)))
    print("=" * 78)
    for r in results:
        tag = {"correct": "✓", "(A) channel": "A", "(B) brain": "B"}.get(r["diagnosis"], "?")
        print("[%s] Q%-2d %-8s %s" % (tag, r["i"], r["verdict"], r["q"][:60]))
        if r["diagnosis"] == "(B) brain":
            print("        captured in: %s" % json.dumps(r["cues_found_in"], ensure_ascii=False))
        elif r["diagnosis"] == "(A) channel":
            print("        NOT in any channel -> needs: %s" % r["expected_channel"])
    print("-" * 78)
    print("(A) missing-channel -> EARNS a new feature:")
    for r in a_miss:
        print("   Q%-2d %s   [%s]" % (r["i"], r["q"][:58], r["expected_channel"]))
    print("(B) brain -> fix navigation/binding (info already captured):")
    for r in b_miss:
        print("   Q%-2d %s" % (r["i"], r["q"][:58]))

    if args.out:
        json.dump({"summary": summary, "per_question": results},
                  open(args.out, "w"), ensure_ascii=False, indent=2)
        print("\nwrote", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
