# S1 / TASK 04 — STORE HYGIENE (kill the self-homework pollution)
*SERIAL. Do not start 05 until this validates. One task, one gate.*

## ROOT CAUSE (measured)
The unified store is 79% pollution: 1407 `mac_screen` nodes (YouTube + the Claude app + the Codex
app + the cockpit) vs ~380 real lived-experience nodes. "nutella" = 103 mac_screen vs 43
phone_camera — i.e. the system captured US DISCUSSING the founder's questions and now retrieves its
own homework. This is the dominant cause of the 45.5% hallucination.

## INPUT CONTEXT
- `data/trace_store.sqlite3` (tables: memory_nodes[source,text,metadata_json], memory_links)
- `src/trace_memory/store.py` (TraceMemoryStore: nodes(), search(), sources filter)
- capture daemons that WRITE mac_screen: `scripts/screen_capture_daemon.py`,
  `scripts/cockpit_updater.py`, anything POSTing source=mac_screen to the brain
- `src/trace_memory/brain/agent.py` (already supports restrict_sources)

## EXACT DIRECTIVE
1. Write `scripts/build_demo_store.py` that produces `data/trace_store_demo.sqlite3` containing ONLY:
   - every node whose `source` in {phone_camera, phys_video, native_speech, live_screen}
   - PLUS `mac_screen` nodes ONLY if their text/app is INTENTIONAL digital context (e.g. an order/
     receipt) and NOT in the DENYLIST app set: {Claude, Codex, Cockpit, Terminal, YouTube, Brave,
     Edge, Chrome, Safari} — detect via the `SCREEN [App]` prefix and url/app tokens.
   - Copy the matching memory_links (both endpoints present).
2. Make the live answer path default to the demo store for the pitch: the brain/eval read
   `data/trace_store_demo.sqlite3` when `TRACE_DEMO_STORE=1`.
3. STOP ongoing pollution: gate `screen_capture_daemon.py` so it SKIPS denylist apps at capture time
   (never writes a Claude/Codex/YouTube frame as memory again).

## VALIDATION METRIC (must be machine-checked, not "looks done")
- `python scripts/build_demo_store.py` exits 0 and prints node counts before/after.
- Assert: `select count(*) from memory_nodes where source='mac_screen'` in the demo store contains
  ZERO denylist-app nodes (script self-checks and prints "DENYLIST RESIDUE: 0").
- Assert: phone_camera node count in demo store == phone_camera count in source store (no real
  signal dropped).
- Re-run the bedroom keyword probe: "nutella" nodes in demo store must be majority phone_camera.
