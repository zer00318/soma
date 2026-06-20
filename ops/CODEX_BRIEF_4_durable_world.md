# CODEX BRIEF 4 — build stamp, durable world, better proposals

Written by Claude lead (Fable 5), 2026-06-12. SUPERSEDES brief 2 — same
items, new priority order, three additions (P0 build stamp, P3 proposal
fallback, explicit gates). Work P0 → P4 strictly in order; each P is
independently shippable. Commit per P with a short imperative subject —
do NOT batch everything into one commit. The lead verifies each P on
device artifacts, not on "build succeeded".

Context you must read first: ops/HANDOVER.md (sections from 2026-06-11
onward), soma_hub/graph.py (LAW — patterns there are binding),
scripts/trace_demo_dashboard.py, SpatialWorld.swift, MobileCLIPNamer.swift.

Project law (violations = rejected work): X-SOMA-Token header;
data/soma_hub.sqlite3; `with self._connect()`; no Flask; never Apple
ID/password; Python suite (122) + `python3 evaluation/run_north_star.py`
(1.00) must be green after ANY soma_hub change; iOS build recipe =
`xcodebuild -project FastVLM.xcodeproj -scheme "FastVLM App"
-configuration Release -sdk iphoneos26.5
ASSETCATALOG_EXEC=/tmp/actool_wrapper/actool build` (destination-based
builds fail; this works — verified 2026-06-12 01:20).

## P0 — Build identity stamp (≤1h, do this first)

WHY: the founder desk-tested a stale build last night without anyone
noticing (posts carried `word_source: native_vision_classifier`, which no
longer exists in the repo). Never again.

- Add a generated `BuildStamp.swift` via an Xcode pre-build Run Script
  phase: `echo "enum BuildStamp { static let sha = \"$(git -C
  "$SRCROOT/.." rev-parse --short HEAD)\"; static let builtAt =
  \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\" }" > ...` (write into a synced-group
  folder; add to .gitignore).
- Show `BuildStamp.sha` in the Spatial-mode status line (append to
  `namingStatus`).
- Add `"build": BuildStamp.sha` into every posted payload's `metadata`
  (the spatial snapshot post AND the regular perception packets).
- Acceptance: status line on device shows the sha; a captured packet in
  the hub DB carries it.

## P1 — Durable world in the GRAPH (the permanence gap)

WHY (lead-verified): `/world` currently renders ONLY the latest
spatial-snapshot observation row; restart the dashboard or wait a day and
the world is empty. Permanence must come from the DB.

- Hub side: when a perception post has
  `metadata.capture_mode == "spatial_word_map"`, upsert ONE
  graph_attributes row per word: attribute_key='spatial_pose',
  attribute_value=JSON `{"x":..,"y":..,"z":..,"w":0,"h":0,"sightings":..,
  "frame":"genesis","last_seen":"<ts>","build":"<sha>"}` — upsert by
  (entity_id, attribute_key), the existing one-value-per-key pattern.
  Entity = kind 'object', label = the word (existing entity resolution
  path; create if absent; status stays current; NEVER delete).
- `/world` renders DB spatial_pose rows merged with the live latest
  snapshot (live wins for shared labels). Empty-DB behavior unchanged.
- Tests: extend the Python suite with a posted-fixture → spatial_pose row
  → /world JSON test. Suite + north-star green.
- Acceptance: phone posts desk words → kill dashboard → restart → /world
  still shows the desk from DB alone (phone off).

## P2 — Object extent (dimensions) [brief 2 item 1, unchanged]

- Raycast region edge midpoints (left/right/top/bottom) → width/height
  estimates; `extent` on SpatialObject (Codable w,h), EMA like position;
  zero if edge raycasts miss — never invent.
- Carry w,h in the posted spatial_words and into spatial_pose (P1 JSON).
  Scale word size by extent in app map + /world.
- Acceptance: monitor word visibly bigger than mouse word on both
  surfaces.

## P3 — Region proposals fallback + vocab feedback [the real bottleneck]

WHY: objectness saliency returns ≤3 coarse regions; a desk has 8+
nameable objects. The namer is fine; starve it less.

- When saliency yields <2 usable regions for a frame: tile the frame 3×3
  plus one center crop (10 ROIs), drop tiles overlapping an accepted
  saliency region (IoU>0.5), run MobileCLIP on the rest, keep
  score/margin survivors. Cap total accepted regions at 5/frame; keep the
  existing per-scan time budget — if p95 scan ms exceeds 350ms, halve the
  scan rate (log it).
- Every region whose best word fails the floors: append
  {ts, best_word, score, margin} to
  `Application Support/SOMA/vocab_misses.ndjson`.
- p50/p95 namer ms + words/min stay on the status line.
- Acceptance: desk scan names ≥6 distinct correct desk objects within
  60s (was ~3-4); vocab_misses.ndjson populates.

## P4 — Re-entry events [brief 2 item 3, unchanged]

- On session start with a loaded world map, after tracking normal 10s:
  expected set = stored objects inside camera frustum cumulatively ~3s
  while panning. Expected, never re-seen within 90s → POST memory_text
  "EVENT | object missing | <word> last seen <date> at stored position |
  spatial re-entry check | likely". Re-seen >0.5m away → "object moved".
  One event per object per session; no deletions; events must appear on
  the dashboard.
- Acceptance: hide the bottle with app closed; reopen, pan desk; missing
  event reaches hub within ~90s.

## Delivery protocol

- Commit per P (you may commit; lead reviews every commit).
- After each P that touches the app: build with the recipe above and STOP
  — the lead installs and device-verifies (founder phone state is lead's
  responsibility).
- Anything ambiguous: leave a NOTE in the commit body, choose the
  conservative reading, keep moving.
