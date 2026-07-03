# P01 — Repo hygiene
wave: W0 · tag: mechanical · executor: local LLM or Sonnet (Opus effort=low) · depends: none

## Context (self-contained)
Repo root `/Users/zer00/Documents/VLM` has 9 stray `tmp*.sqlite3` files (test leftovers,
Jul 1) and model weights scattered at root. Store hygiene matters: a past audit found the
live store 70% contaminated and 21 redundant sqlite stores. The ONLY live store is
`data/trace_store.sqlite3` (+ its -wal/-shm). Do not touch it or `data/*backup*`.

## Laws that bind you
L3: never delete memory-store data — archive, don't destroy, anything you are not 100%
sure is disposable. Merge gate: `pytest -q` green (241+ tests).

## Do
1. `git rm` (if tracked) or delete (if untracked) the root `tmp*.sqlite3` files — verify
   first with `git ls-files tmp*.sqlite3` and confirm none is referenced by any test
   (`grep -rn "tmpXXX" tests/ src/ scripts/` per file).
2. Add to `.gitignore`: `tmp*.sqlite3`, `*.sqlite3-wal`, `*.sqlite3-shm` at root scope.
3. Find any process fixtures writing temp sqlite files to repo root instead of tempdirs
   (`grep -rn "tmp.*sqlite" tests/ evaluation/ scripts/ | grep -v data/`) — if a writer is
   found, point it at `tempfile.mkdtemp()`; if ambiguous, STOP and report instead of guessing.
4. Run `pytest -q`; confirm green; commit.

## Done when
Root has no tmp sqlite files, .gitignore covers them, pytest green, one commit, INDEX flipped.
