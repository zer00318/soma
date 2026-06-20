# Sprint 2 — Entity-Centric Capture (the real mis-attribution fix)

*Authored 2026-06-18 after Sprint 1 proved mis-attribution is NOT fixable in the brain. The
per-frame caption already mixes "a person in green, a person in pink, a backpack reading North
Face" — WHO wore what is lost at capture, so no downstream gate/graph can recover it (the
entity-graph gate confidently bound "what was HE wearing" → self, "the mate's logo" → whiteboard).
Fix the SOURCE. This is the first concrete member of the society-of-specialists
([[trace-society-of-specialists]]).*

## Goal
Bind attributes to the RIGHT entity AT CAPTURE. Replace the loose "list all objects/colours"
caption with ENTITY-CENTRIC extraction: each distinct person/object emitted WITH its own
attributes, so the brain reasons over already-sorted entities.

## Build (local, recorded-clip phase — GPU serial)
1. **`scripts/build_entity_capture.py`** — per salient keyframe, one Qwen2.5-VL call that returns
   STRUCTURED JSON, not prose:
   - persons: `[{appearance: "<distinguishing>", clothing:{top,bottom,colors}, accessories:[...],
     holding:[...], position:"left/center/right"}]` — each person a SELF-CONTAINED record.
   - text_objects: `[{object, logo_or_text}]` — a logo bound to ITS object (backpack vs shirt).
   - is_self_view: bool + self_attributes when the wearer's own body/hands are in frame.
   (One VLM call/frame; the binding happens INSIDE the model's look, where the pixels still say
   who-wore-what. This is the key move.)
2. **Cross-frame re-ID** — merge per-frame person records into persistent entities by appearance
   similarity + temporal continuity (cheap, CPU). Output `entity_centric.json`:
   `[{entity_id, type, attributes:[{attr,value,frames,confidence}], mentions:[t]}]`.
3. **Feed it to `entity_graph`** — build_entities consumes `entity_centric.json` (already-bound)
   instead of re-deriving from mixed captions. binding_confidence then resolves real referents.

## Verify (the no-bandage proof)
Rebuild the day clip → assert: the greeted guy (green tee + black shorts) is a SEPARATE entity from
April (pink "Breakfast Club"); the backpack's "North Face" is bound to the backpack, not offered as
the fist-bump mate's logo. Then re-score BOTH clips: Q13 answers green/black-shorts OR refuses (never
"pink"); Q9 (April) and Q6 (my outfit, via self) hold; hallucination DOWN on both, recall not tanked.
ALWAYS verify live (ask_home.ask) + gold re-score — agent self-tests are NOT proof (see
[[trace-verify-agent-output-and-capture-binding]]).

## Live-readiness
One structured VLM call per SALIENT frame (not every frame) + cheap re-ID — fits the real-time
society-of-specialists budget. The offline rig runs it on all keyframes for the sufficiency proof.

## Done bar
Mis-attribution hallucinations (day Q13/Q18; the walk's wrong-entity cases) drop to ~0 because the
binding is correct at the source, verified on ≥2 clips, with a path that runs live.
