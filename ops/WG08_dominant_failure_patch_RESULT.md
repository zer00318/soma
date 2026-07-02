# WG08 Dominant Failure Patch Result

## Outcome
Patched one class only: retrieval/conflict in the world-grounded bedroom demo path.

The concrete failure was that physical `where/current` questions could pull:
- generic authored sleep memories (`memory with ...`)
- screen-transcript/report rows that merely quoted prior eval mistakes

ahead of the raw observation that actually contained the grounded location/app evidence.

The patch stays inside `src/trace_memory/brain/agent.py` and does not weaken the refusal gate, mutate raw helper observations, or touch binder/perception code.

## Code changed
- `src/trace_memory/brain/agent.py`
- `tests/unit/test_world_grounded_memory.py`

## Verification
- Required smallest proof slice rerun:
  - `.venv/bin/python -m pytest tests/unit/test_world_grounded_memory.py -k 'specific_location or relevant_citation_support'`
  - Result: `2 passed, 5 deselected`
- Added regression:
  - `test_agent_prefers_specific_location_evidence_over_conflicting_generic_memory`
  - Proves a location question now ranks the suitcase-bearing support row ahead of the generic bed-only conflict row.
- Real device-derived artifact replay:
  - Replayed the patched agent against `data/trace_store_frontier.sqlite3` (the measured bedroom store built from phone capture).
  - Positive signal: for the laptop-app conflict, the evidence chain now promotes the `Claude File Edit View Window Help` frame (`350922ec-35d9-4df9-b71b-9d0ed9a3dc67`) ahead of the later Codex-report rows.
  - Negative signal: the full bedroom store still does not cleanly resolve `Where is the blanket currently?` and `Where is the current nutella jar?`, so I did not claim a measured frontier-score win from this patch.

## Device verification status
Fresh on-device verification did not complete in this session.

What was verified:
- The iPhone is connected over USB (`system_profiler SPUSBDataType` reported the device).
- The handover deploy path was attempted with `bash scripts/deploy_ios.sh`.
- A second build attempt redirected SwiftPM/clang caches into `/private/tmp`.

What blocked completion:
- `xcodebuild` still attempted SwiftPM/clang writes under `/Users/zer00/.cache` and `/Users/zer00/Library/Caches`, which this sandbox cannot write.
- Because the build never produced an `.app`, `xcrun devicectl device install app ...` could not run.

So the results above are verified against real device-derived bedroom artifacts, but not by a fresh app build/install/launch on the phone in this sandboxed turn.

## Residual risk
- The patch is intentionally narrow. It does not fix helper perception misses, authored-memory wording quality, or the remaining physical-location conflicts in the measured bedroom store.
- If WG08 is revisited, the next honest step is another measured retrieval/conflict pass on the unresolved `blanket/current jar` cases rather than widening this patch into perception or refusal changes.
