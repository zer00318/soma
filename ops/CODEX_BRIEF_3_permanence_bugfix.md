# CODEX BRIEF 3 — Permanence bugfix (BLOCKS brief 2; founder test FAILED)

Lead-verified failure analysis, 2026-06-12 ~01:00. Founder desk test of
brief 1: FAIL on all three acceptance points. Fix in this order; brief 2
(extent/graph/events) resumes only after re-acceptance.

## Verified root causes

1. PERSISTENCE NEVER EXECUTES (fact: after a full session of use,
   `Library/Application Support/SOMA/spatial_world.json` DOES NOT EXIST
   on device — lead checked via devicectl). Saving happens only in
   `stop()` — but swiping the app away is SIGKILL; no callback fires.
   FIX:
   - Debounced save: 2s after any object upsert, plus every 30s timer.
   - Lifecycle save: observe scenePhase -> .inactive/.background (or
     UIApplication.willResignActiveNotification) and save BOTH the JSON
     and the ARWorldMap there, wrapped in
     `UIApplication.beginBackgroundTask` so the async
     `getCurrentWorldMap` completes before suspension.
   - Saving the JSON must never depend on the world map call succeeding.

2. IN-SESSION DUPLICATES (founder: re-showing the same electronics
   created second copies). Suspects, in likelihood order: merge radius
   (0.4m) smaller than raycast scatter on `.estimatedPlane`; raycast
   sometimes hits the wall/floor behind the object (meter-scale error);
   no nearest-match (any miss creates). FIX:
   - Merge to NEAREST same-word object if within 1.2 m (EMA position).
   - Two-sighting confirmation: a new word creates a PENDING candidate;
     only a second sighting of the same word within 0.8 m of the pending
     position promotes it to a permanent object. One-off flukes die.
   - If a same-word permanent object exists within 2 m, never create a
     second one — merge to nearest.

3. NO DIAGNOSTICS (fact: native log has zero spatial entries — failures
   are invisible). FIX: append every naming/upsert decision to
   `Application Support/SOMA/spatial_diag.ndjson`:
   {ts, word, score, ms, pos:[x,y,z], decision: merged|pending|created|
   rejected, matched_id?, dist_to_nearest_same_word?}. The next desk
   test must produce NUMBERS (scatter distances, latencies), not vibes.

4. CROSS-SESSION: until (1) lands every launch is a fresh genesis frame,
   so cross-session duplicates are guaranteed by design. After (1):
   when a world map loads, gate upserts until tracking is `.normal`
   (relocalized); if relocalization hasn't happened within 20 s, run
   with the loaded objects anyway but log `relocalization_timeout`.

5. DASHBOARD WAS NOT RUNNING (fact: no process on :8777 — that's why
   "localhost doesn't work"). Lead started hub + dashboard manually;
   both / and /world now return 200. FIX: add `scripts/run_trace_stack.sh`
   — idempotent (pgrep guards) start of hub (:8765), dashboard (:8777),
   enricher; print status lines. Founder runs ONE script after reboot.

## Re-acceptance (same founder test, now measurable)

1. Desk pan: cpu/fan/keyboard/mouse named + pinned; showing them AGAIN
   merges (sightings climb in diag log) — no second copies.
2. Swipe-kill the app. Reopen: words return in place (JSON reload +
   relocalization). spatial_world.json exists on device.
3. http://localhost:8777/world renders after `run_trace_stack.sh`.
4. Lead pulls spatial_diag.ndjson and verifies: merge rate, scatter
   distances, p50 namer ms.

## Law (unchanged)

X-SOMA-Token; soma_hub.sqlite3; no Flask; -sdk iphoneos26.5 +
ASSETCATALOG_EXEC=/tmp/actool_wrapper/actool; device
D3A506B2-8923-5313-B8A3-FF769ABBA228. COMMIT YOUR WORK when verify
passes — uncommitted deliveries slow the lead down. Python suite +
north-star stay green after any soma_hub change. Findings →
ops/HANDOVER.md.
