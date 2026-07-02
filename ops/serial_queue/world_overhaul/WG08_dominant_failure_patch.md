# WG08 — Dominant Failure Patch Only

You are Codex working inside `/Users/zer00/Documents/VLM`.

## Mission
Read the latest measured artifacts and patch exactly one dominant failure class in the
world-grounded one-room demo path. Do not spread across multiple theories.

## Required context
- `evaluation/ras/store_eval_frontier.json`
- `ops/fixtures/world_grounded/helper_outputs.json`
- `ops/fixtures/world_grounded/binder_outputs.json`
- `ops/fixtures/world_grounded/brain_outputs.json`
- `src/trace_memory/store/`
- `src/trace_memory/brain/agent.py`
- `scripts/light_ingest.py`
- `tests/unit/test_world_grounded_memory.py`

## Hard laws
- Patch only the dominant measured miss class.
- Do not weaken the refusal gate to inflate answered percentage.
- Do not revert the world-grounded contract back to pose-only metadata.
- Do not run the OOM accurate binder at scale.
- Keep raw helper observations immutable.
- Add or update tests for the exact failure you patch.
- Re-run the smallest test slice that proves your patch before finishing.

## Deliverable
1. Implement the bounded patch.
2. Update/add tests.
3. Write `ops/serial_runtime/world_overhaul/last_patch_result.md` with:
   - dominant failure chosen
   - files changed
   - tests run
   - residual risk
