# CODEX BRIEF 8 — phantom judge, space data, "where is X"

Lead-fired sprint brief (2026-06-13). Founder's #1 verdict on the live
world: "it invented an iron board… and many many more objects that are
not there." Your job: kill phantoms with FastVLM as judge, ship the
data the space-renderer needs, and make the graph answer "where is X".

BUDGET DISCIPLINE: you have a usage limit. P0 → P1 → P2 strictly; one
commit per P; NO refactors, NO polish, NO drive-by fixes. If a P is
ambiguous, take the conservative reading, note it in the commit body,
move on. Stop after P2.

Read first: ops/HANDOVER.md (top 3 sections), SpatialWorld.swift
(verification path), trace_hub/graph.py (LAW — its patterns are binding),
scripts/trace_demo_dashboard.py (/api/world).

Project law: X-TRACE-Token; data/trace_hub.sqlite3; `with self._connect()`;
no Flask; never Apple ID/password; Python suite + north-star
(python3 -m unittest discover -s tests -p "test_*.py";
python3 evaluation/run_north_star.py) MUST be green after any trace_hub
change; iOS build recipe: xcodebuild -project FastVLM.xcodeproj -scheme
"FastVLM App" -configuration Release -sdk iphoneos26.5
ASSETCATALOG_EXEC=/tmp/actool_wrapper/actool build. Build at the end of
each P that touches Swift; the lead installs on device.

## P0 — Phantom judge (Swift, SpatialWorld.swift + MobileCLIPNamer area)

The tier-2 verifier already relabels via vocab-gated prose extraction.
Extend it to JUDGE EXISTENCE:

- Add to SpatialObject: `phantomStrikes: Int = 0`, `phantom: Bool =
  false` (Codable, default-decoding like verified/relabeledFrom).
- In finishVerification: when cleanVerifiedSpatialLabel returns nil AND
  the raw output matches the garbage/cannot-see class (reuse
  garbageCropTells + "no objects", "cannot see", "not visible"), count
  ONE strike — but only if this crop's updatedAt differs from the crop
  that caused the previous strike (3 strikes must come from 3 DISTINCT
  crops, i.e. different sightings/moments). At 3 strikes: phantom=true,
  diag decision "phantom_marked" with sightings + strikes.
- A SUCCESSFUL verification (verified or relabeled) resets strikes to 0
  and phantom=false (objects can rehabilitate), diag "phantom_cleared".
- phantom objects: EXCLUDED from `words` (regenerateTree) and from
  posted spatial_words; NEVER deleted from `objects` (provenance).
  Status line gains "ph:N" count.
- Per-object verification backoff (existing) applies unchanged; phantom
  objects stop being verified (skip in maybeStartVerification) unless
  re-sighted by MobileCLIP after phantom_marked — a fresh sighting
  resets backoff attempts to allow one re-judgment cycle.
- Acceptance: a misnamed low-score object at an empty position gets
  phantom_marked within ~3 verification cycles in spatial_diag.ndjson;
  it disappears from the on-phone map and from new posts; total object
  count in spatial_world.json unchanged.

## P1 — Space data through to /api/world (Swift post + Python ingest)

The renderer needs SPACE, not points (founder: "the word desk should
look like a desk so things can rest on it").

- Swift: posted spatial_words entries gain `w`, `h` (extent — fields
  exist on SpatialObject), `support_plane` (supportPlaneID string or
  null), `verified` (bool), `phantom` is never posted (P0 excludes).
- Python hub ingest: spatial_pose attribute JSON gains the same keys
  (upsert by entity_id+attribute_key — existing pattern).
- /api/world objects gain w, h, support_plane, verified passthrough.
  Missing values default 0/null/false — never invent.
- Tests: extend the existing spatial fixture test: post a word with
  extent+plane → spatial_pose row carries them → /api/world returns
  them. Suite + north-star green.
- Acceptance: curl /api/world shows w/h/support_plane/verified for
  fresh desk objects.

## P2 — "where is X" recall intent (Python, trace_hub)

First spatial RAS payoff: the graph can answer object-location
questions with citations.

- New recall intent: questions matching r"where('s| is| was)? (my |the
  )?(?P<obj>[a-z ]+)" (and "wo ist" German equivalent) → look up
  entities kind=object whose label/label_norm fuzzy-matches obj and
  that have a spatial_pose attribute.
- Answer, extractive style (NO generation): "<label>: pinned in the
  room at (x, y, z) meters [frame: genesis], size ~w×h m, last seen
  <last_seen>, sightings <n>." If multiple matches, list up to 3 by
  sightings desc. If none: the standard honest miss.
- Citations carry the spatial_pose provenance (entity id + last_seen)
  with confidence from verified (0.9 verified / 0.6 unverified).
- Tests: fixture with two pinned objects; questions "where is the
  keyboard", "where's my bottle" answer with coords; unknown object →
  honest miss. Suite + north-star green.
- Acceptance: python3 -c against the live DB answers "where is the
  keyboard" with coordinates and a citation.

## Delivery

Commit per P (style: short imperative subject + measured body). After
P0 and P1 Swift changes: run the iOS build; report result in the final
message. Do NOT install on device — the lead does that. Leave a 5-line
summary at ops/CODEX_BRIEF_8_RESULT.md (what shipped, what's risky,
what you'd verify first).
