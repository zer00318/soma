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
3. Output: observations arrive at the store already carrying anchor_id + bound_text +
   live_instance_hint. Sleep binder consumes hints as evidence, keeps final authority.
4. Regression: the full M2 live-desk results must not regress (mouse 1 FIRM, laptop 1
   FIRM, keyboard/tv ranges, unicorns refused) — rerun on the real store.

## Done when
Live capture of the founder's desk yields bound rows (OCR text attached to the right
object's anchor, VLM description attached to the same instance); M2 regression holds;
pytest + battery hold; INDEX flipped with before/after desk numbers.
