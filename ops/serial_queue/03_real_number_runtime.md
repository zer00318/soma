# SERIAL TASK 03 — Real Number Runtime

Worker: local host runtime, not Codex sandbox.
Status: ACTIVE AFTER TASK 02.
This is the first overnight grind task.

## Goal
Produce the only number the cockpit is allowed to trust: the measured unified-store score from the
production agent.

## Input Context
- `evaluation/annotate_live.py`
- `evaluation/ras/store_eval.json`
- `data/phone_captures/live/ground_truth.json`
- `data/trace_store.sqlite3`
- `scripts/cockpit_ask_server.py`
- `ops/cockpit/cockpit_state.json`

## Exact Directive
Run the production eval against the unified live store. Do not use fixture-only scene evals, demo
cache, or planner percentages.

Primary command:
```bash
.venv/bin/python evaluation/annotate_live.py \
  --store data/trace_store.sqlite3 \
  --annotations data/phone_captures/live/ground_truth.json \
  --reasoner local-ollama \
  --repeats 1
```

If `ANTHROPIC_API_KEY` is intentionally configured for demo-day evaluation, rerun with:
```bash
.venv/bin/python evaluation/annotate_live.py \
  --store data/trace_store.sqlite3 \
  --annotations data/phone_captures/live/ground_truth.json \
  --reasoner frontier \
  --repeats 3
```

## Validation Metric
The task is only complete if ALL of these are true:

1. `evaluation/ras/store_eval.json` exists and contains:
   - `answered_pct`
   - `halluc_pct`
   - `n`
2. `n >= 10`.
3. Re-running the same command does not drift by more than 1 answered point unless the store itself changed.
4. The cockpit truth surface reads this artifact instead of any synthetic progress value.

## Output
Append a dated note to `ops/SPRINT_HANDOFF.md` with:
- command used
- exact JSON result
- whether the gate `answered >= 75 and halluc < 10` was met
- if not met, the top 3 failure modes observed
