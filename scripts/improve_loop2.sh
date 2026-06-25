#!/bin/bash
# Improvement loop, pass 2: MERGE base captions+OCR with the dense detail (per frame), then
# re-measure the 44 on the merged memory. Local compute only (ollama gemma). Zero Claude tokens.
# Bounded -> exits cleanly. Logs to the cockpit flight recorder.
#   PYTHONUNBUFFERED=1 nohup caffeinate -is bash scripts/improve_loop2.sh > /tmp/improve_loop2.log 2>&1 & disown
set -u
cd /Users/zer00/Documents/VLM
PY=.venv/bin/python
log(){ "$PY" scripts/clog.py "$1" "$2" >/dev/null 2>&1 || true; }

DAY_BASE=data/walks/day_in_life_20260618/memory/kf_memory.json
WALK_BASE=data/walks/walk_outside_20260614/memory/kf_memory.json
DAY_DENSE=data/walks/day_in_life_20260618_dense/memory/kf_memory.json
WALK_DENSE=data/walks/walk_outside_20260614_dense/memory/kf_memory.json
DAY_MERGE=data/walks/day_in_life_20260618_merge/memory/kf_memory.json
WALK_MERGE=data/walks/walk_outside_20260614_merge/memory/kf_memory.json

echo "[loop2] start $(date)"
log run "Improvement loop pass-2: merging base captions+OCR with dense detail (per frame)."
"$PY" scripts/merge_memory.py "$DAY_BASE"  "$DAY_DENSE"  "$DAY_MERGE"  >> /tmp/improve_loop2.log 2>&1
"$PY" scripts/merge_memory.py "$WALK_BASE" "$WALK_DENSE" "$WALK_MERGE" >> /tmp/improve_loop2.log 2>&1
log done "Merged memories built (base OCR kept + dense detail folded in)."

log eval "Re-measuring the 44 on the MERGED memories (local gemma3:12b)."
DAY_MEM="$DAY_MERGE" WALK_MEM="$WALK_MERGE" \
  CEILING_OUT=evaluation/ras/merge_run.json CEILING_STATUS=ops/cockpit/eval_merge.json \
  ANSWER_MODEL=gemma3:12b-it-qat "$PY" evaluation/run_ceiling.py >> /tmp/improve_loop2.log 2>&1
RES=$("$PY" -c "import json;d=json.load(open('ops/cockpit/eval_merge.json'));print(f\"{d.get('correct')}c/{d.get('wrong')}w/{d.get('miss')}m  {d.get('correct_pc')}%correct  {d.get('halluc_pc')}%halluc\")" 2>/dev/null || echo 'see eval_merge.json')
log done "MERGED re-measure complete: $RES  (base ceiling 45.5%/4.8%; dense 43.2%/13.6%). MEASURED."
echo "[loop2] DONE $(date) :: $RES"
