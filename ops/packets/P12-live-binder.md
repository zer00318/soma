# P12 — The live binder (instant fusion at the anchor)
wave: W1 · tag: judgment · executor: Fable · depends: P10, P11, P02

## Context (self-contained)
Founder's core correction to the architecture: binding must not wait for sleep. The moment
a frame is perceived, everything the helpers said fuses AT THE ANCHOR — this OCR text
belongs to that object at that spot. Today only OCR→track binding exists at capture
(M4, Swift-side 'label text:' + bound_text) and everything else is sorted out nightly by
`src/trace_memory/store/individuate.py`. The live binder generalizes M4: ALL helper
outputs (VLM description, OCR, specialist results, fingerprint, sound direction if any)
attach to the anchor instantly; same-vs-new is decided live by coordinates × fingerprint ×
time × attributes.

## Laws that bind you
L2: the live binder AUGMENTS raw observations, never replaces them (provenance intact;
sleep reconsolidation can always re-derive from immutable raw). L4: sleep binder remains
the owner of authored counts — the live binder produces bound raw rows + live instance
hypotheses, not authored memories.

## Do
1. Decide placement honestly: phone-side (lowest latency, binds before emission — likely
   right, M4 precedent) vs hub-side at ingest (easier iteration). Document the call.
2. Bind rule v1 (port M2's hard-won lessons — they cost real bugs): same-frame ≤150ms
   different-cell = distinct; same-cell = duplicate box; attribute contradiction
   (weight/volume, colour family) splits; fingerprint distance beyond P11's threshold
   splits; else same. Ambiguity → both hypotheses recorded, low grade.
   **UPDATE from the 2026-07-04 three-jar walks (P10/P11 measured results — supersedes two
   assumptions above):** (a) fingerprint cosine CANNOT split same-kind objects (same-jar
   0.28-0.68 overlaps cross-kind 0.13-0.52) — it is a category/corroboration signal only;
   there is NO P11 threshold to split on. (b) The strongest identity signal is METRIC
   co-visibility from per-track `track_world` stamps: simultaneous raycasts of one jar
   measured 0.000-0.001 m apart across its duplicate/flip-flopped tracks, different adjacent
   jars 0.102-0.127 m — perfectly bimodal (constants `_COVIS_DUP_M`/`_COVIS_SPLIT_M` in
   individuate.py). THE CORE JOB HERE: a GLOBAL identity graph over tracks — union on
   simultaneous-same-place (this crosses COCO label flips: cup-trk-16 = bottle-trk-17 at
   0.000 m), cannot-link on simultaneous-different-place, propagate constraints. Per-label
   buckets in individuate.py cannot represent this; on walk 2 the graph resolves 8 tracks ->
   exactly 3 jars where per-label counting cannot. That graph is what makes "how many
   nutella jars" answer a FIRM 3.
3. Output: observations arrive at the store already carrying anchor_id + bound_text +
   live_instance_hint. Sleep binder consumes hints as evidence, keeps final authority.
4. Regression: the full M2 live-desk results must not regress (mouse 1 FIRM, laptop 1
   FIRM, keyboard/tv ranges, unicorns refused) — rerun on the real store.

## Done when
Live capture of the founder's desk yields bound rows (OCR text attached to the right
object's anchor, VLM description attached to the same instance); M2 regression holds;
pytest + battery hold; INDEX flipped with before/after desk numbers.
