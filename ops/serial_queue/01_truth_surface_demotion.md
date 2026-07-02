# SERIAL TASK 01 — Truth Surface Demotion

Worker: Codex or a careful implementation model under Chief review.
Status: ACTIVE.
Must finish and validate before Task 02 begins.

## Goal
Kill fake readiness bars as decision signals. The founder cockpit must stop presenting
`overall_progress`, `project_plan` percentages, or `pitch_progress.percent` as product readiness.

## Input Context
- `ops/cockpit/founder_dash.html`
- `scripts/cockpit_ask_server.py`
- `scripts/cockpit_updater.py`
- `scripts/agent_orchestrator.py`
- `ops/cockpit/project_plan.json`
- `ops/cockpit/pitch_progress.json`
- `evaluation/ras/store_eval.json`
- `evaluation/ras/live44_summary.json`

## Exact Directive
Implement the following, and nothing broader:

1. In the founder dashboard, remove the founder-facing “Overall progress” framing that reads as
   product completeness.
2. Replace it with an explicit “Reality Gates” section driven only by measured artifacts:
   - `evaluation/ras/store_eval.json`
   - `evaluation/ras/live44_summary.json`
   - if missing, show `UNMEASURED`
3. Keep ops counters such as node count and daemon liveness, but label them as ops telemetry, not
   readiness.
4. Any remaining use of `project_plan.progress`, `pitch_progress.percent`, or `overall_progress`
   must be visually labeled `OPS ONLY` or equivalent language that cannot be mistaken for product
   readiness.
5. Do not invent new scores.
6. Do not touch the demo cache or answer engine.

## Validation Metric
The task is only complete if ALL of these are true:

1. `rg -n "Overall progress|overall_progress" ops/cockpit/founder_dash.html scripts/cockpit_ask_server.py`
   shows no founder-facing readiness headline that still represents a percent-complete product claim.
2. `rg -n "UNMEASURED|Reality Gates|OPS ONLY" ops/cockpit/founder_dash.html scripts/cockpit_ask_server.py`
   shows the new truth framing is present.
3. `.venv/bin/pytest -q tests/test_cockpit_rich.py tests/test_trace_brain_server.py`
   passes.
4. If the page is served locally, `/dash.json` still loads and the dashboard still renders.

## Output
Write a short result note to `ops/CODEX_BRIEF_01_truth_surface_demotion_RESULT.md` with:
- what changed
- what metric sources now drive the page
- the exact validation commands and their outcomes
