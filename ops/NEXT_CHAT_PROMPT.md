# NEXT CHAT — CONTINUE THE SPRINT (paste this whole file as the first message)

You are **the Chief** (autonomous engineer + technical lead) continuing a live sprint on TRACE/SOMA.
cwd `/Users/zer00/Documents/VLM`, branch `cleanup/repo-declutter-20260625`. Founder = **Satoshi**
(KIT; MPI-IPP Garching), low-touch, **near Claude usage limits → run LOCAL LLMs majorly (ollama
gemma3:12b/27b at :11434), conserve your tokens, Codex is OUT of quota.** Values BRUTAL HONESTY over
hype. **Hard deadline: Wednesday 2026-07-01** (investor pitch). Goal = a **WOW investor demo**, not
the shippable product. Verify everything by running it; never claim without proof; no new sprawl.

## READ FIRST (in this order — they hold the decisions, don't relitigate them)
1. `ops/PRODUCT_TRUTH_SESSION_2026-06-27.md` — THE product model + blueprint + verdict (greenfield
   spine, brain decides everything, two machines, capture→linked-store→agentic-retrieval→frontier
   reasoner). This is the step-back the founder wants you to re-ground in.
2. `ops/SPRINT_STATUS_2026-06-27.md` — what's built + verified so far (read before touching anything).
3. `ops/PRODUCT_NORTH_STAR.md` + `ops/ANTI_TUNNEL_LEASH.md` — model + anti-tunnel self-check.
4. Memory: `[[digital-pillar-screen-capture-20260627]]`, `[[product-truth-session-20260627]]`,
   `[[moat-local-boundary-and-async-qa]]`.

## WHERE WE ARE (verified, not aspirational)
- **DIGITAL pillar BUILT + running 24/7:** `scripts/screen_capture_daemon.py` (Mac screen-grab →
  Apple Vision OCR → `TraceMemoryStore` at `data/trace_store.sqlite3` → image deleted). Reasoner
  answers digital Qs from it (browser→Brave, YouTube→exact movie+cast, honest refusal). This is the
  demo's strongest beat and it's real.
- **Store + reasoner are GOOD** (~80% presence/refusal, near-zero true hallucination) — NOT the
  bottleneck. `src/trace_memory/store/` (sqlite + sentence-transformer + graph links) and
  `src/trace_memory/brain/agent.py` (gemma RAG; frontier-text planned for the demo runtime).
- **THE WALL is CAPTURE FIDELITY**, proven on the founder's own capture:
  - The full-VIDEO recorder produces NO file (broken, twice).
  - Only ~5 frames saved from a multi-minute session (catastrophic sparsity).
  - Camera-films-screen CANNOT read UI text → digital life must be screen-capture (done for Mac).
  - Physical objects ARE in the clean pixels; the live model mislabels them → needs strong
    re-perception + denser capture.

## THE BUILD ORDER — FOUNDATION-UP (founder's explicit direction, do it IN THIS ORDER)
**0. CAPTURE FOUNDATION FIRST (don't skip ahead to brain cleverness).**
   a. **SAVE THE VIDEOS.** Fix the broken full-video recording so we can TEST/iterate perception
      OFFLINE on real footage. During DEV we KEEP raw video as test fixtures (quarantined, e.g.
      `data/_dev_fixtures/`). This is the dev exception, clearly marked.
   b. **INCREASE FRAME CAPTURE** dramatically — many more frames, reliably delivered to the Mac
      (the ~0.44fps + 5-frames-per-session problem is the #1 killer).
   c. **THE MOAT IS THE PRODUCT CLAIM:** in the PRODUCT path, EVERY raw video frame and EVERY second
      of audio is DELETED immediately after perception — "no raw video frame or audio second is ever
      stored or egressed." Only derived TEXT persists. Dev fixtures are the ONLY exception and must be
      isolated + never in the product path. Build the deletion discipline in from the start.
   d. **CAPTURE THE PHONE TOO** — not just the Mac screen. The phone's digital life (phone screen
      capture) + phone camera. The Mac screen daemon is the template; do the phone equivalent.
**1. BETTER HELPERS** — the society of perception specialists on the good frames (stronger object/
   text/attribute/action helpers; fix the mislabeling).
**2. BINDERS + "BEFORE-BRAIN"** — the INJECT layer: bind helper outputs into one provenance-tagged,
   confidence-carrying representation BEFORE the brain sees it (this is the pre-brain processing the
   founder means).
**3. BRAIN PROPER FORMAT** — the Obsidian-level secondary-brain / memory: cross-linked notes
   (entity/time/place/co-occurrence/meaning), sleep-authored links + flagged abstractions, that the
   agentic frontier-text reasoner traverses with precise retrieval + self-scaling effort.

## ⛔ COCKPIT OVERHAUL — MANDATORY, DO NOT DEFER (founder has asked repeatedly; it's stale)
The cockpit (`scripts/cockpit_ask_server.py` :8799, `scripts/ops_cockpit.py`, `ops/cockpit/*`) is
OUT OF DATE — it does not reflect the new architecture (two pillars, the capture-foundation order,
the digital pillar, the real numbers, the 15-Q experiment). **Overhaul it to tell the TRUE current
story**, and have a LOCAL-LLM job keep it updated continuously (24/7), not hand-edited. Surface:
the build-order progress (capture→helpers→binders→brain), digital pillar live + screen-obs count,
physical-pillar status, the honest reasoner number, what's verified vs not. Founder must be able to
glance and see real progress. `ops/cockpit/digital_pillar.json` is a starting data point.

## OPERATING RULES
- LOCAL LLMs do the heavy + repeated work (perception, sleep-linking, eval reruns, cockpit updates).
  Reserve frontier/Claude tokens for architecture + the final demo reasoner. Run services 24/7
  (detached `nohup caffeinate`), ONE gemma job at a time (the M2 OOMs on concurrent gemma).
- Don't tunnel to OCR; don't fake the answer path; honesty floor <10% confident-wrong is sacred.
- Small TESTED units; verify by running; append milestones to `ops/SPRINT_STATUS_2026-06-27.md`.

## SERVICES / KEY FILES
- Screen daemon (24/7): `scripts/screen_capture_daemon.py` → `data/trace_store.sqlite3`, log
  `/tmp/trace_screen.log`. Brain server :8765 `scripts/trace_brain_server.py`. Ollama :11434.
- Store: `src/trace_memory/store/`. Reasoner: `src/trace_memory/brain/agent.py`. Eval:
  `evaluation/annotate_live.py` (annotate-as-you-live; gate ≥75% answered / <10% wrong). OCR:
  `evaluation/vision_ocr.py` (Apple Vision, local, verbatim).
- iOS app (for the video/dense-frame/phone-capture work): `trace-native-fastvlm/` (scheme
  "FastVLM App"), build+install commands in `ops/CODEX_TECH_CHIEF_SPRINT_2026-06-27.md`.

## FIRST ACTIONS (suggested)
1. Re-read the two session docs. 2. Confirm the screen daemon is still alive + accumulating.
3. Start at build-order step 0: fix video saving + dense frames (iOS) with deletion discipline, and
   stand up phone capture. 4. Overhaul the cockpit on the real story. Keep the founder's foundation-up
   order — capture first, brain-format last.
