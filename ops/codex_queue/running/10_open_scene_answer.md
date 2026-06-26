# CODEX BRIEF 10 — open-ended "what did I see / what's here" scene answer

Branch: `codex/10-open-scene`. Python via `.venv/bin/python`. Additive. Do NOT touch
`trace-native-fastvlm/` or `src/trace_memory/domain/`. Builds on `live_eventlog.py` + `entity_binder.py`.

## Why
The #1 demo question is "what did I see?" / "what's here?" — open-ended, not count/existence/attribute.
The event-log answer path currently only parses those three intents. Add an open scene-summary intent.

## Tasks
1. In `live_eventlog.answer_question`, detect open questions ("what did I see", "what's here/there",
   "what was around", "describe what I saw", "what was on the table"). For these, build the answer from the
   bound entities (entity_binder): list the high/medium-confidence objects with their best attributes,
   ordered by confidence/recency, e.g. "You saw a blue water bottle, a Pringles can (sour cream & onion),
   a cereal box, and a soda can." Cite a couple of timestamps.
2. Produce the two-zone result (reuse brief 04): personal_evidence = the object list; world_context = fenced
   world knowledge for the recognized branded items.
3. If NO bound objects exist → honest refusal ("I didn't capture anything clearly").

## Acceptance (`tests/test_open_scene_answer.py`)
- "what did I see" over a fixture with {blue water bottle, pringles can, cereal box} → answer NAMES all three,
  not refused, with personal_evidence non-empty.
- Low-confidence-only ghosts (1-frame) are excluded or hedged.
- Empty memory → refusal.

## Guardrails
- Additive; `pytest tests/ -q` passes. No domain edits. Commit on branch. Report the example answer text.
