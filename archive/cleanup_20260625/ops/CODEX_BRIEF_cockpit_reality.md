# CODEX BRIEF — Honest cockpit reality surface

You are updating the cockpit so the founder can see, in ~20 seconds, the TRUE current state of the
prototype and a REALISTIC projection. The founder's explicit ask: "update my cockpit with realistic
projections so I can understand where the prototype is and how we're progressing." Months of work,
repeated tunnel vision — so the #1 rule is HONESTY, not a flattering number.

## Read first (source of truth — do not contradict these)
1. `ops/PRODUCT_NORTH_STAR.md` — the corrected product + architecture model. THE authority.
2. `ops/ANTI_TUNNEL_LEASH.md` — the honesty discipline (no "done" on cherry-picked evidence; no
   roadmap-dressed-as-done; secondary constraints must not shrink the primary product).
3. `ops/cockpit/engine.json` and `ops/cockpit/cockpit_engine.html` — the EXISTING reality surface
   (schema + renderer). Learn how it is structured and how it is served.
4. `scripts/cockpit_ask_server.py` — how the cockpit serves pages/JSON (find how the engine page is
   reached; wire the new content so it actually DISPLAYS, not just sits in a file).

## What to produce
Update `ops/cockpit/engine.json` and its renderer `ops/cockpit/cockpit_engine.html` so the cockpit
honestly shows ALL of the following. Preserve existing top-level keys where compatible; ADD the new
sections. Keep the renderer readable at a glance (a founder, not an engineer).

### A. Architecture (one line + the 6-stage pipeline)
One-liner: "HELPERS extract (open-ended) → INJECT binds at capture into a provenance+confidence
scene/event graph (the binding brain) → LLM thinks and refuses past the edge of capture. Capture is
primary (the moment is irreversible); world-reach is the backstop."

Render the pipeline as 6 stages, each with a `state` in {built, partial, not_built, unverified} and a
short honest note. USE EXACTLY THESE STATES (do not upgrade them):
- **0 Frame & Sync** (space-time frame: timestamped pose · clock · place) — `partial`: native capture
  has time + GPS/geocode; per-observation 3D pose-anchoring (ARKit) is NOT wired.
- **1 Detect & Localize** (detection / OCR / speech → boxes) — `partial`: native detector+OCR+speech
  proven in Munich 2026-06-04 (vision 102, detector 29, speech 1); 3D-anchoring of boxes NOT done;
  OCR acceptance was 0 in the last run and needs a fix.
- **2 Track & Identify** (persistent entity IDs, re-ID, diarization) — `not_built`: the fusion digest
  has frequency/seen-counts, which is NOT true cross-frame identity binding.
- **3 Bind / INJECT** (scene-graph binding with confidence) — `not_built`: `inject_expand.py` is
  FUSE/EXPAND only, NOT the binding brain. **This is THE primary gap / next build.**
- **4 Enrich** (VLM caption · emotion · world-EXPAND, written onto entities) — `partial`: EXPAND is
  built and hallucination-gated (n=4 adversarial audit on real gemma, refute-by-default corroboration
  killed a confident fabrication "ZLORPTECH" at conf 0.95); emotion/affect NOT built.
- **5 Reason / LLM** (ask_home brain; honesty gates S1/S2/B1) — `built` but small-n.

### B. What is VERIFIED (with the caveat — never a bare number)
- Cross-frame consensus OCR recall (TEXT subset only): 47%→60% strict / 67% fair; hallucination
  42%→~9–18%; **n=15 (small)**. Module `scripts/consensus_recall.py`, wired into `ask_home`.
- EXPAND hallucination-gate: n=4 adversarial audit on real gemma; recognize-or-stay-silent.
- PII scrub: wired into BOTH storage seams (live ingest + demo build) + tested end-to-end
  (`test_scrub_wiring.py`, `test_scrub_pii.py`). Privacy line = no raw media stored/leaves.

### C. The honest number (the gate to a pitch-ready PRODUCT)
n=15, 60% correct, 18.2% hallucination (wrong/answered), gate = BOUNDARY (def: ≥60% correct AND <10%
hallucination). Caveat: small n; standalone recall eval, NOT the full brain. Baseline 47%/42%.
**THE GATE: n≥50 held-out with human gold — UNMEASURED.** Make this prominent.

### D. The two deliverables (state each honestly)
1. Flawless 3-min investor demo — **essentially READY** (curated `demo_cache` beats, instant,
   grounded, honest privacy footer; the "wow" of the architecture).
2. Trustworthy honest number — **NOT MET** (the gate in C).

### E. Realistic projection (label it a projection; no fake precision)
Recompute git branch / commits-ahead-of-main / dirty-file count live (`git`). Primary remaining build:
Stage 3 binding → Stage 2 identity → calibrated binding-confidence + conformal/selective abstention →
then the big-n eval (which needs a founder capture + human gold). Give an HONEST range or an explicit
"blocked on big-n capture (needs founder)", NOT a single false-precision day. State the current
verdict: "Demo essentially ready; product number untrusted (n=15) — the binding brain (Stage 3) and a
big-n eval are the gates."

## HONESTY RULES (hard)
- Every state ∈ {built, partial, not_built, unverified}. If you are unsure → `unverified`. Never
  upgrade a state to look better.
- No number without its caveat. Do NOT claim the binding INJECT exists — it does not.
- The DEMO being ready is NOT the PRODUCT being ready — keep them visibly separate.
- Do not invent milestones, dates, or metrics not given here or computed from the repo.

## Verify before you finish (and report what you did)
- `python -c "import json; json.load(open('ops/cockpit/engine.json'))"` parses.
- The cockpit serves the engine page (the server is running on :8799). Confirm HTTP 200 and that the
  new pipeline + deliverables + honest-number sections are present in the served HTML.
- Output a short summary: files changed, the final pipeline states, and the verdict line. Do not
  overstate — if something could not be verified, say so explicitly.
