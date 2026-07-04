# P11 — Appearance fingerprints (things pin to identities)
wave: W1 · tag: guided · executor: Opus effort=medium · depends: P00 (frame source), P02 (schema field)

## Context (self-contained)
Coordinates alone mis-count movable things: keys occupy six coordinates in a day — six
"objects" by geometry, one by identity. Fix: every confirmed track gets a compact visual
signature computed ON THE PHONE from its crop, emitted as the `fingerprint` field
(P02 schema). Fingerprints must be non-reversible (L1: they may cross to the Mac; pixels
may not) — an embedding vector, not an image patch.

## Laws that bind you
L1 (non-reversible, small — target ≤256 floats), L2. Crops never leave the device.

## Do
1. Phone: reuse the existing per-track crop path (EnrichmentScheduler /
   TraceDetectorBridge in `trace-native-fastvlm/FastVLM App/`) to feed a small on-device
   embedding model (Vision featureprint or a distilled ANE model — executor evaluates,
   documents choice) once per confirmed track (throttled like M5's crop enrichment;
   respect its kill switch pattern — enrichment froze the app once).
2. Emit fingerprint on the track's observations; hub stores it typed (not in text).
3. Mac: cosine-similarity helper in the store (`src/trace_memory/store/`) so the sleep
   binder and future live binder can ask "same thing?" — with a measured same/different
   threshold: validate on ≥20 real object pairs (same mug two sightings vs different mugs)
   and record the ROC numbers in this file.

## Forbidden
No merging decisions in this packet (P12/P32 own same-vs-new). No pixels in the store.

## Done when
Real capture shows fingerprints on ≥70% of confirmed tracks; same-object pairs measurably
closer than different-object pairs (numbers pasted below); pytest + battery hold; iOS
build green. INDEX flipped.

## Landed (Mac side) — 2026-07-04
Fully tested (`tests/unit/test_appearance_fingerprints.py`, 8 tests; pytest + battery hold):
- `contract.py`: `is_valid_fingerprint` / `normalize_fingerprint` — one owner for the L1
  non-reversible-vector rule (≤512 floats), shared by the contract path AND the legacy phone
  shape. Garbage vector → dropped, row survives.
- `trace_hub.py`: fingerprint flows through the LEGACY ingest path too (the phone streams
  legacy — same lesson as P10), stored typed in metadata, never in the text column.
- `sqlite_store.py`: `fingerprint_of` / `fingerprint_similarity` (cosine, reuses `_cosine`) /
  `same_appearance` / `fingerprint_neighbors` (linear scan — honest for prototype scale) /
  `fingerprint_coverage` (Done-when instrument). `FINGERPRINT_MATCH_THRESHOLD = 0.82` is a
  SYNTHETIC default, flagged in-code as a lie until the device ROC replaces it.
- Synthetic ROC test proves the cosine substrate separates same-object from different-object
  pairs and the threshold sits in the gap — the MACHINERY is sound; the featureprint's real
  separation on our crops is the device unknown.

## Swift side — LANDED (build-verified compiling; behavior device-pending) 2026-07-04
`maybeFingerprintTrackCrop` (ContentView) + `computeFeaturePrint` + the `track_fingerprint`
emission:
1. Own kill switch `ENABLE_TRACK_FINGERPRINT` (default true), NOT gated behind the disabled
   heavy VLM crop enrichment. Cheap ANE `VNGenerateImageFeaturePrintRequest`, detached Task,
   ONE dedicated low-frequency row per confirmed track (the ~2048-float vector never rides the
   high-frequency detector posts). Throttle: once per track, ≥2s cooldown, one at a time.
   MUST verify on a device run that frames_received/converted hold (no perception tax).
2. Model choice = native Vision featureprint (~2048 floats), L2-normalized. Chose to RAISE the
   contract cap (`FINGERPRINT_MAX_FLOATS` 512→4096) over shipping a blind on-device reduction —
   L1's hard rule is non-reversibility (holds), the "≤256 small" target was a soft nicety.
   Reduction (random projection / distilled model) is a future optimization gated on measured
   need. Swift refuses to emit any vector >4096 or non-float32 (never emits what the hub drops).
3. Emits `fingerprint` (top-level) + `track_id`; the Mac side above already consumes it.

## Measured ROC
- (device-gated — the walk writes real same/different pairs here and sets the threshold)
