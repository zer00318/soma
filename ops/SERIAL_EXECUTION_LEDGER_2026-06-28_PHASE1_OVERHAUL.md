# SERIAL EXECUTION LEDGER — 2026-06-28 PHASE 1 OVERHAUL
*Commander-in-Chief override. Goal: biggest percentage jump before pitch by attacking the
actual lever, not the noisiest code path.*

## EXECUTIVE JUDGMENT
- The biggest increase will NOT come from more specialists, more binders, or more planner math.
- The biggest increase comes from:
  1. locking the pitch to a controlled curated demo,
  2. improving the exact demo capture so the evidence is actually present,
  3. measuring frontier on that corpus,
  4. patching only the dominant measured miss class.

## PHASE 1 — IMMEDIATE TASK LIQUIDATION & PRUNING

### KILLED
- `ops/cockpit/pitch_progress.json` as a readiness signal
- `ops/cockpit/project_plan.json` percentages as readiness
- `ops/cockpit/cockpit_state.json` `overall_progress` as readiness
- all specialist families as pitch drivers:
  `scripts/specialist_*`, `scripts/activity_*`, `scripts/instance_*`
- all "while we're here" binder expansions:
  `world_binder`, `node_merge`, `spatial_relations`, `identity_consensus`

### FROZEN
- general-product work that does not move the bedroom/demo number
- open live prototype claims
- cockpit cosmetics beyond truthful measured surfacing

### ALTERED
- the pitch mode is now `controlled curated demo`
- the judged answer path is `frontier perception -> unified store -> store agent -> measured artifact`
- founder is the real-world capture pipeline; machines prepare, ingest, score, classify, patch

## PHASE 2 — 24/7 SERIAL EXECUTION LEDGER

### S7 — Controlled Demo Lock
- Input Context:
  `ops/PRODUCT_TRUTH_SESSION_2026-06-27.md`, `ops/SOVEREIGN_STATE.md`,
  `ops/cockpit/founder_dash.html`, `scripts/cockpit_ask_server.py`
- Exact Prompt / Directive:
  Use `ops/serial_queue/07_controlled_demo_lock.md`.
- Validation Metric:
  one explicit pitch mode, no founder-facing contradiction.

### S8 — Bedroom Capture Overhaul
- Input Context:
  `scripts/probe_bedroom_coverage.py`, `scripts/run_frontier_room_cycle.sh`,
  `data/phone_captures/bedroom_dense_353f`, `ground_truth.json`
- Exact Prompt / Directive:
  Use `ops/serial_queue/08_bedroom_capture_overhaul.md`.
- Validation Metric:
  machine coverage probe runs and outputs a real gap list.

### S9 — Frontier Demo Number
- Input Context:
  `scripts/run_frontier_room_cycle.sh`, `evaluation/annotate_live.py`,
  `evaluation/ras/store_eval_frontier.json`
- Exact Prompt / Directive:
  Use `ops/serial_queue/09_frontier_demo_number.md`.
- Validation Metric:
  artifact exists and dominant miss class is named from it.

### S10 — Dominant Failure Only
- Input Context:
  latest `store_eval_frontier.json`, latest coverage probe, matching code path only
- Exact Prompt / Directive:
  Use `ops/serial_queue/10_dominant_failure_only.md`.
- Validation Metric:
  next measured artifact improves the chosen class or the patch is reverted.

### S11 — Truth Surface Final
- Input Context:
  `founder_dash.html`, `cockpit_ask_server.py`, best measured artifact
- Exact Prompt / Directive:
  Use `ops/serial_queue/11_truth_surface_final.md`.
- Validation Metric:
  founder sees measured truth only; no fake readiness remains.

## SERIAL LAW
- S7 -> S8 -> S9 -> S10 -> re-S9 -> S11
- No parallel feature hunts.
- No second patch lane before the first re-measure lands.
- No number reaches the founder without an artifact.

## STANDBY COMMAND — FIRST BATCH
```bash
./scripts/run_phase1_serial.sh list
./scripts/run_phase1_serial.sh 07
./scripts/run_phase1_serial.sh 08
./scripts/run_phase1_serial.sh 09
```

## HARD TRUTH
If S8 shows the store still lacks `battery`, `app`, `diary`, `pillow count`, or `jar count`,
then the next highest-ROI action is a founder recapture with a strict dwell checklist. No amount
of sub-agent motion can hallucinate missing evidence into the store without breaking the honesty bar.
