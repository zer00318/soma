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


## Mac core LANDED 2026-07-04 (commit pending gates) — global identity graph in individuate.py
Stage 1 `_mustlink_components`: union tracks ACROSS labels on simultaneous same-place stamps
(all simultaneous pairs <= _COVIS_DUP_M). Stage 2 `_counting_families`: components count
together when same identity label OR overlapping detector-label sets. Never-covisible median
splits are tiered (liberal 0.15 / strict 0.30, measured) so mid-zone separations widen the
honest RANGE instead of asserting. LIVE RESULT on walk 2's jar burst: 8 fragmented tracks
(4 COCO labels) -> EXACTLY the 3 ground-truth jars ({trk-11,14} | {trk-13,15,22,23} |
{trk-16,17}), count [2,3] — hedged only on the one never-witnessed pair (A vs C). Firm 3
arrives when one frame witnesses all three simultaneously; Swift raycast now falls back to
estimated planes (stamp density was 50/~1100 rows) to make that likely on the next pan.
REMAINING for this packet: live (at-ingest or on-phone) binding + instance hints; the sleep
binder consumes the same graph.


## Natural-motion hardening 2026-07-04 (founder correction: adapt to users, not vice versa)
Founder's burst 3 (same 3 jars, NATURAL glancing/walking, world-grade session) broke the
walk-2-calibrated rules and taught the regime-proof set. Measured failures:
- one jar's stamps scattered 0.2-1.3 m ALONG THE RAY (raycast depth junk while moving;
  walk-2 self-spread was <=0.16) -> fixed 0.15/0.30 median thresholds minted phantoms:
  count read [5,8] vs ~3 truth — a FIRM-WRONG (low>truth), the cardinal sin;
- the phone TRACKER drifts across adjacent identical jars (two "dup" track pairs showed
  7-9 deg simultaneous bearing separation = two silhouettes) -> tracks are NOT identity
  anchors near identical items; triangulation over drifting tracks converges to the table
  centroid (0.01 m agreement between tracks that were provably boxing different jars) —
  plausible-but-wrong, caught only by the bearing check;
- the detector double-boxes one close jar up to ~18 deg apart (6 'bottle' boxes in ONE
  frame on the 3-jar row) -> centre-angle alone cannot separate dup boxes from adjacent
  objects at close range; needs BOX EXTENTS (now emitted: box_w/box_h, this commit).
REGIME-PROOF RULES now in individuate.py (honesty-asymmetric: strict/LOW needs proof,
liberal/HIGH splits eagerly — a wide range is vague, a wrong low is a lie):
- DUP: simultaneous 3D <=0.05 m (depth-proof — junk moves both stamps along one ray);
- STRICT split: simultaneous bearings >=20 deg (metric analog of M2's non-adjacent-cell
  rule; dups measured <=18 deg, distinct 20-46 deg) OR stable-stamp medians beyond
  max(0.30, 4x the tracks' own measured noise); scatter (no stable stamps) NEVER testifies;
- LIBERAL split: bearings >=3 deg or medians >=0.15 — widens the range only.
RESULTS: walk 2 partition/count unchanged (3 groups exactly = ground truth, [2,3]);
burst 3 low 5->4 high 8 — low=4 is now a FALSIFIABLE claim (3 jar-zone groups + one
stable track ~30 cm away by the toothbrush/scissors: founder to confirm a real 4th
bottle-kind object there). Pauses tighten counts, sweeps widen them, no choreography.
NEXT LEVEL: instant-disjointness floor from box extents (data flows from next build).
