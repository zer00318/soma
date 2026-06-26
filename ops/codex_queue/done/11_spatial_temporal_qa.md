# CODEX BRIEF 11 — spatial + temporal question answering over the event log

Branch: `codex/11-spatial-temporal`. Python via `.venv/bin/python`. Additive. Do NOT touch
`trace-native-fastvlm/` or `src/trace_memory/domain/`. Builds on briefs 03/07 (binder + pose spatial_anchor).

## Why
Demo questions include "what did I see FIRST / before X", and "where / which side was X" (LEFT/RIGHT).
The event log has `t_ms` (temporal) and `spatial_anchor` (pose buckets from brief 07) — use them.

## Tasks
1. TEMPORAL intent ("what did I see first", "what came before/after X", "in what order"): answer from the
   ordered object observations by t_ms — give the first/ordered subjects with their times. If the asked
   reference X isn't present → refuse.
2. SPATIAL intent ("where was X", "which side was X", "what was to the left/right of X"): use the
   spatial_anchor yaw bucket of X vs other entities to answer relative position ("the cereal box was to the
   left of the water bottle"). Only answer when X is a grounded object AND pose anchors exist; otherwise be
   honest ("I saw X but didn't track exactly where" or refuse if X absent).
3. Keep the honest-refusal default: never invent a direction or an order for an unseen thing.

## Acceptance (`tests/test_spatial_temporal_qa.py`)
- Fixture: object A at t=1000 anchor yaw≈10°, object B at t=3000 anchor yaw≈80°.
  - "what did I see first" → A (with time).
  - "which side was A relative to B" → left/right consistent with the yaw buckets.
  - "where was a zebra" (absent) → refuse.

## Guardrails
- Additive; `pytest tests/ -q` passes. No domain edits. Commit on branch. Report the example answers.
