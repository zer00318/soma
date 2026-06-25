#!/usr/bin/env python3
"""Single source of truth for the pitch-prototype progress the cockpit renders.

The Chief updates milestone states here as the sprint advances; the cockpit
(`scripts/ops_cockpit.py` -> `pitch_progress.json`) shows the bar + checklist so
the founder can always answer "are we actually progressing?".

Edit MILESTONES below (state: done | now | todo), then run:
    .venv/bin/python scripts/pitch_progress.py
to recompute the percent and rewrite ops/cockpit/pitch_progress.json.

A milestone may be set to one specific state "now" (the active task). Percent =
done / total, rounded.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

HEADLINE = "Lean live TRACE app + on-device brain"

# (id, label, state, note)
MILESTONES = [
    ("build",      "Native app builds & signs for iPhone 17",            "done", ""),
    ("deploy",     "App installed, trusted & launching on device",       "done", ""),
    ("brain",      "Mac brain live + over-refusal fixed & verified",     "done", "gemma3:27b on :8765; answers what it saw, refuses what it didn't"),
    ("strip3d",    "Cut dead 3D world + record-then-process shell",      "done", "-187KB; @main -> lean ContentView"),
    ("helpers",    "Live helpers ON (YOLO+OCR+classify+VLM)",            "done", ""),
    ("leanui",     "Lean live POV UI + in-app Ask box",                  "done", "builds; installed & launching"),
    ("feed",       "Live world feed (Brave POV walk) playing",           "done", "Shibuya Tokyo POV walk in dedicated Brave window"),
    ("livespine",  "Live spine: POV window -> local VLM -> brain",       "done", "trace_live_feed.py: gemma3:12b per-frame, 0 raw media, real timeline in brain"),
    ("askbox",     "End-to-end: ask -> cited answer / honest refusal",   "done", "live Tokyo walk: 6/7, RAS 85.7, 0 hallucination, cited; open-ended 'describe' over-refuses"),
    ("prototype",  "Pitch prototype surface (4-beat demo page)",         "done", "served at brain :8765/  — live perception stream + 0-raw-media proof panel + ask-anything + market quadrant, bound to real data"),
    ("liveperc",   "Phone on-device stream lands in brain",              "now",  "Mac spine proves loop end-to-end; phone native app still must POST to brain :8765"),
    ("frontier",   "Frontier fallback wired & verified",                 "now",  "wiring verified (refusal->fallback path fires, fails gracefully); key returns HTTP 401 -> needs a valid ANTHROPIC_API_KEY"),
    ("rehearse",   "End-to-end demo rehearsed + 0-raw-media proof",      "now",  "script written (ops/PITCH_DEMO_SCRIPT.md) + loop run end-to-end w/ 0-raw-media proof; needs timed spoken run-through"),
]

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "ops", "cockpit", "pitch_progress.json")


def build() -> dict:
    done = sum(1 for _, _, s, _ in MILESTONES if s == "done")
    total = len(MILESTONES)
    return {
        "headline": HEADLINE,
        "percent": round(done * 100 / total) if total else 0,
        "done": done,
        "total": total,
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "milestones": [
            {"id": i, "label": l, "state": s, "note": n}
            for i, l, s, n in MILESTONES
        ],
    }


def main() -> int:
    state = build()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(state, f, indent=2)
    print(f"pitch progress {state['percent']}%  ({state['done']}/{state['total']})  -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
