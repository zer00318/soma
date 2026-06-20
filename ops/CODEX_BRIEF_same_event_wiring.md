# CODEX BRIEF — wire same_event_relations into the brain (Python only, no GPU, no model)

## Why
The cold clip's remaining hallucinations are MIS-BINDING: a name/logo read on ONE object
gets carried onto a DIFFERENT one (Q10 "Röntgen" onto the wrong blue poster; Q22 the active
chat; Q18 the mate's logo). `scripts/same_event_relations.py` exists precisely to stop this —
it turns `entity_capture.json` rows into per-object/person EPISODES where text stays bound to
the object it was printed on and is NEVER borrowed across a temporally-separate episode. It is
built and tested but has **0 references in `scripts/ask_home.py`** — the brain never sees it.
Wire it into the answer dossier.

## API you will use (read `scripts/same_event_relations.py` for exact signatures)
- `build_relation_index(rows, ...)` — build the episode index from entity_capture rows.
- `query_focus(index, focus, limit=4)` — episodes relevant to a focus term.
- `compact_relation_summary(rows, question, limit=4)` — a compact, dossier-ready summary string.
Input rows = the parsed NDJSON of `entity_capture.json` (the `entity_capture` channel that
`gather_evidence` already loads — confirm it's there; if not, parse the sibling
`entity_capture.json` the same defensive way).

## Edit ONLY `scripts/ask_home.py` + add `tests/test_same_event_wiring.py`
1. `gather_evidence(question, memory_path, mems)` (~line 1371): build the relation index from
   the entity_capture rows and add it to the returned dict, e.g. `"relations": <index-or-None>`.
   Degrade to None on any error / missing file (mirror the existing `bound`/`attr_log` loaders).
2. `build_evidence_dossier(question, channels, ...)` (~line 1444): when `relations` is present,
   add a section near the entity-capture / bound-memory sections:
   ```
   === EPISODE-BOUND RELATIONS (text stays with the object it was printed on) ===
   <compact_relation_summary(...) lines, focused on the question>
   ```
   Use the question to focus (compact_relation_summary takes the question; or query_focus on the
   question's distinctive tokens). Keep it short (limit ~4). The POINT: each line ties OCR/text to
   ITS object/person/episode, so the assembler can answer "whose name is on THIS poster" from the
   right episode and refuse to borrow a name from a different one.

## LAWS (follow exactly)
- Edit ONLY `scripts/ask_home.py` and add `tests/test_same_event_wiring.py`. Nothing else.
- DO NOT modify the structural grounding gate (`structural_grounding`, G1/G2/G3/G4) or any
  `ASSEMBLER_*` constant. DO NOT change `answer_assembler`'s control flow other than adding the
  dossier section.
- DO NOT call ollama / load any model / run any GPU build. Pure Python, CPU only.
- Degrade safely: missing/empty/unparseable `entity_capture.json` → `relations=None` → the dossier
  simply omits the section. NEVER raise. The brain must work unchanged when the file is absent.
- `python3 -m py_compile scripts/ask_home.py` MUST pass.

## Test (CPU, no model) — your proof
`tests/test_same_event_wiring.py`, runnable via `.venv/bin/python tests/test_same_event_wiring.py`
(make it run with or without pytest). Write a tiny fake `entity_capture.json` (NDJSON) into a temp
memory dir with a minimal `world_memory.json`, where TWO different posters in DIFFERENT time
windows each carry a different name. Assert:
1. `gather_evidence` returns a non-None `relations` index;
2. `build_evidence_dossier` for "whose name is on the blue poster" surfaces the name from the
   blue poster's OWN episode and does NOT attach the other poster's name to it;
3. with NO entity_capture.json present, `relations` is None and the dossier still builds (no crash).

## Deliverable
Write `ops/CODEX_BRIEF_same_event_wiring_RESULT.md` with the diff summary and the PASTED passing
test output. Do not claim success without the pasted output.
