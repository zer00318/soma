# LOOP LEASH — step back, check for tunnel vision

Run this at the START of every loop iteration (and any time I've spent >1 cycle on one thing).
≤2 minutes. Read the founder's recent messages FIRST, then answer the 7 questions honestly in
the iteration's opening lines. If any check fails, name it and correct course in the SAME turn.

Complements `ops/ANTI_TUNNEL_LEASH.md` (over-narrow vs over-broad); this one is tuned to the
2026-06-30 founder corrections.

## The founder's north star (what "done" means)
A **working prototype** that feels like *magic — "it remembers everything"* — and is:
- **LOCAL**: on-device / lightweight helpers; brain = local Gemma on the Mac. **Frontier (Claude API) is DEAD.**
- **PRIVATE**: raw frames DELETED after perception; only derived text persists. (Mac+stored frames = testing scaffold, not the product.)
- **HONEST**: 0% confident-wrong is the moat — never trade it for a higher score.
- Demoable for KIT Gründerschmiede. The goal is a PRODUCT, not a benchmark number.

## Tunnel patterns this founder has already caught me in
1. **Grinding the noisy eval.** The 21-Q eval has a ±2-3 noise band > any single change's effect. Optimizing it is chasing noise. ("Maybe you're tunnel visioning.")
2. **Wrong config.** Measured on the frontier brain when the product brain is local Gemma; defaulted perception to Mac/gemma when it should be on-device/lightweight.
3. **Analysis instead of building.** Running yet another experiment when the founder said build the product. ("Why're you stopping? /loop till you reach the prototype product.")
4. **Stalling / over-asking** when told to keep going and offload to local LLMs.

## The 7-question step-back (answer every iteration)
1. **PRODUCT or METRIC?** Am I building toward a demoable prototype, or polishing a number the founder doesn't care about?
2. **REAL CONFIG?** Local Gemma brain + on-device/lightweight helpers + frames deleted — not frontier, not Mac-permanent?
3. **MOAT INTACT?** Is the 0%-confident-wrong honesty floor preserved? Privacy boundary respected?
4. **MEASURABLE?** If I claim an improvement, is it OUTSIDE the ±2-3 noise band (n=21)? If not, label it "unmeasurable" and don't bank it.
5. **FOUNDER'S WORDS?** Re-read the latest founder message — am I doing what they asked, or what I find interesting?
6. **OFFLOAD?** Is the heavy work (perception, reasoning) on local Gemma in the background, with me orchestrating light?
7. **STOPPING?** Am I stalling or asking when told to keep going? Default to shipping the next brick.

## Redirect table
- Failing #1/#4 → stop the experiment; pick the next concrete piece of the end-to-end pipeline.
- Failing #2 → switch to local Gemma / on-device / delete-frames before doing anything else.
- Failing #3 → revert the change; the moat outranks the score.
- Failing #5/#7 → do what the founder asked, now.
- Failing #6 → move the heavy compute to a background gemma job; keep my turn light.

## Iteration log (newest first)
- _iter M1 (2026-07-02):_ Canonical ledger M1 DONE+committed (120207b): one count resolver
  (binder+cluster+floor, hedge-on-disagreement), floor unpoisonable, intent family, type
  discriminator. Garage DoD 10/10 / 0 confident-wrong; live store 0 confident-wrong. LEASH:
  caught my own overfit pre-commit (type splitter tuned on clean synthetic broke on real
  capture — the live store is now a mandatory pre-commit check for counting changes).
  Next: M2 identity/fragmentation.
- _iter M0 (2026-07-02):_ Canonical ledger M0 DONE+committed (8a6e34f): unicorn breach closed
  (gate before count fastpath, narrowed count subject, irregular plurals), pytest 211 green at
  HEAD, :8799 zombie dead. DoD measured live (10/10 absent-counts honest, gemma12b). LEASH:
  product ✓ local-config ✓ moat ✓ deterministic-measure ✓. Next: M1 one-counting-path.
- _iter 1 (2026-06-30 ~17:00):_ Built observer (CV triage, 353→28). 27b brain eval in background.
  LEASH: was tunneling on the eval number earlier (founder caught it); corrected to building the
  capture pipeline on the local stack. On config ✓ (local gemma, frames-deleted design), offload ✓.
