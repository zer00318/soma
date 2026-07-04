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

## Swift side — NOT YET SHIPPED (deliberate). Plan + caution:
Insertion point is clean: `maybeEnrichTrackCrop` (ContentView) already extracts a per-track
crop, throttled + kill-switched + deduped. But a fingerprint pass is a NEW per-frame ANE
compute path, and its whole value (does a Vision featureprint separate OUR crops?) is
device-gated — shipping it blind right after the recording-taxes-perception fix repeats the
exact scar. Do it as a focused pass:
1. Its OWN lightweight kill switch (`ENABLE_TRACK_FINGERPRINT`), NOT gated behind the heavy
   VLM crop enrichment; detached Task; once per confirmed track (throttle like M5). It must
   NOT tax perception — verify frames_received/converted hold on a device run.
2. Model choice — `VNGenerateImageFeaturePrintRequest` is the default, BUT its featureprint is
   ~2048 floats > the 512 contract cap. MEASURE elementCount + separation on a few real crops
   FIRST, then choose: (A) fixed-seed random projection to ≤256 (preserves cosine, stays under
   cap), (B) raise the cap (still non-reversible; L1 "small" is a soft target), or (C) a
   distilled ≤256 CoreML embedding (P11 RED branch if the featureprint doesn't separate).
3. Emit `fingerprint` (top-level) + `track_id`; the Mac side above already consumes it.

## Measured ROC
- (device-gated — the walk writes real same/different pairs here and sets the threshold)
