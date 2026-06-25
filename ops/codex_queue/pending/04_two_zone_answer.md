# CODEX BRIEF 04 — two-zone honest answer (personal evidence + fenced world knowledge)

Branch: `codex/04-two-zone`. Python via `.venv/bin/python`. Additive; do NOT touch `trace-native-fastvlm/`
or `src/trace_memory/domain/`. Builds on briefs 01/03.

## Why
The demo "wow" is honesty WITH usefulness: answer what was actually seen (citable, personal), and SEPARATELY
attach world knowledge (fenced, never asserted as personal). `scripts/inject_expand.py` already implements a
world-knowledge EXPAND layer — reuse it; do not reinvent.

## Tasks
1. In the event-log answer path (`src/trace_memory/adapters/live_eventlog.py` answer_question), when a question
   is answered from bound entities, ALSO produce a structured two-zone result:
   `{ "personal_evidence": "<what you saw, with t citations>", "world_context": "<fenced world knowledge>", "answer": "<combined>" }`.
   - personal_evidence: only from bound entities / event-log observations (citable).
   - world_context: call `inject_expand` (or its public function) on the recognized entities to add world
     knowledge (e.g. "Pringles is a brand of stackable potato crisps"); clearly fenced, NEVER a personal claim.
   - If the question is a refusal (subject not an object), still refuse — do NOT world-expand a thing not seen.
2. Surface the two zones in the brain's `/ask` JSON (add `personal_evidence` and `world_context` fields) when
   `TRACE_EVENTLOG=1`. Keep the existing `answer`/`refused`/`source` fields.

## Acceptance (`tests/test_two_zone_answer.py`)
- A question about a seen object returns non-empty `personal_evidence` AND a fenced `world_context`, and the
  combined `answer` does not state world knowledge as something personally observed.
- A refusal (e.g. "how many nutella jars" with nutella only in OCR) returns refused with EMPTY world_context.
- If `inject_expand` is unavailable/offline, world_context is empty but personal_evidence still works (graceful).

## Guardrails
- Additive; `pytest tests/ -q` must pass. Reuse inject_expand; no domain edits. Commit on branch. Report.
