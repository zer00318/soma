# PRODUCT NORTH STAR — TRACE
*Canonical. Read this FIRST — before the leash, before any build, before any blueprint. If another
doc contradicts this, this wins. Written 2026-06-24 after the founder corrected the Chief THREE times
in one session for shrinking the product. The lesson is encoded here so it never has to be a fourth.*

---

## 1. What the product IS
**Open-domain question answering over your own lived experience.** The device captures rich DERIVED
context of what you saw and heard (never raw media). Later you ask *anything*. It answers from what
was actually observed — **binding** the pieces into understanding — and honestly **refuses or hedges**
what it didn't capture.

It is NOT OCR. NOT a search engine. NOT a general assistant. It is a **faithful, bound, honest memory
of subjective experience**, private by construction.

The set of answerable questions **cannot be enumerated at capture time.** Walk past a restaurant and
you might later ask about its menu, its typeface, where else you saw that name, or what a stranger
nearby was drinking. The system has no idea which. So nothing about it can be a fixed schema.

> **Anti-fixation rule:** every example in this doc (and every example the founder gives) is an
> ILLUSTRATION of a principle, never the spec. If the question were different the solution would be
> different. Solve the principle, never the instance. The founder has said "don't fixate on this
> example" repeatedly — heed it.

---

## 2. The principle that orders everything: IRREVERSIBILITY
The moment happens once and is gone forever. The world persists and can be queried any time. That
asymmetry **forces** the priority — it is physics, not preference:

- **Capture richness is PRIMARY.** Extract everything you possibly can at the moment —
  *speculatively over-complete* — because the question that needs it hasn't been asked yet and the
  moment will never return.
- **World-reach is the BACKSTOP.** Only for what capture missed, because the world is still there to
  query later. It is the LLM thinking outside the box when the helpers fell short — NOT a co-equal
  axis. (An earlier Chief framed capture and world-reach as "two axes that compound." Wrong. Strict
  priority ordering.)

**More helpers / richer context is ALWAYS better and is PRIMARY** — with one sharpening (see §4):
richness only helps if it is *bound*.

---

## 3. The architecture: HELPERS → INJECT → LLM
Three layers. Get their roles exactly right — the Chief mis-cast INJECT twice; this is the corrected
definition.

### HELPERS — extract (open-ended society of specialists)
An **open, growing** society of parallel aspect-specialists, each turning one slice of perception into
a derived signal: VLM scene description, OCR text, object placement, permanence, spatial, temporal,
textural, emotional/affect, audio/speech, action, self/wearer — **and many, many more we have not
discovered yet.** Naming a finite list is the limiting trap; the list ends in "…and more" and we mean
it. We find a missing aspect two ways: (a) a question *breaks* and reveals the gap, or (b) exhaustive
research enumerates candidate aspects, we build helpers for them, and stress-test what breaks.
A helper EXTRACTS. It does not bind.

### INJECT — bind (the binding brain) ⟵ THE PIECE THAT WAS MISUNDERSTOOD
INJECT sits **between the helpers and the LLM**. It is **a brain of its own that does NOT understand
nuance** — its single job is to **BIND** the many disconnected helper outputs into one coherent,
**provenance-tagged, confidence-carrying** representation (a scene graph / bound event stream) so the
actual brain receives *proper, organized information* instead of a pile of loose signals.

- **Binding = deciding which attributes / utterances / objects belong to which entities, across space
  and time** — and across frames (stable identity / re-identification).
- **Bind AT CAPTURE.** The iPhone is plugged in; compute is available; thermal is secondary (§6).
- INJECT must bind **conservatively** (only relations backed by spatial/temporal co-occurrence above a
  confidence), **mark speculative bindings as speculative**, and **never collapse provenance** — every
  bound fact keeps its source helper(s) and a binding confidence. (Binding is itself inference and
  therefore a hallucination surface — see §5.)
- World-EXPAND / agentic world-reach is **one tool** INJECT/LLM may use as the backstop — it is NOT
  INJECT's identity. (The `inject_expand.py` EXPAND/TIER/COMPILE work is a real, useful *part* of this,
  but INJECT is fundamentally the BINDER, not the expander.)

### LLM — think (the actual brain)
Does the nuance and reasoning over the bound representation. **Plans its own path per question** — no
hard-coded question-type router (that was naive schema-thinking moved to the query side). Reaches into
the world only when capture didn't hold the answer. Answers ONLY from sufficiently-confident bound
evidence; refuses or hedges otherwise; keeps the zones fenced: **observed / inferred / world /
reconstructed-from-world** never blend into one another. That is "the whole reason for a damn LLM."

---

## 4. The sharpening of "more is better": BOUND richness
More *independent* tags is not better — it is a **larger hallucination surface.** The hard questions
never fail for lack of one more detector; they fail because an attribute bound to the wrong entity or
an utterance to the wrong speaker. So the real axis is **bound richness**, and a helper that adds an
*unbound* attribute is a net negative until something binds it. Binding is the hard half and the
valuable half. This is why INJECT (the binder) is load-bearing, not decorative.

---

## 5. Limitations & where we can FAIL (be honest — this is not theater)
1. **The honesty frontier gets HARDER as context gets richer.** More bound, fluent context →
   more *convincing* confabulation when a question reaches past what was captured. Richness and
   honesty pull against each other at the edge. Defense: INJECT propagates **binding confidence +
   provenance** into the LLM, and the LLM is **structurally** forced to answer only from
   sufficiently-confident bound evidence. Strip the certainty out during binding and the brain cannot
   know what it's allowed to say.
2. **INJECT is a second hallucination surface.** Binding is inference. Over-binding injects fabrication
   *upstream* of the brain, which then reasons perfectly over a lie with no tell. Bind conservatively;
   mark speculation.
3. **The unrepresented-aspect question.** A question needs an aspect no helper captured — and the
   moment is gone (irreversible). The system MUST detect "I never captured that" and refuse, not
   confabulate from adjacent signals. This gap is permanent and unbounded ("many many more"); the
   discipline is *detecting the edge of capture*, not pretending to eliminate it.
4. **Cross-time identity binding** (re-identification): "same person 30s later," "where did I see this
   before." Mis-ID across time = mis-binding across time. Its own hard problem.
5. **Worst-helper ceiling:** the bound representation is only as good as the weakest helper on the
   critical path. One garbled OCR / mislabeled object poisons the bind. Needs per-helper confidence +
   cross-helper corroboration (the consensus primitive) so no single helper poisons the brain.
6. **The number is still UNMEASURED.** The grandest failure: build this whole spine and still be ~40%
   on real held-out questions and never know, because the pitch *wow* is not the product *truth*.
   n=15 proves nothing. This remains THE gate.

---

## 6. What's PRIMARY vs SECONDARY (so the next Chief doesn't tunnel)
- **PRIMARY now:** capture richness (more *bound* helpers), the INJECT binding brain at capture, the
  honesty frontier, and the trustworthy number.
- **SECONDARY / later:** eyewear, thermal/battery scheduling, hardware. The iPhone-always-plugged-in
  is the current target. (The Chief once made the thermal scheduler "the spine" — that was an
  over-rotation. Hardware constraints must NOT shrink the pitch.)
- **The pitch is the WOW of the architecture** — that it remembers, binds, understands, and refuses
  honestly. Not thermal, not battery, not hardware.

---

## 7. Privacy line (precise)
- **Inviolable:** no raw video frame and no second of audio is ever stored or leaves the device.
- **Free:** derived TEXT (scrubbed referent strings, queries) MAY leave the device, be
  cross-referenced, and drive world lookups. Egress per se is not the violation; **raw-media
  capture / storage / transmission is.** So background auto-enrichment + explicit gated live search
  are both on-brand.
- Scrub / generalize location-linked referents before egress (a location+time string is a movement
  fingerprint). The PII scrubber is the seam; it is wired and tested.

---

## 8. The two deliverables (unchanged — the goal lock)
1. A **flawless 3-minute investor demo** that makes the paradigm undeniable (the architecture's wow).
2. A **trustworthy, honest number** on real held-out use (real n, lies near zero). This is the gate to
   a pitch-ready *product*, which is DISTINCT from the demo.

---

## 9. Status: VERIFIED vs ASPIRATIONAL (no roadmap-dressed-as-done)
- **Verified:** cross-frame consensus OCR recall (text subset); EXPAND hallucination-gate (n=4
  adversarial audit on real gemma); PII scrub wired into both storage seams + tested end-to-end.
- **Built, small-n:** `ask_with_understanding`, the ~12-channel fuse in `ask_home.py`.
- **NOT yet built as described here:** the bind-at-capture **scene-graph INJECT** (current INJECT is
  partial — FUSE/EXPAND only, no full binding); cross-time identity; the open-ended helper-discovery
  loop; the honest number at n≥50 with human gold.
- Read alongside: `ops/ANTI_TUNNEL_LEASH.md` (the self-check), `ops/SOVEREIGN_STATE.md` (resume
  anchor). Memory: [[product-extent-do-more-not-less]], [[anti-tunnel-leash]],
  [[injection-layer-standing-ground]], [[trace-society-of-specialists]].
