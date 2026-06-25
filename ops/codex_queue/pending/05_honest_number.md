# CODEX BRIEF 05 — the honest number (correct% / hallucination% with CIs)

Branch: `codex/05-honest-number`. Python via `.venv/bin/python`. Additive; do NOT touch
`trace-native-fastvlm/` or `src/trace_memory/domain/`. Builds on briefs 01–04.

## Why
We need a real, repeatable number — the pitch gate — not vibes. Extend the eval harness (brief 02:
`evaluation/run_scene_eval.py`, `evaluation/gold/scene_gold.json`) to score the FULL event-log answer path
(object-grounded + binder + two-zone) and report confidence intervals.

## Tasks
1. Grow `evaluation/gold/scene_gold.json` to >=30 items across: present-object answers, label/flavour reads,
   counts (incl. duplicate-instance via spatial anchor), absent-thing refusals (rings/pesto/tortilla), and
   OCR-only-term refusals (nutella). Build the matching fixture `events.db`(s) the items reference (script it).
2. Make `evaluation/run_scene_eval.py` call the event-log answer path (the same code `/ask` uses with
   TRACE_EVENTLOG=1) and classify each: correct / wrong / HALLUCINATION (asserting on an expect=refuse item).
3. Report: N, correct %, hallucination %, and **95% Wilson confidence intervals** for both; per-item table;
   write a machine-readable `evaluation/results/scene_eval_latest.json` and a short markdown summary
   `evaluation/results/scene_eval_latest.md`.

## Acceptance (`tests/test_scene_eval_number.py`)
- The eval runs end-to-end on the fixtures and writes both result files.
- correct% and hallucination% each have a reported 95% CI (lo, hi).
- A planted expect=refuse item that the answer path asserts is counted as a HALLUCINATION (regression guard).

## Guardrails
- Additive; `pytest tests/ -q` must pass. Offline (no network needed for the eval). Commit on branch. Report
  the final correct% / hallucination% with CIs in your summary.
