# S11 / TASK 11 — TRUTH SURFACE FINAL
*SERIAL. Only after the real number improves.*

## GOAL
Make the founder-facing cockpit reflect the improved measured artifact and nothing else.

## INPUT CONTEXT
- `ops/cockpit/founder_dash.html`
- `scripts/cockpit_ask_server.py`
- `ops/cockpit/cockpit_state.json`
- latest `evaluation/ras/store_eval.json`
- latest `evaluation/ras/store_eval_frontier.json`

## EXACT DIRECTIVE
1. Keep ops telemetry visible only as internal execution motion.
2. Surface the best current measured bedroom/demo artifact prominently.
3. Remove any stale readiness wording that conflicts with the artifact.
4. Do NOT promote a new number until the artifact exists on disk.

## VALIDATION METRIC
- Founder dash still labels ops motion as internal-only.
- The visible readiness verdict is traceable to the measured artifact on disk.
- No file still presents planner/task percentages as product readiness.
