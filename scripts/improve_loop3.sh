#!/bin/bash
# Improvement loop pass-3: ENTITY-CENTRIC (BOUND) capture — the phone-grade format. Builds
# entity_capture.json (persons + their own attributes + text_objects, bound at capture) over
# the existing frames, ALONGSIDE the base kf_memory (OCR+captions = the 45.5% config), then
# re-measures the 44. Tests whether BOUND richness beats base AND the dense-prose that
# confabulated. Local compute only. Bounded -> exits clean. Logs to the cockpit.
#   PYTHONUNBUFFERED=1 nohup caffeinate -is bash scripts/improve_loop3.sh > /tmp/improve_loop3.log 2>&1 & disown
set -u
cd /Users/zer00/Documents/VLM
PY=.venv/bin/python
log(){ "$PY" scripts/clog.py "$1" "$2" >/dev/null 2>&1 || true; }

DAY_FR=data/walks/day_in_life_20260618/work/run_frames
WALK_FR=data/walks/walk_outside_20260614/work/run_frames
DAY_E=data/walks/day_in_life_20260618_entity/memory
WALK_E=data/walks/walk_outside_20260614_entity/memory
mkdir -p "$DAY_E" "$WALK_E"
cp data/walks/day_in_life_20260618/memory/kf_memory.json  "$DAY_E/kf_memory.json"
cp data/walks/walk_outside_20260614/memory/kf_memory.json "$WALK_E/kf_memory.json"

echo "[loop3] start $(date)"
log run "Pass-3: entity-centric BOUND capture (persons+attributes+text) on DAY frames — the phone-grade format."
"$PY" scripts/build_entity_capture.py --frames-dir "$DAY_FR"  --out "$DAY_E/entity_capture.json"  >> /tmp/improve_loop3.log 2>&1
log run "Pass-3: entity-centric BOUND capture on WALK frames."
"$PY" scripts/build_entity_capture.py --frames-dir "$WALK_FR" --out "$WALK_E/entity_capture.json" >> /tmp/improve_loop3.log 2>&1
log done "Entity-bound captures built (base OCR/captions + bound persons/attributes per frame)."

log eval "Re-measuring the 44 on the ENTITY-BOUND memories (local gemma3:12b)."
DAY_MEM="$DAY_E/kf_memory.json" WALK_MEM="$WALK_E/kf_memory.json" \
  CEILING_OUT=evaluation/ras/entity_run.json CEILING_STATUS=ops/cockpit/eval_entity.json \
  ANSWER_MODEL=gemma3:12b-it-qat "$PY" evaluation/run_ceiling.py >> /tmp/improve_loop3.log 2>&1
RES=$("$PY" -c "import json;d=json.load(open('ops/cockpit/eval_entity.json'));print(f\"{d.get('correct')}c/{d.get('wrong')}w/{d.get('miss')}m  {d.get('correct_pc')}%correct  {d.get('halluc_pc')}%halluc\")" 2>/dev/null || echo 'see eval_entity.json')
log done "ENTITY-BOUND re-measure: $RES  (base 45.5/4.8 · dense 43.2/13.6). Does BOUND richness beat prose?"
echo "[loop3] DONE $(date) :: $RES"
