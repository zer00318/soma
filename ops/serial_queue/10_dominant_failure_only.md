# S10 / TASK 10 — PATCH ONLY THE DOMINANT FAILURE CLASS
*SERIAL. One class only. No adjacent fixes.*

## GOAL
Avoid another tunnel-vision sprawl. After S9, patch exactly one failure class and re-measure.

## INPUT CONTEXT
- latest `evaluation/ras/store_eval_frontier.json`
- latest `scripts/probe_bedroom_coverage.py` output
- `src/trace_memory/brain/agent.py`
- `scripts/light_ingest.py`
- `scripts/ingest_session.py`
- `scripts/build_demo_store.py`
- whichever single code path matches the dominant class

## EXACT DIRECTIVE
1. Pick ONE class only:
   - capture/dwell
   - perception/reading
   - retrieval/conflict
   - counting
2. Make the smallest patch that can move that class materially on the demo corpus.
3. Re-run S9 immediately after the patch.
4. If the new number worsens, revert the patch and mark the class as a dead end.

## VALIDATION METRIC
- The follow-up frontier artifact improves the chosen class without worsening `halluc_pct`.
- If the artifact regresses, the patch is reverted in the same cycle.
- No second failure class is touched in the same task.
