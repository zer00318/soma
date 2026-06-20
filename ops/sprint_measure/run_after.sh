#!/bin/bash
# Sprint AFTER-measurement: current tree (entity-resolution + guard + leak-fixed prompt).
# Sequential (one GPU), independent judge (answer=12b / judge=27b, matches 06-19 baseline),
# OLLAMA_MAX_LOADED_MODELS=1 to cap peak memory at ~18GB (avoids the 06-20 co-resident OOM).
# Resumable checkpoints in /tmp; honest status to ops/sprint_measure/after_*.json.
cd /Users/zer00/Documents/VLM || exit 1
export OLLAMA_MAX_LOADED_MODELS=1
PY=.venv/bin/python
run() {
  clip=$1; qs=$2; gold=$3; mem=$4; ck=$5; st=$6
  echo "=== $(date '+%H:%M:%S') START $clip ==="
  rm -f "$ck"
  "$PY" evaluation/run_live.py --questions "$qs" --gold "$gold" --memory "$mem" \
    --answer-model gemma3:12b-it-qat --judge-model gemma3:27b-it-qat \
    --checkpoint "$ck" --status "$st"
  echo "=== $(date '+%H:%M:%S') DONE $clip rc=$? ==="
}
run cold evaluation/ras/day_in_life_20260618.txt evaluation/ras/day_in_life_20260618.gold.json \
    data/walks/day_in_life_20260618/memory/world_memory.json /tmp/after_cold.jsonl ops/sprint_measure/after_cold.json
run walk evaluation/ras/walk_outside_20260614.txt evaluation/ras/walk_outside_20260614.gold.json \
    data/walks/walk_outside_20260614/memory/world_memory.json /tmp/after_walk.jsonl ops/sprint_measure/after_walk.json
echo "=== $(date '+%H:%M:%S') ALL DONE ==="
