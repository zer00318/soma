# CODEX BRIEF 13 — kf_memory.json persistence across brain restarts

Branch: `codex/13-kf-persistence`. Python via `.venv/bin/python`. Additive.
Only edit `scripts/trace_brain_server.py`. Do NOT touch `src/`, `trace-native-fastvlm/`, or `ops/`.

## The problem
`_LIVE` is an in-process dict that empties on brain restart. The first `/ingest` after restart
writes `kf_memory.json` with only 1 record, overwriting everything captured in previous sessions.
`events.db` (Source 1, live_eventlog) already persists correctly — this fix is for the kf
rolling buffer used by Sources 3 and 5 in the answer cascade.

## Fix (one function, two lines)
In `_capture()` in `scripts/trace_brain_server.py`, after:
```python
store = _LIVE.setdefault(moment, {"t0": time.time(), "records": []})
```
add — ONLY when `store["records"]` is empty (first capture this brain session for this moment):
```python
if not store["records"]:
    _path = _moment_dir(moment) / "kf_memory.json"
    if _path.exists():
        try:
            _existing = json.load(open(_path))
            if isinstance(_existing, list):
                store["records"] = _existing[-LIVE_MAX:]
        except Exception:
            pass
```
This loads the existing records from disk into `_LIVE` before appending the new frame, so
`kf_memory.json` is never overwritten with a shorter list than what was on disk.

## Constraints
- Insert inside the `with _LIVE_LOCK:` block, right after the `setdefault`.
- File read must be inside the lock to avoid a race.
- If the file is missing, malformed, or not a list → silently skip (the try/except handles it).
- Do not change LIVE_MAX or any other logic.

## Acceptance (`tests/test_kf_persistence.py` — write this file)
```python
import json, tempfile, pathlib
# Simulate: write a kf_memory.json with 5 records, clear _LIVE, send a new capture,
# verify kf_memory.json now has 6 records (5 old + 1 new), not 1.
```
Test must:
1. Write a fake kf_memory.json with 5 records into a temp moment dir.
2. Call `_capture` with the moment pointing at that dir (monkey-patch `_moment_dir`).
3. Assert kf_memory.json has 6 records (old 5 + new 1).
4. Call `_capture` again (second frame): assert 7 records.
5. `pytest tests/ -q` passes (all 301+ existing tests still green).

## Guardrails
- Additive change only — no existing behaviour changes when kf_memory.json doesn't exist.
- No new imports needed.
- Commit on branch. Report: "old records=N loaded, new total after first new frame=N+1".
