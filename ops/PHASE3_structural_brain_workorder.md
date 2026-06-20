# Sprint 1 — The Structural Brain (replaces prompt-tuning)

*Authored 2026-06-18 after the prompt-tuning dead-end (cold RAS 15.8→10.5→0.0 as the leash
was tuned; gemma-12B does not reliably obey an accreting rule-prompt). This sprint replaces
the hand-written refusal rule with STRUCTURE. Governed by ROADMAP.md §3 (every miss diagnosed
(A)/(B)) and the founder's law: every sprint ships a capability that holds across ≥2 clips and
is built for the live stream — never a rule tuned to rescue one clip.*

## Why (the evidence)
- The assembler crash is fixed; the brain now sees all channels. The remaining wall is the
  REFUSAL/BINDING decision, currently an unreliable gemma prompt (`verify_grounded` + the leash).
- Two distinct hallucination sources, NEITHER fixable by prompts:
  1. **Perception phantom** (walk): a phantom "train"/wrong bag colour from ONE blurry caption.
  2. **Mis-attribution** (day Q13/17/18): the right token is present but bound to the WRONG
     entity (a stranger's outfit, a clock that isn't the lecture's end, another object's logo).

## The structural mechanism (provenance + confidence + entity binding)
Replace "LLM decides refuse/answer from a wall of rules" with deterministic structure:
- **Provenance:** every remembered fact knows its source (channel, frame t).
- **Confidence by corroboration:** a fact seen in N frames/channels is stronger than a 1-frame
  claim; a fact contradicted by other high-confidence facts is suspect. (Kills phantoms.)
- **Entity binding:** details attach to ENTITY NODES (person / object / screen / place). A
  question about a specific entity retrieves only THAT entity's evidence; if several candidate
  entities fit, the binding is low-confidence → refuse. (Kills mis-attribution.) This is the
  founder's neuron-graph: nodes + weighted edges + activation; decay = retrieval cost, never
  deletion (perfect-recall).
- **Structural refusal:** answer iff a high-confidence, entity-scoped evidence card supports it;
  else honest "I don't know". No prompt rules.

## Increments (each ends with run_live on BOTH day + walk; halluc must trend → 0)
1. **`scripts/evidence_confidence.py`** — DONE (2026-06-18). Deterministic confidence over a
   memory dir. KEY LESSON (found in seconds, CPU): frequency ≠ truth — the phantom "train"
   repeats across 31 caption frames, while the true "Joe" is one ASR segment. So confidence =
   **CHANNEL RELIABILITY** (speech/OCR/screen are verbatim → ~0.9; the 4-bit caption model
   hallucinates → 0.4) **boosted by cross-channel agreement** (caption+OCR → 1.0), NOT frame count.
   Verified on BOTH clips: "Joe" 0.92, "Wilhelm" (caption+OCR) 1.00, phantom "train" (caption-only)
   0.40. A ~0.6 assert-threshold keeps real facts and flags phantoms — by structure, no prompt.
2. **`scripts/entity_graph.py`** — cluster observations into entities (type + lexical + temporal
   co-occurrence), attach attributes WITH provenance + confidence, expose
   `entities_for(question)` and `evidence_for(entity)`. *Verify:* the wearer ("me") is one entity;
   April another; the greeted stranger another — outfits don't cross.
3. **Wire into `ask_home`**: the assembler builds its dossier from entity-scoped, confidence-ranked
   evidence; refusal becomes structural (drop `verify_grounded`'s LLM gate). *Verify:* re-score
   day + walk → hallucination DOWN on both, recall not tanked; (A)/(B) tool + critic confirm.
4. **Self-entity channel** (the wearer) — earned (Q6 outfit). A first-class "me" node so
   "what was I wearing" resolves structurally, not by guessing among people.

## Live-readiness (non-negotiable)
Every piece is O(frames), incremental, and runs on a stream — confidence accrues as frames arrive,
entities update online. The offline 11s/frame captioner is the SUFFICIENCY rig only; helpers go
to the society-of-specialists parallel design (separate workorder) for the live budget.

## Done bar
Hallucination on BOTH clips trends toward 0 with recall preserved, achieved by structure (no
clip-specific prompt rule), and the same mechanism is plausibly real-time. Then Phase 4 re-runs
the cold gate to confirm generalization.
