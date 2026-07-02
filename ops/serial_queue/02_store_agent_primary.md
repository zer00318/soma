# SERIAL TASK 02 — Store Agent Primary Path Proof

Worker: Codex or a careful implementation model under Chief review.
Status: ACTIVE AFTER TASK 01.
Must finish and validate before Task 03 begins.

## Goal
Make the unified store agent the unquestioned primary live `/ask` path, and prove when it answered
versus when the system fell back.

## Input Context
- `scripts/trace_brain_server.py`
- `src/trace_memory/brain/agent.py`
- `evaluation/annotate_live.py`
- `tests/test_store_agent_wired.py`
- `tests/test_trace_brain_server.py`
- `tests/unit/test_eval_uses_production_agent.py`

## Exact Directive
Implement the following, and nothing broader:

1. Ensure `/ask` tries the store agent first for grounded answers.
2. Only treat the store path as “wired” when a non-refused store-agent answer actually wins.
3. Preserve honest fallback behavior when retrieval is weak or the store agent refuses.
4. Add or tighten provenance in the returned payload so a successful store answer clearly exposes
   evidence ids / citations from the unified store.
5. Keep source scoping and the honesty floor intact.
6. Do not broaden question coverage by adding brittle heuristics.

## Validation Metric
The task is only complete if ALL of these are true:

1. `.venv/bin/pytest -q tests/test_store_agent_wired.py tests/test_trace_brain_server.py tests/unit/test_eval_uses_production_agent.py`
   passes.
2. `rg -n "source.?=.?.?store_agent|\"store_agent\"" scripts/trace_brain_server.py tests/test_store_agent_wired.py`
   proves the store agent is the explicit winning source on success.
3. `rg -n "reasoner_wired.flag|_touch_store_wired" scripts/trace_brain_server.py`
   shows the wiring flag is still present and tied to the live path.
4. No new hardcoded brand, count, or attribute fast-paths are introduced in `src/trace_memory/brain/agent.py`.

## Output
Write a short result note to `ops/CODEX_BRIEF_02_store_agent_primary_RESULT.md` with:
- what changed in the live path
- when fallback still occurs
- the exact validation commands and their outcomes
