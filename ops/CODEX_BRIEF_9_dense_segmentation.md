# CODEX BRIEF 9 — dense mask proposals: label EVERYTHING in the room

Founder verdict after the first ground-truth eval (P 0.417 / R 0.244,
evaluation/home_eval_20260612.md): coverage is the product. "There are
so many items in my room and it identified not even 1%." The saliency
proposal stage is the structural ceiling — replace it with dense
segment-everything masks. The namer (MobileCLIP), judge (FastVLM),
pinning, permanence, posting: all UNCHANGED — you are swapping the
region source and adding per-instance shape.

BUDGET: P0 → P1 → P2 in order, commit per P (if .git is read-only in
your sandbox again, leave work uncommitted and say so loudly in the
RESULT file). Stop after P2. No refactors.

Laws: suite + north-star green after any soma_hub change; build recipe
`xcodebuild -project FastVLM.xcodeproj -scheme "FastVLM App"
-configuration Release -sdk iphoneos26.5
ASSETCATALOG_EXEC=/tmp/actool_wrapper/actool build`; X-SOMA-Token;
no Flask; never Apple ID/password. Lead installs on device.

## P0 — Segment-everything proposals on-device

- Find/produce a CoreML everything-mode segmentation model in the
  SAM-2-tiny / MobileSAM / FastSAM class. Try in this order, take the
  first that WORKS end-to-end, document the choice in RESULT:
  1. A published CoreML conversion (search ml-community repos /
     huggingface for "mobilesam coreml", "sam2 coreml", "fastsam
     coreml"); verify license permits use.
  2. Convert yourself via coremltools from the official tiny checkpoint
     (everything-mode: grid prompt or mask-decoder-free variant like
     FastSAM-s). .venv has python; pip-install into .venv only.
  3. FALLBACK if neither lands within your budget: dense pyramid crops
     — Vision attention saliency + 5x5 AND 7x7 grid tiles at two
     scales, IoU-dedup, cap 40 regions/frame. Shippable tonight,
     mark as fallback in RESULT.
- Integrate as the region source in SpatialWorld scan path: masks →
  bounding rects (+ mask polygon, see P1) → existing MobileCLIP naming
  → existing pinning. Keep per-scan time budget: if scan ms p95 >
  600ms, subsample masks by area (largest first) — log the cap.
  Skip masks <1.5% or >70% of frame area.
- Per-frame proposal target: ≥20 named candidates in a cluttered view
  (was ≤5). Words/min status line will show it.

## P1 — Instance footprints (founder: "the word in the SHAPE of the
actual object")

- For each accepted mask: simplify its outline to ≤24 points
  (Douglas-Peucker), project the points via the existing raycast path
  onto the support plane (or best-fit plane through the hit points),
  store on SpatialObject: `footprint: [[x,z]...]` (plane-local meters,
  Codable, default empty) + `heightM: Float` (mask vertical extent in
  world units). Multi-sighting: union/EMA the footprint conservatively
  (keep it stable, don't let one bad mask wreck it).
- Post footprint+heightM in spatial_words; hub stores them in
  spatial_pose JSON; /api/world passes through. Tests for the
  passthrough (suite green).
- world3d consumes it later (qwen task) — your job ends at the API.

## P2 — Throughput guard + vocab rebuild integration

- The namer will now run 5-20x more often. Batch MobileCLIP requests
  per frame (single VNCoreML handler reuse), measure: status shows
  namer p50 and proposals/frame. If thermal state >= serious, halve
  proposal cap (log it).
- ops/spatial_vocab.txt will be expanded to ~1500 words by the local
  fleet tonight (night-shift task N2). If
  Resources/vocab_embeddings.json has >800 entries when you build,
  bundle it; otherwise build with the current one — do NOT block on it.
  (HF .cache gotcha: delete any .cache dir the builder leaves before
  xcodebuild — synced groups try to compile it.)

## Acceptance (lead verifies on device)

1. Same desk/room pan that produced ~24 objects now yields ≥80 named
   pinned objects (founder's cluttered home).
2. /api/world objects carry footprint polygons for ≥half of them.
3. Scan stays interactive (no thermal shutdown, p95 scan < 600ms).
4. RESULT file: model chosen + why, proposal counts measured, risks.
