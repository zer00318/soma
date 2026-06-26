# CODEX BRIEF 09 — CP6 pipeline: score the honest number on a REAL captured events.db

Branch: `codex/09-real-number`. Python via `.venv/bin/python`. Additive. Do NOT touch
`trace-native-fastvlm/` or `src/trace_memory/domain/`. Builds on briefs 01/03/04/05.

## Why
The number today (brief 05) is on hand-built fixtures. When the founder does a live device capture, we must
turn it into a scored number with one command — no manual fiddling. Build that pipeline now so CP6 is one
step the moment a real events.db exists.

## Tasks
1. `evaluation/score_real_capture.py <events_db_or_moment_id> <gold.json>`: loads a REAL events.db (or the
   live moment's), runs each gold question through the event-log answer path, and produces the same
   correct% / hallucination% (95% Wilson CI) report + per-item table, writing
   `evaluation/results/real_<moment>.json` and `.md`.
2. `evaluation/gold/real_gold_template.json`: a documented template (with 6 example items spanning answer /
   read / count / refuse / OCR-only-refuse) the founder fills in after a capture.
3. A one-paragraph `evaluation/HOW_TO_GET_THE_NUMBER.md`: the exact steps — capture on device with
   TRACE_EVENTLOG=1, freeze gold from what was actually in the scene, run score_real_capture.py.

## Acceptance (`tests/test_score_real_capture.py`)
- Given a fixture events.db + a small gold file, `score_real_capture.py` writes both result files with a
  correct% and hallucination% each carrying a 95% CI.
- A planted expect=refuse item that gets asserted is counted as a HALLUCINATION.

## Guardrails
- Additive; offline; `pytest tests/ -q` passes. Commit on branch. Report the example run's number.
