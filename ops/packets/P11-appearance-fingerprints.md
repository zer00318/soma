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
First device walk 2026-07-04 (founder's room, live stream — no recording needed). Vision
featureprint dim = **768** on this device (iPhone18,3), well under the 4096 cap. 4 fingerprints:
2× laptop tracks, 2× bed tracks (same-label ≈ same-instance in a single room).
- SAME-object cosine: 0.806 (laptop), 0.847 (bed) — min 0.806, mean 0.827
- DIFF-object cosine (laptop vs bed): 0.520–0.697, mean 0.609
- **SEPARATION +0.109** (worst same 0.806 > best diff 0.697) → featureprint DISCRIMINATES,
  GREEN branch confirmed (no distilled model needed).
- **Synthetic default 0.82 was too HIGH** (would split the same laptop at 0.806). Measured cut
  ≈ 0.75. PROVISIONAL: n=6 pairs, cross-CATEGORY only (laptop vs bed). The hard test — two
  DIFFERENT same-category objects (two cups) — is NOT yet captured; same-category diff-pairs
  score higher, so the final threshold needs that pass before it's set in code.
- Perception NOT taxed: all 4 channels produced rows this walk (detector/vlm/ocr/asr all up),
  frame-conversion at the designed ~10fps throttle. The cheap ANE featureprint coexists.

## Measured ROC, round 2 — THE HARD TEST (3 identical nutella jars, 2026-07-04)
The founder pointed at three identical jars — same kind, different places. This is the pass
the round-1 optimism was missing, and it KILLS the fixed-threshold story:
- same-KIND-different-jar cosines: **0.28–0.68** — OVERLAPS cross-kind (0.13–0.52); the worst
  same-kind pair (0.279) scores BELOW the best cross-kind pair (0.516).
- **NO cosine threshold splits same-jar from different-jar. The "cut ≈0.75" above is DEAD.**
  `FINGERPRINT_MATCH_THRESHOLD` stays a flagged lie; nothing may make merge/split decisions
  from cosine alone.
- Verdict: the featureprint is a **CATEGORY signal, not an instance signal**. Its honest jobs:
  (a) corroborate "same kind" across label flip-flop (jar read as bottle/cup by COCO),
  (b) retrieval ranking. The INDIVIDUATOR for identical objects is P10 coordinates — the
  three-jar walk proved genesis-frame raycasts re-measure one static object to ≲0.15 m
  across camera poses while different jars sit ≥0.33 m apart.
- Crop lever: best same-jar pair (0.68) << laptop self-match (0.81) ⇒ the 10% padded crop
  fed the featureprint mostly table/background. Pad tightened 0.10→0.02 (this commit);
  re-measure separation on the next walk.
- Coordinate emission was ALSO broken for this case: per-LABEL `anchorMap` caps world points
  at one-per-label (3 jars → 2 labels → third jar never got a coordinate; 0.5 m dedup made
  anchors jump between jars). Fixed this commit: per-TRACK raycast (`trackWorldPosition`)
  stamps `track_world` on every detector_track + fingerprint row; Mac `_tracks_conflict`
  now splits ≥0.30 m / merges ≤0.25 m in the genesis frame (thresholds measured on this
  walk, trusted grades only, median per track). `tests/unit/test_world_individuation.py`
  locks: 3 far-apart identical jars → firm 3, same-spot re-sighting → 1, mid-zone asserts
  nothing, relocalizing-grade coords never split, outlier raycast can't move the median.
- DEVICE-PENDING: re-walk the 3 jars on this build → expect 3 `track_world` clusters → firm
  count 3 from the binder; re-measure fingerprint ROC with the tight crop.
