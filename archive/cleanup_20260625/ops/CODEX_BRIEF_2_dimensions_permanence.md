# CODEX BRIEF 2 — Dimensions, durable world map, re-entry events

Written by Claude (lead). Prerequisite: brief 1 (MobileCLIP naming core)
is built and installed; founder desk acceptance may still be pending —
these items are independent enough to start now. Founder's standing
priority: objects fix their DIMENSIONS and COORDINATES in space and stay
in memory FOREVER. This brief is that, completed.

## 1. Object dimensions (extent)

- When a region is named and pinned, also raycast the region's left/right
  edge midpoints and top/bottom edge midpoints; world-space distances give
  width and height estimates. Store `extent: simd_float2` on SpatialObject
  (Codable: w,h). EMA-update like position. If edge raycasts miss, keep
  extent zero — never invent.
- Render size: in the app word map and in the /world view, scale the word
  by extent (bigger thing = bigger word — the founder's "large word desk").

## 2. Durable world map in the GRAPH (not just app-local JSON)

- Extend the spatial snapshot the app already POSTs to the hub so each
  word carries {x, y, z, w, h, sightings}.
- Hub side (python, trace_hub/graph.py is LAW — read before touching):
  upsert ONE graph_attributes row per spatial entity:
  attribute_key='spatial_pose', attribute_value=JSON
  {"x":..,"y":..,"z":..,"w":..,"h":..,"sightings":..,"frame":"genesis"}.
  Upsert by (entity_id, attribute_key) — the existing one-value-per-key
  pattern. Never delete spatial entities (status stays current).
- /world in scripts/trace_demo_dashboard.py renders from the DB
  (spatial_pose rows) merged with live posts — so the map survives app
  restarts and shows on the dashboard even when the phone is offline.

## 3. Re-entry events — the payoff of permanence

- On session start with a loaded world map: after relocalization
  stabilizes (tracking normal for 10s), build the EXPECTED set: objects
  whose stored position fell inside the camera frustum for a cumulative
  ~3s while the user pans. Expected but never re-seen within 90s →
  POST memory_text event: "EVENT | object missing | <word> last seen
  <date> at stored position | spatial re-entry check | likely".
  Re-seen >0.5m from stored position → "EVENT | object moved ...".
- Keep it conservative: one event per object per session, no deletions.

## 4. Perf + vocabulary feedback loops

- Log p50/p95 namer latency ms and words/min to the on-screen status.
  Budget: <80ms per region on ANE; if exceeded, halve scan rate.
- Every region whose best word scored BELOW threshold: append
  {ts, best_word, score} to Application Support/TRACE/vocab_misses.ndjson.
  The founder reviews it to grow ops/spatial_vocab.txt; rebuilding
  embeddings = rerun scripts/build_vocab_embeddings.py + rebuild app.

## Acceptance (founder-testable)

1. Desk objects show plausible sizes; monitor word bigger than mouse word.
2. Kill app, open dashboard /world on the mac: the room is still there,
   from the DB.
3. With app closed, hide the bottle. Reopen app, pan the desk: within
   ~90s a "bottle missing" event reaches the hub (visible in dashboard).

## Law (unchanged)

X-TRACE-Token; trace_hub.sqlite3; `with self._connect()`; no Flask; build
-sdk iphoneos26.5 + ASSETCATALOG_EXEC=/tmp/actool_wrapper/actool; device
D3A506B2-8923-5313-B8A3-FF769ABBA228; run the python test suite + 
north-star eval after ANY trace_hub change (must stay green); write
findings/deviations into ops/HANDOVER.md for the next Claude session.
