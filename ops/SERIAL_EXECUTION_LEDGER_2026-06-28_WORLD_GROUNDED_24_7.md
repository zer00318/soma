# SERIAL EXECUTION LEDGER — WORLD-GROUNDED 24/7 OVERHAUL

## Objective
Run the local stack and Codex in a strict serial lane until the world-grounded one-room
demo path is architecture-complete and the measured bedroom score improves honestly.

## Serial law
- One task at a time.
- Each task writes an artifact.
- Each artifact is validated before the next task starts.
- Real code edits happen only after fixtures, synthetic proofs, and the latest measured
  eval all point at the same dominant failure.

## Queue
### WG01 — Fixture Manifest
- Input:
  `data/phone_captures/bedroom_kf40`
- Work:
  build recorded-frame manifest plus synthetic binder and brain seed fixtures
- Command:
  `.venv/bin/python scripts/build_world_grounded_fixtures.py`
- Validation:
  `.venv/bin/python scripts/validate_world_grounded_fixtures.py --stage manifest`

### WG02 — Helper Outputs From Recorded Frames
- Input:
  `ops/fixtures/world_grounded/recorded_frames_manifest.json`
- Work:
  run local helper perception over the selected recorded frames and export canonical helper outputs
- Command:
  local `scripts/light_ingest.py` over the selected room frames, then `scripts/export_world_store.py`
- Validation:
  `.venv/bin/python scripts/validate_world_grounded_fixtures.py --stage helper`

### WG03 — Synthetic Binder Outputs
- Input:
  `ops/fixtures/world_grounded/sample_binder_inputs.json`
- Work:
  build synthetic canonical helper observations, run the sleep binder, export authored memories
- Command:
  `.venv/bin/python scripts/build_synthetic_world_store.py --fresh`
- Validation:
  `.venv/bin/python scripts/validate_world_grounded_fixtures.py --stage binder`

### WG04 — Synthetic Brain Outputs
- Input:
  `ops/fixtures/world_grounded/sample_brain_questions.json`
- Work:
  run the production brain over the synthetic binder store and export evidence chains
- Command:
  `.venv/bin/python scripts/run_world_brain_fixture.py`
- Validation:
  `.venv/bin/python scripts/validate_world_grounded_fixtures.py --stage brain`

### WG05 — Architecture Test Gate
- Input:
  canonical store, binder, and brain code
- Work:
  run the structural + binder + brain unit slice
- Command:
  `.venv/bin/pytest tests/unit/test_store.py tests/unit/test_sleep.py tests/unit/test_agent.py tests/unit/test_world_grounded_memory.py -q`
- Validation:
  all green

### WG06 — Real Bedroom Eval
- Input:
  `data/phone_captures/bedroom_dense_353f`, `bedroom_kf40`, frontier key
- Work:
  run keyframe select -> canonical ingest -> sleep bind -> bedroom eval artifact
- Command:
  `./scripts/run_frontier_room_cycle.sh`
- Validation:
  `evaluation/ras/store_eval_frontier.json` exists with real measured keys

### WG07 — Dominant Failure Report
- Input:
  latest eval artifact + fixture outputs
- Work:
  local critic writes one dominant failure report
- Validation:
  `ops/serial_runtime/world_overhaul/dominant_failure_report.md` exists

### WG08 — Dominant Failure Patch
- Input:
  latest report + measured artifacts + fixture artifacts
- Work:
  Codex patches only the dominant miss class and updates tests
- Command:
  `./scripts/run_codex_brief.sh ops/serial_queue/world_overhaul/WG08_dominant_failure_patch.md`
- Validation:
  patch result note exists and targeted tests pass

### WG09 — Re-measure
- Input:
  patched code
- Work:
  rerun WG05 and WG06
- Validation:
  eval artifact is updated; improvement or honest no-improvement is recorded

## Loop law
- WG06 -> WG07 -> WG08 -> WG09 repeats until:
  - `gate_met` is true, or
  - the latest patch does not improve the measured artifact, or
  - the supervisor hits the configured loop cap and stops honestly.
