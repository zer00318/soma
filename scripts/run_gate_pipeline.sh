#!/bin/bash
# Full BEFORE pipeline on the CURRENT (pre-fix) gate: capture pre-gate drafts for all
# four clips, then grade each with the current structural_grounding. Resumable (capture
# skips cached questions; judge cache skips re-judged answers). Run START-TO-FINISH
# BEFORE editing ask_home.py so the baseline reflects the old gate.
set -u
cd /Users/zer00/Documents/VLM || exit 1
export OLLAMA_MAX_LOADED_MODELS=1
PY=.venv/bin/python
OUT=/tmp/gate_reg
mkdir -p "$OUT"
M=gemma3:27b-it-qat

cap() { # name questions memory
  echo "=== $(date '+%H:%M:%S') CAPTURE $1 ==="
  "$PY" scripts/gate_regression.py capture --clip "$1" --questions "$2" --memory "$3" \
    --model "$M" --cache "$OUT/$1.drafts.jsonl"
}
grade() { # name questions gold
  echo "=== $(date '+%H:%M:%S') GRADE(before) $1 ==="
  "$PY" scripts/gate_regression.py grade --clip "$1" --questions "$2" --gold "$3" \
    --cache "$OUT/$1.drafts.jsonl" --judge-model "$M" \
    --judge-cache "$OUT/$1.judge.json" --label before --out "$OUT/$1.before.json"
}

cap walk evaluation/ras/walk_outside_20260614.txt data/walks/walk_outside_20260614/memory/world_memory.json
cap day  evaluation/ras/day_in_life_20260618.txt  data/walks/day_in_life_20260618/memory/world_memory.json
cap tokyo_core    live:core    data/phone_captures/tokyo_walk/kf_memory.json
cap tokyo_shatter live:shatter data/phone_captures/tokyo_walk/kf_memory.json

grade walk          evaluation/ras/walk_outside_20260614.txt evaluation/ras/walk_outside_20260614.gold.json
grade day           evaluation/ras/day_in_life_20260618.txt  evaluation/ras/day_in_life_20260618.gold.json
grade tokyo_core    live:core    live:core
grade tokyo_shatter live:shatter live:shatter

echo "=== $(date '+%H:%M:%S') BEFORE PIPELINE DONE ==="
