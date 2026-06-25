# CODEX BRIEF — wire persistent event-log memory + object-grounded answering into the live brain

You are working in /Users/zer00/Documents/VLM. Do this on a branch:
`git checkout -b feat/eventlog-persistence-and-binding`. Run Python with `.venv/bin/python`.
Keep changes ADDITIVE and behind a flag; do NOT break the existing live path.

## Why
The live brain (`scripts/trace_brain_server.py` → `scripts/ask_home.py`) stores captures in a FLAT
file `data/phone_captures/<moment>/kf_memory.json` that is a rolling buffer — it gets OVERWRITTEN as
the camera moves and reset on every brain restart, so earlier moments are LOST. Also, questions ground
on raw OCR substrings, so "how many nutella jars" answers from the OCR word "nutella" even when there
is no nutella OBJECT.

A clean, tested capture core already EXISTS but is NOT wired in: `src/trace_memory/`
- `adapters/sqlite_eventlog.py` → `SqliteEventLog(path)` with `.append(Observation)`, `.observations()`, `.close()` (append-only, persistent, immutable).
- `domain/observation.py` → typed `Observation(kind, subject, attributes, t_ms, spatial_anchor, confidence, provenance, refutation_cue)` and `Attribute(name, value)`; `domain/confidence.py`, `domain/provenance.py`.
- `application/recall.py` → `Recall.execute(query, memory_reference)`; `application/grounding_gate.py`; `application/binder.py`; `domain/query.py`.
- Tests already exist under `tests/` (test_grounded_recall.py, test_memory_provenance.py, test_structured_recall.py, …). READ them to learn the real API before coding. Do not change the domain dataclasses.

## PHASE 1 — Persistence (no more overwrite). Do this first; verify before Phase 2.
1. In `scripts/trace_brain_server.py`, gate new behavior behind env `TRACE_EVENTLOG=1` (default off → existing path unchanged).
2. When `TRACE_EVENTLOG=1`, in the `_capture` handler (the `/capture/perception` path) ALSO append each
   committed perception to a persistent `SqliteEventLog` at `data/phone_captures/<moment>/events.db`:
   - Parse the phone's derived text lines. A line `OBJECT | <subject> | <attrs…>` →
     `Observation(kind="object", subject=<subject>, attributes=(Attribute("detail", <attrs>),), source_channel="vlm", …)`.
     An OCR string → `Observation(kind="text", subject="text surface", attributes=(Attribute("text", <ocr>),), source_channel="ocr", …)`.
   - Set `t_ms`/provenance.captured_at_ms from the record time; confidence from any certainty token (else a medium default). Look at `tests/test_memory_provenance.py` for how to build these objects correctly.
   - APPEND ONLY. Never delete/overwrite. The DB must survive a brain restart and accumulate across captures.
3. Leave the existing `kf_memory.json` write in place (additive) so nothing regresses.

### Phase 1 acceptance (must pass — add as `tests/test_live_eventlog_persistence.py`):
- Append observations for "scene A" (subjects: water bottle, pringles), then "scene B" (subjects: stairs, window) to the SAME `events.db`. Reopen the log (simulate restart) → `.observations()` returns BOTH scenes' objects (A not overwritten).

## PHASE 2 — Object-grounded answering (fixes "nutella jars"). Only after Phase 1 passes.
4. Add a recall/answer path the brain uses when `TRACE_EVENTLOG=1`: answer a question from the event-log
   Observations, and GROUND ON OBJECTS:
   - For existence/count/attribute questions ("how many X", "is there X", "what colour is X"), the subject X
     must be the `subject` of at least one `kind=="object"` Observation (allow simple singular/plural + a small
     synonym set). If X appears ONLY in `kind=="text"` (OCR) observations and in NO object subject → REFUSE
     with the honest-refusal string, do NOT answer from OCR text alone.
   - Reuse `application/grounding_gate.py` / `application/recall.py` if they already express this; otherwise
     implement the object-subject check as a thin function. Prefer reusing existing code.

### Phase 2 acceptance (add as `tests/test_object_grounded_refusal.py`):
- Memory has object subjects {water bottle, pringles can} and OCR text containing the word "nutella"
  (no nutella object). Then:
  - "how many nutella jars" → REFUSE (nutella is not an object subject).
  - "is there a water bottle" / "how many water bottles" → ANSWER (water bottle IS an object subject).
  - "what flavour is the pringles" → still answerable (pringles is an object subject; flavour from its attrs/ocr).

## Guardrails (hard)
- Additive + flagged (`TRACE_EVENTLOG`); existing path with the flag OFF must behave EXACTLY as before.
- Append-only; never delete or mutate observations.
- Do NOT modify the domain dataclasses in `src/trace_memory/domain/`.
- `.venv/bin/python -m pytest tests/ -q` must pass (existing + your 2 new tests). Run it and paste the summary.
- Keep functions small; reuse `src/trace_memory` rather than reimplementing. No changes to `trace-native-fastvlm/`.
- Commit on the branch (do NOT push). Output: a summary of what changed + the pytest summary + the 2 new tests' results.

When done, STOP and report. The reviewer (me) will read the diff and the test output before anything goes live.
