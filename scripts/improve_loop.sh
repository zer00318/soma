#!/bin/bash
# Self-chaining LOCAL-LLM improvement loop. Runs entirely on local compute (MLX Qwen2.5-VL
# for dense vision + ollama gemma for the brain). ZERO Claude tokens. Logs each step to the
# cockpit flight recorder so the founder can watch on :8799/ops. Bounded: does one full pass
# (dense-caption day + walk -> re-measure the 44 on the enriched memory) then exits cleanly,
# so it never thrashes the box. The Chief wakes occasionally to read the result + add the
# next capability.
#
# Launch (detached, survives the session):
#   PYTHONUNBUFFERED=1 nohup caffeinate -is bash scripts/improve_loop.sh > /tmp/improve_loop.log 2>&1 & disown
set -u
cd /Users/zer00/Documents/VLM
PY=.venv/bin/python
log(){ "$PY" scripts/clog.py "$1" "$2" >/dev/null 2>&1 || true; }

DAY_FR=data/walks/day_in_life_20260618/work/run_frames
WALK_FR=data/walks/walk_outside_20260614/work/run_frames
DAY_DENSE=data/walks/day_in_life_20260618_dense/memory/kf_memory.json
WALK_DENSE=data/walks/walk_outside_20260614_dense/memory/kf_memory.json

echo "[improve_loop] start $(date)"
log run "Improvement loop: dense-captioning the DAY clip on local MLX-VL (resumes from checkpoint)."
"$PY" scripts/build_keyframe_memory.py --frames-dir "$DAY_FR" --out "$DAY_DENSE" --dense >> /tmp/dense_caption.log 2>&1
DAYN=$("$PY" -c "import json;print(len(json.load(open('$DAY_DENSE'))))" 2>/dev/null || echo '?')
log done "DAY dense memory built ($DAYN frames). Richer people/devices/held/surfaces detail."
echo "[improve_loop] day dense done ($DAYN) $(date)"

log run "Improvement loop: dense-captioning the WALK clip on local MLX-VL."
"$PY" scripts/build_keyframe_memory.py --frames-dir "$WALK_FR" --out "$WALK_DENSE" --dense >> /tmp/dense_caption_walk.log 2>&1
WALKN=$("$PY" -c "import json;print(len(json.load(open('$WALK_DENSE'))))" 2>/dev/null || echo '?')
log done "WALK dense memory built ($WALKN frames)."
echo "[improve_loop] walk dense done ($WALKN) $(date)"

log eval "Re-measuring the 44 questions on the DENSE memories (local gemma3:12b)."
DAY_MEM="$DAY_DENSE" WALK_MEM="$WALK_DENSE" \
  CEILING_OUT=evaluation/ras/dense_run.json CEILING_STATUS=ops/cockpit/eval_dense.json \
  ANSWER_MODEL=gemma3:12b-it-qat "$PY" evaluation/run_ceiling.py >> /tmp/dense_remeasure.log 2>&1
RES=$("$PY" -c "import json;d=json.load(open('ops/cockpit/eval_dense.json'));print(f\"{d.get('correct')}c/{d.get('wrong')}w/{d.get('miss')}m  {d.get('correct_pc')}%correct  {d.get('halluc_pc')}%halluc\")" 2>/dev/null || echo 'see eval_dense.json')
log done "DENSE re-measure complete: $RES  (vs ceiling 45.5%/4.8%). MEASURED on the enriched capture."
log note "Improvement loop finished one full pass. Chief: read evaluation/ras/dense_run.json, spot-check, then add the next capability (binder wire-in / heading)."
echo "[improve_loop] DONE $(date) :: $RES"
