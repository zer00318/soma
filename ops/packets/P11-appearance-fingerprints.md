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

## Measured ROC
- (executor writes here)
