#!/usr/bin/env python3
"""Tiny driver: build screen_memory.json for the walk via Apple Vision OCR.
Uses ocrmac (Neural Engine / CPU), not ollama — safe to run alongside a GPU job."""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import screen_reader as S

KF = os.path.join(ROOT, "data/walks/walk_outside_20260614/memory/kf_memory.json")
kf = json.load(open(KF))
if isinstance(kf, dict):
    kf = kf.get("keyframes") or kf.get("kf") or []
recs = S.build_screen_memory(kf, KF, force=True)
print("screen frames enriched:", len(recs))
for r in recs:
    print("t=%.1f  %s" % (r["t"], r["screen_ocr_txt"][:160]))
