# CODEX BRIEF — wire ENTITY-CAPTURE into the assembler dossier (Python only, no GPU)

## Goal
The brain hallucinates by mis-binding attributes to the wrong entity (cold clip:
"bag zip closed" with fake timestamps, "Röntgen" name carried onto the WRONG poster).
`scripts/build_entity_capture.py` already produces per-entity structured records that
bind clothing/logos/holding to the RIGHT person/object AT CAPTURE. It exists but is NOT
read by the brain. Your job: WIRE that channel into the assembler so (a) bound attributes
reach the dossier and (b) when a question asks about an attribute that was NEVER observed
for an entity, the dossier says so explicitly — giving the model grounds to refuse instead
of fabricate.

## Exact integration points (edit ONLY `scripts/ask_home.py` + add ONE test file)
1. `gather_evidence(question, memory_path, mems)` (ask_home.py ~line 1371): load the
   entity-capture channel. NOTE: `entity_capture.json` is **NDJSON** — ONE JSON object per
   LINE, not a JSON array. Parse line-by-line, skip blank/garbage lines defensively (mirror
   the try/except style of the `attr_log`/`bound` loaders right above the `return`). Add the
   parsed list to the returned dict as `"entity_capture": <list-or-None>`. Each row schema
   (see the header of scripts/build_entity_capture.py):
   `{t, frame, persons:[{appearance, clothing:{top,bottom,colors:[]}, accessories:[],
   holding:[], position}], text_objects:[{object, logo_or_text}], is_self_view, 
   self_attributes:{...}, parse_ok}`.
2. `build_evidence_dossier(question, channels, ...)` (ask_home.py ~line 1444): add a new
   section, mirroring the existing `bound`/`attr_log` sections (rank rows by question-keyword
   overlap using the existing `_dossier_tokens` / `_score_overlap`; cap at `max_per_channel`).
   Emit lines like:
   ```
   === ENTITY CAPTURE (who-wore-what, bound at the moment of capture) ===
   [t=Xs] PERSON: <appearance> — top <top>, bottom <bottom>, colors <...>; holding <...>; <position>
   [t=Xs] OBJECT: <object> — logo/text: "<logo_or_text>"
   [t=Xs] SELF-VIEW: <self_attributes summarized>
   ```
   Only include `parse_ok` rows. Keep each line short.
3. HONEST-REFUSAL HELPER (the point of the whole thing): when the question targets a
   specific entity+attribute (e.g. "bag zip", "colour of the bag", "logo on the mate"),
   and across the surfaced entity-capture rows that attribute/state is ABSENT, append ONE
   explicit line so the model can refuse honestly, e.g.:
   `NOTE: across the entity-capture frames, no <attribute> was recorded for <entity> — if
   no other channel reports it, answer "I don't have that in my memory."`
   Keep this conservative: only emit the NOTE when the entity itself WAS seen but the asked
   attribute was not. Do not invent.

## LAWS (follow exactly)
- Edit ONLY `scripts/ask_home.py` and add `tests/test_entity_capture_wiring.py`. Touch nothing else.
- DO NOT modify the structural grounding gate (`structural_grounding`, G1/G2/G3/G4) or any
  constant near `ASSEMBLER_GROUNDING_GATE`. They are calibrated; leave them.
- DO NOT call ollama, load any model, or run the GPU build. Pure Python, CPU only.
- Degrade safely: if `entity_capture.json` is absent or unparseable, the channel is None and
  the dossier simply omits the section — NEVER raise. The brain must work unchanged when the
  file is missing (it is missing right now; the Chief generates it separately on the GPU).
- `python3 -m py_compile scripts/ask_home.py` MUST pass.

## Tests (CPU, no model) — this is your proof, not a claim
Add `tests/test_entity_capture_wiring.py` that, WITHOUT any model:
1. Writes a tiny fake `entity_capture.json` (NDJSON, 2-3 rows: a person in a green top with a
   "North Face" backpack; a separate object row; one is_self_view row) into a temp memory dir
   with a minimal `world_memory.json`.
2. Calls `gather_evidence` + `build_evidence_dossier` and asserts:
   - the green-top person and the "North Face" logo BOTH appear in the dossier, bound to their
     own lines (the logo is NOT attached to the person line);
   - for a question like "was my bag zip open or closed", since no zip/zipper state exists in
     any row, the dossier contains the explicit "no ... recorded" NOTE.
3. Asserts that with NO entity_capture.json present, `gather_evidence` returns
   `entity_capture=None` and `build_evidence_dossier` still returns a dossier (no crash, no section).
Run it with the repo venv: `.venv/bin/python -m pytest tests/test_entity_capture_wiring.py -q`
(or `.venv/bin/python tests/test_entity_capture_wiring.py` if pytest is absent — make it run both ways).

## Deliverable
When done and tests pass, write `ops/CODEX_BRIEF_entity_wiring_RESULT.md` with: the exact diff
summary, the test output (pasted), and any edge cases you handled. Do not claim success without
the pasted passing test output.
