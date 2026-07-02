# S9 / TASK 09 — FRONTIER DEMO NUMBER
*SERIAL. Do not start 10 until this artifact exists and is read by a human.*

## GOAL
Turn the current capture into the only number that matters: a measured frontier score on the
actual bedroom founder questions.

## INPUT CONTEXT
- `scripts/run_frontier_room_cycle.sh`
- `scripts/probe_bedroom_coverage.py`
- `evaluation/annotate_live.py`
- `evaluation/ras/store_eval_frontier.json`
- `data/phone_captures/live/ground_truth.json`

## EXACT DIRECTIVE
1. Run the full frontier room cycle end to end.
2. Write the score artifact to `evaluation/ras/store_eval_frontier.json`.
3. Stop and classify the misses BEFORE making any new code changes:
   - `capture missing`
   - `perception/reading miss`
   - `retrieval/conflict`
   - `counting`
4. Name the single dominant class by question count.

## VALIDATION METRIC
- `evaluation/ras/store_eval_frontier.json` exists and contains:
  `answered_pct`, `halluc_pct`, `n`, `correct`, `confident_wrong`.
- The miss classification references the real per-question detail in the artifact.
- No code is changed during this task.
