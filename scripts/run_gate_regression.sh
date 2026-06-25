#!/bin/bash
# Capture pre-gate drafts for all four regression clips, sequentially (one GPU).
# Answer model = gemma3:27b-it-qat to match the live brain. temp 0 -> stable cache.
set -u
cd /Users/zer00/Documents/VLM || exit 1
export OLLAMA_MAX_LOADED_MODELS=1
PY=.venv/bin/python
OUT=/tmp/gate_reg
mkdir -p "$OUT"
M=gemma3:27b-it-qat

cap() {  # name questions memory
  echo "=== $(date '+%H:%M:%S') CAPTURE $1 ==="
  "$PY" scripts/gate_regression.py capture --clip "$1" \
    --questions "$2" --memory "$3" --model "$M" --cache "$OUT/$1.drafts.jsonl"
  echo "=== $(date '+%H:%M:%S') DONE $1 rc=$? ==="
}

cap walk evaluation/ras/walk_outside_20260614.txt \
    data/walks/walk_outside_20260614/memory/world_memory.json
cap day evaluation/ras/day_in_life_20260618.txt \
    data/walks/day_in_life_20260618/memory/world_memory.json
cap tokyo_core live:core data/phone_captures/tokyo_walk/kf_memory.json
cap tokyo_shatter live:shatter data/phone_captures/tokyo_walk/kf_memory.json

echo "=== $(date '+%H:%M:%S') ALL CAPTURES DONE ==="
