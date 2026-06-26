# CODEX BRIEF 08 — CP5 de-risk: full event-log loop integration test

Branch: `codex/08-e2e`. Python via `.venv/bin/python`. Additive. Do NOT touch `trace-native-fastvlm/`
or `src/trace_memory/domain/`. Exercises the whole brain path end to end so the live device run can't be
the first time it's tried together.

## Why
Persistence (01), binder (03), two-zone (04), pose anchors (07) each have unit tests, but the FULL loop —
capture packets -> append to events.db -> bind -> two-zone honest answer / refuse — has never been tested
as one flow. De-risk CP5 before the device run.

## Tasks
1. `tests/test_eventlog_e2e.py`: simulate a realistic capture session by POSTing/append-ing a sequence of
   perception packets (objects across 2 poses + OCR labels + an absent thing only in OCR), into a temp
   events.db via the same code path `/capture/perception` uses with `TRACE_EVENTLOG=1`.
2. Then run the same answer path `/ask` uses, and assert a full mini-battery:
   - a present object → answered + cited + has personal_evidence
   - a duplicate object across 2 poses → count == 2 (binder + pose anchors working together)
   - a flavour/label read → answered, with a fenced world_context
   - an absent thing (rings/pesto) → REFUSED
   - an OCR-only term (nutella) → REFUSED
   - persistence: after a SECOND unrelated capture, the first scene's answers still work (no overwrite)
3. Add `evaluation/run_eventlog_e2e.py` (a runnable script printing the same battery as a human-readable
   table) so it can be demoed quickly.

## Acceptance
- The e2e test passes; `evaluation/run_eventlog_e2e.py` prints the battery with PASS/FAIL per item.
- `.venv/bin/python -m pytest tests/ -q` passes.

## Guardrails
- Additive; commit on branch (driver commits). Report the battery results table.
