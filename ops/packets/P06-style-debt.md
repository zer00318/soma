# P06 — Style debt: make the pre-push hook green again
wave: W0 · tag: mechanical · executor: local LLM or Sonnet (Opus effort=low) · depends: P03+P05 merged (don't reformat under their feet)
status: BLOCKED (until the two in-flight agent branches merge)

## Context (self-contained)
`git push` runs `make check` (Makefile): ruff format --check, ruff check, a function-
complexity gate (tools/check_functions.py, max 10), and frozen-gold verification.
As of 2026-07-04 it fails: 29 files need `ruff format`, 194 ruff lint errors (42
auto-fixable), and `individuate.py:499` complexity 16 (max 10). This debt accumulated
across the sprint — the hook only fires on push and nothing was pushed since June.
Pushes currently use --no-verify (functional gates — 257 tests + canonical battery —
are green and stricter, but the hook must return to service).

## Laws that bind you
Behavior-preserving ONLY. The merge gate is the proof: `.venv/bin/python -m pytest -q`
identical pass count before and after, and the canonical battery
(`.venv/bin/python evaluation/run_canonical_battery.py`) holds CONFIDENT-WRONG = 0.

## Do
1. `.venv/bin/python -m ruff format src tests/unit tools`
2. `.venv/bin/python -m ruff check --fix src tests/unit tools`, then fix the remaining
   lint findings by hand — smallest edits, no logic changes. If a rule demands a logic
   change, `# noqa` it with a one-line justification instead.
3. `individuate.py` complexity 16 → extract straight-line helper functions (pure
   mechanical extraction, no reordering of decisions) until the gate passes.
4. `make check` fully green, full pytest + battery hold, one commit, plain `git push`
   (no --no-verify) proves the hook.

## Done when
`make check` exits 0 · pytest count unchanged · battery holds · pushed without bypass.
INDEX flipped.
