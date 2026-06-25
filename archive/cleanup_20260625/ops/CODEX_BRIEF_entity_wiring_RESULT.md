# Entity-Capture Wiring Result

## Exact diff summary

- `scripts/ask_home.py`: `gather_evidence` now reads sibling `entity_capture.json` as NDJSON, skips blank/malformed/non-object lines, and returns valid rows as `entity_capture` or `None` when no valid rows are available.
- `scripts/ask_home.py`: `build_evidence_dossier` now ranks `parse_ok` entity-capture rows by question-keyword overlap, caps them at `max_per_channel`, and emits separate concise `PERSON`, `OBJECT`, and `SELF-VIEW` lines. Object logo/text remains on its object line.
- `scripts/ask_home.py`: added a conservative entity-bound absence check for explicitly requested zip state, colour, logo, clothing, or held-item attributes. It emits one honest-refusal note only when the named entity was surfaced and that attribute was not recorded for it.
- `tests/test_entity_capture_wiring.py`: added pure-Python coverage for NDJSON loading, malformed-line skipping, `parse_ok` filtering, person/object binding, self-view output, absent zip-state notes, missing files, and wholly unparseable files.

No structural-grounding gate code or `ASSEMBLER_GROUNDING_GATE` constants were changed by this task.

## CPU proof

`pytest` is not installed in the repository venv, so the brief's approved direct-test fallback was used:

```text
..
----------------------------------------------------------------------
Ran 2 tests in 0.010s

OK
```

`PYTHONPYCACHEPREFIX=/tmp/codex-pycache python3 -m py_compile scripts/ask_home.py` also passed with no output. The cache prefix keeps bytecode inside the writable sandbox.

## Edge cases handled

- Missing `entity_capture.json` returns `entity_capture=None` and omits the dossier section.
- Blank, malformed JSON, and valid non-object NDJSON lines are skipped without raising.
- A present file containing no valid object rows degrades to `None`.
- Rows without `parse_ok: true` are not surfaced.
- Missing or wrongly typed nested person/object fields degrade to omitted details rather than exceptions.
- Absence notes are not emitted unless the question clearly requests a supported attribute and a matching surfaced entity was actually seen.
