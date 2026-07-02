# PHASE 1 AUTOPILOT PLAN — 2026-06-28

## Objective
Run the biggest-lift serial lane for pitch week:

`dense bedroom capture -> keyframe selection -> frontier light ingest -> coverage probe -> measured frontier artifact -> one-class-only patch`

No dead work. No planner percentages. No parallel feature hunts.

## Command Law
1. Lock the pitch to controlled curated demo mode.
2. Improve capture coverage on the exact founder demo corpus.
3. Measure frontier on that corpus.
4. Patch only the dominant measured miss class.

## Execution Architecture

### Stage A — Command Queue
- Source of authority: `ops/SERIAL_EXECUTION_LEDGER_2026-06-28_PHASE1_OVERHAUL.md`
- Active serial tasks:
  - Task 07: controlled demo lock
  - Task 08: bedroom capture overhaul
  - Task 09: frontier demo number
  - Task 10: dominant failure only
  - Task 11: truth surface final

### Stage B — Local-LLM Runtime
- Models:
  - `gemma3:12b-it-qat` for bounded scout summaries
  - `gemma3:27b-it-qat` for critic / next-step concentration
- No LM Studio dependency.
- Codex is used for bounded queue tasks only; measurement stays script-first.

### Stage C — Overnight Grind
- Run `scripts/run_frontier_room_cycle.sh` on the latest dense bedroom capture.
- Read `scripts/probe_bedroom_coverage.py` output first.
- Read `evaluation/ras/store_eval_frontier.json`.
- If the artifact improved:
  - classify the dominant miss class
  - prepare the single next bounded patch
- If coverage is still missing critical facts:
  - stop patching and request a founder recapture with the dwell checklist

### Stage D — Self-Conservation
- Short sleep when the store or eval artifact changed materially.
- Long sleep when nothing moved.
- If another `evaluation/annotate_live.py` run is already in flight, the daemon waits inside its own loop,
  writes `ops/serial_runtime/state.json` with `mode: waiting`, and appends lane-blocked activity until the lane clears.
- Persist state to `ops/serial_runtime/state.json`.
- Append activity to `ops/serial_runtime/activity.jsonl`.
- Mirror daemon stdout/stderr to `ops/serial_runtime/daemon.log`.

### Stage E — Human Review Boundary
- The loop is allowed to measure, summarize, and focus.
- It is not allowed to silently widen scope, start a new feature family, or reopen frozen specialist work.
- It never treats planner bars, fixture-only results, or demo cache behavior as readiness.

## First Live Move
1. Seed checkpoints: old Tasks 01 and 02 remain historical only.
2. Run Task 07, then Task 08, then Task 09 now.
3. Use `scripts/start_serial_chief.sh 09` only to arm a sanctioned current task, never the obsolete daemon loop.
