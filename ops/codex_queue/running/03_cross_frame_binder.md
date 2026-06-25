# CODEX BRIEF 03 — cross-frame entity binder over the event log

Branch: `codex/03-binder`. Python via `.venv/bin/python`. Additive; do NOT touch `trace-native-fastvlm/`
or `src/trace_memory/domain/`. Builds on brief 01 (`src/trace_memory/adapters/live_eventlog.py`, events.db).

## Why
The same physical object appears in many frames → many `kind="object"` Observations with the same/similar
subject. Today they're counted/listed naively. We need to BIND them into ONE entity so counts and attributes
are right (the "maximum context, bound" goal).

## Tasks
1. Add `src/trace_memory/application/entity_binder.py` with a pure function
   `bind_entities(observations) -> list[BoundEntity]` where `BoundEntity` has: `subject` (canonical),
   `count` (best estimate of distinct real instances — NOT frame count), `attributes` (merged, deduped),
   `first_t_ms`, `last_t_ms`, `frames_seen`, `spatial_anchors` (set), `confidence`.
   - Group object Observations by normalized subject (singular/plural + a small synonym map).
   - **Consensus + spatial de-dup (KEY):** observations of the same subject that share a spatial_anchor
     (pose bucket) and/or fall in a short time window are the SAME instance → do not double-count.
     `count` = number of distinct (subject, spatial_anchor-bucket) groups, floored at 1 for a seen subject;
     if no spatial_anchor info, count stays "1 (at least)" — never inflate to frame count.
   - confidence high if frames_seen large; low if 1-2 (a tiny-VLM ghost).
2. Wire it into `live_eventlog.answer_question`: counts/listing answer from BoundEntities, not raw rows.
   "how many X" → the bound count; if only seen in 1-2 frames, hedge ("at least one, can't reliably count").

## Acceptance (`tests/test_entity_binder.py`)
- 8 observations of subject "bottle" across 2 distinct spatial anchors → `count==2` (not 8).
- 5 observations of "bottle" all at the SAME anchor → `count==1`.
- A subject seen once → confidence "low", count answer hedged.
- Existing object-grounded refusal (brief 01 tests) still passes.

## Guardrails
- Additive; `.venv/bin/python -m pytest tests/ -q` must pass. No domain-class edits. Commit on the branch
  (driver handles commit). Report summary + pytest result.
