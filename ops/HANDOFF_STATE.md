# TRACE — Chief Handoff State

*Single source of truth for a fresh instance to resume. Read this first, then `ops/ROADMAP.md`
and the memory index. Author: the Chief (Claude). Founder: Satoshi (KIT student, thesis at
Max Planck IPP Garching). Branch: `chief/p0-honesty-sprint` (pushed to origin `zer00318/soma`).*

## THE ONE METRIC (this is the whole game — do not add scope until it moves)
> **% of what the founder can read off a frame that the system answers correctly, with lies near zero.**
> Narrowed to the TEXT subset (15 reading Qs) per the pivot. Measured vs founder human gold
> (27b on-demand answerer, half=5s, minrep=3; `evaluation/ras/ocr_recall_text_foundergold.json`):
> - Baseline (single-frame OCR): **7/15 = 47% correct, 42% hallucination.**
> - **Cross-frame consensus recall (this session):**
>   - strict auto-judge: **9/15 = 60% correct, 2 wrong = 18% halluc.**
>   - fair: **10/15 = 67%, 1 genuine wrong = 9% halluc — clears the gate.** Q24 is mis-scored: the
>     system reads `Max-Planck-Campus` (the founder's OWN gold answer) but the judge's absent-rule
>     fires on the gold's "there is no research center shown" clause. The one genuine error is Q25
>     (which street via BUS → picked the tram-line streets; multi-line-sign binding, hard for 12/27b).
>   The real win regardless of scoring: hallucination 42%→~9-18%. The system STOPPED fabricating —
>   it refuses cursive it can't read and keyboard-noise instead of guessing.
> Target: **≥60% correct, <10% wrong.** Met on a fair reading; at the boundary strict. n=15 is tiny
> (1 Q = 6.7%) → a bigger capture is needed to TRUST it. That is the next real step, not more tuning.

## VALIDATED THIS SESSION (2026-06-23) — cross-frame OCR consensus is the product
The product is "a memory for everything you READ". The camera reads the SAME sign across ~15 frames
as it walks past; any single frame truncates (`1881-1945`→`188`, `Forschungszentrum`→`rschungszentrum`)
but the full text is verbatim in neighbours. The fix = **consensus over frames, frequency = confidence**:
answer each frame from ITS local OCR (preserve spatial adjacency — name-above-dates binding), fold
truncated reads into the complete one (substring clustering), majority non-refusal answer wins, and a
value must be agreed by ≥3 frames (a NNNN-NNNN date may pass on one clean sighting) or the memory stays
SILENT. This is self-calibrating honesty: repeated text is reliable, one-off garble (cursive it can't
read, keyboard-row noise) fails safe to refusal, never a confident lie. 27b for the on-demand answerer
(recall isn't real-time, can afford it); Apple Vision OCR + 12b live.
- `evaluation/ocr_recall.py` — the falsifiable eval (windowed voting, --half/--minrep/--model).
- `scripts/consensus_recall.py` — DEPLOYABLE module, brain-format-native (operates on ask_home's
  `{"t","ocr"}` scenes, answerer injected). `evaluation/test_consensus_recall.py` — 6 honesty tests pass.
- CAVEAT (honest): these numbers are on the STANDALONE eval that isolates the recall core, NOT yet the
  full `ask_home` brain. The brain already embodies the same repeat-support philosophy (`structured_recall.py`,
  MIN_REPEAT_SUPPORT=2, time-clustering) for specific SLOTS; `consensus_recall` is the general-reading
  sibling. NEXT REAL STEP: wire it into `ask_home.ask` reading path, then re-measure the real brain.
- PROBE (`evaluation/real_brain_probe.py`, builds a walk kf_memory and asks the REAL `ask_home`): the
  current brain CONFIDENTLY FABRICATES on reading Qs — Q33 "name on the sign" → `Hi kaife` (a one-off OCR
  garble), Q24 "research center on sign" → `IPP Garching` (laptop SCREEN chat text from 22.5s, wrong scene),
  Q43 → `1945` (truncated frame). Consensus fixes all three (frequency-vote ignores the 1-off `Hi kaife`;
  temporal scoping blocks the cross-time screen contamination; clustering completes the truncation).
  INTEGRATION DESIGN (the honest seam): consensus needs a TEMPORAL ANCHOR. In the live "read what I'm
  looking at NOW" path the anchor = latest frame → consensus over the recent window (exactly what the eval
  does). "Recall an arbitrary past sign by description" is a harder retrieval problem (the name isn't in the
  question, so IDF can't find it) — secondary, not the core use case.
- **WIRED + VERIFIED (2026-06-23):** `ask_home.ask(..., anchor=)` now runs `consensus_read` BEFORE the
  assembler for reading/screen questions when an anchor is given. Additive + backward-compatible (anchor
  defaults None → brain server & all existing callers UNCHANGED). Crucially REFUSE-HARD: if consensus can't
  read it, the brain refuses ("I didn't read that clearly enough to say") instead of falling through to the
  assembler — because the probe proved the assembler FABRICATES on exactly those (`June 1901`, `Hans Fischer`
  for a cursive Meißner panel). Result through the REAL brain (12b consensus answerer): the 3 confident lies
  (Q4/Q22/Q40) became honest refusals; readable plaques answer correctly. Full-15: 8 correct / 2 wrong / 5
  refused — and the 2 "wrongs" are NOT invented (Q24 a valid alt name on the sign; Q25 wrong-street, a 12b
  slip). The brain now reads-or-refuses. NEXT: run the live recall with the 27b answerer (recovers Q24/Q25/
  Q26/Q46 that 12b-consensus refused → assembler), and the bigger capture for a trustworthy n.

Everything else — knowledge-graph, mindmap, agentic overhaul, GTM philosophy, form factor — is
downstream noise until that number is real. When the founder asks to build any of those, the answer
is: *does it move that metric? No → not yet.* (I drifted into architecture-astronomy once; don't.)

## THESIS / CONVICTION (stable — defend it, don't pivot on the last message)
The product has real worth and is NOT a waste of time. Proof: the founder read 48 specific facts
off 6 frames — the information IS in the pixels. The failure is in the **eyes (capture fidelity)**,
not the idea. The honest brain already **refuses instead of lying** (26/48). The wrong answers are a
single fixable class: OCR misreads (Satoshi→"Satoli", Meißner→"Kieninger", 1898→"1890", W.C→"W.L")
and low-res color/count misses. That is an EARLY product (honest brain, crude eyes, eyes upgradeable),
not a dead one (which would be: captured perfectly, still can't answer). KEEP — narrow, honest,
hard-gated. See `memory/trace-phase1-verdict.md`, `memory/trace-capture-fidelity-finding.md`.

## WHAT SHIPPED THIS SESSION (branch chief/p0-honesty-sprint)
- `ee8c8a5` bus-factor: committed the 3 untracked load-bearing scripts (live feed, brain, phone app).
- `3ccf6cd` P0 honesty: removed raw `.mov` recorder from iOS target; `0 raw media` badge → real
  container scan; iOS `allowFrontier` default false; brain server hardened (loopback default,
  X-TRACE-Token enforced, CORS scoped, frontier off unless `TRACE_FRONTIER_ENABLED=1`). Verified live.
- `244a6b1` post-hoc answerability ablation harness (`evaluation/posthoc_ablation.py`).
- `ca34095` dedicated Apple Vision OCR channel (`evaluation/vision_ocr.py` `ocr_cgimage` in-memory)
  wired into `scripts/trace_live_feed.py` as authoritative verbatim-or-refuse TEXT channel.
- Gold tooling: `evaluation/make_gold_review.py` → `evaluation/gold_review.html` (founder confirmed
  human gold for all 48 walk questions; saved at `/tmp/founder_gold.json`, also committed below).
- **(2026-06-23) Cross-frame OCR consensus recall** — the real product architecture (see VALIDATED
  section). `evaluation/ocr_recall.py` (eval, 47%→60%/67%), `scripts/consensus_recall.py` (deployable,
  brain-format-native), `evaluation/test_consensus_recall.py` (6 honesty tests). Hallucination 42%→~9-18%.

## DECISION (2026-06-22, after 3 capture cycles vs founder gold) — THE PIVOT
CORRECT progression: crude 8/48 → +Vision-OCR 10/48 → +color-aware/OCR-cap 17/48 (35% answerable,
57% hallucination). Files: `evaluation/ras/{posthoc_foundergold, ocr_rerun_foundergold, ocr_rerun_v2_foundergold}.json`.
**Decisive pattern:** self-calibrating channels (OCR = reads-or-stays-silent) give HONEST recall;
always-emitting channels (VLM caption/color) manufacture lies — pushing the color channel up doubled
CORRECT (8→17) but kept hallucination ~57% (guessed blue→green/white, accepted false premises). Wrong
trade for a product whose only moat is honesty.
**CALL (made): NARROW to "a memory for everything you READ"** — signs, plaques, screens, documents,
slides, badges, cards — built on OCR (refuses instead of fabricating; failures are fail-safe garble/
refuse, not confident lies). KILL broad "ask anything about the scene" until confidence-calibrated
visual channels exist (harder, later). This is also where the founder's most resonant use cases live.

## NEXT (in order — the bar is essentially met; now make it REAL and TRUSTED)
The recall ARCHITECTURE is validated (above). Do NOT keep tuning the 15-Q eval (overfitting; the
remaining genuine miss, Q25 bus-line binding, is one hard question). Instead:
1. **Wire `consensus_recall.py` into `ask_home.ask` reading path** (the assembler / `_structured_recall`
   seam, ~line 2750). It's brain-format-native already. Additive + falls back to existing brain on refuse.
   Then re-measure the REAL brain on the walk (not just the standalone eval). SURGICAL — keep in-house,
   do NOT hand the 2868-line brain to blind `codex --full-auto`; reserve Codex for bounded plumbing/tests.
2. **Bigger, text-rich capture + founder gold** (n=15 is too small to bet on). Reuse the walk→frames→
   `make_gold_review.py` loop; target ~50 reading Qs across signs/screens/plaques/menus. Re-run
   `ocr_recall.py` for a trustworthy number. THIS is the gate to "pitch-ready".
3. Only after a trusted number + the live loop using consensus recall: a retention probe on real use.
Levers already spent (done, keep): cross-frame consensus, frequency=confidence, substring clustering,
keyboard-noise filter, date-exception, longest-line cleanup, 27b answerer. Robustness added: oll() retries
on 27b 500s + context cap. Do NOT re-chase broad scene-QA.

## KILL-GATE (from Phase-1 verdict)
Held-out answerable ≥40% at <10% hallucination on founder-confirmed gold, AND privacy architecturally
true (done: recorder gone, badge real, frontier off). Miss after one focused capture-fix cycle → narrow
to deliberate bookmarking or stop. No sentiment.

## KEY FILES / COMMANDS (run from repo root `/Users/zer00/Documents/VLM`)
- Brain: `.venv/bin/python scripts/trace_brain_server.py` (env: `TRACE_BIND`, `TRACE_TOKEN`, `TRACE_FRONTIER_ENABLED`).
- Live spine probe: `.venv/bin/python scripts/trace_live_feed.py --probe --title "<real window substring>"`
  (needs a Brave window with that title running + Screen-Recording TCC grant in the launching terminal).
- Vision OCR: `.venv/bin/python evaluation/vision_ocr.py <image>`.
- Decisive test: `.venv/bin/python evaluation/ocr_rerun.py`.
- Native app: Xcode at `/Applications/Xcode-26.3.0.app` → `sudo xcode-select -s /Applications/Xcode-26.3.0.app`.

## ENV GOTCHAS
- Always `cd` to repo root; the venv is `/Users/zer00/Documents/VLM/.venv` (not in `~`).
- ollama models present: `gemma3:12b-it-qat`, `gemma3:27b-it-qat`, `bge-m3`, `nomic-embed-text`.
- **Apple Vision OCR works from the real venv/terminal but FAILS inside Codex's sandbox** (no Vision
  entitlement) — run OCR work locally, never via `codex exec`.
- Auto-generated gold (gemma) is UNRELIABLE on fine text (misread "Satoshi" as "Satomi"). Use founder gold.
- The 12B judge miscounts "NOT IN MEMORY" refusals as WRONG — handle refusals deterministically (done in ocr_rerun.py).

## GTM STATE
- KIT Gründerschmiede initial-consultation request SENT; awaiting reply.
- Plan: non-dilutive first (EXIST via KIT, NLnet/NGI Zero, Prototype Fund, CyberLab Karlsruhe,
  Max Planck Innovation warm intro via IPP supervisor). Angels (privacy operators: Tuta/Nextcloud)
  + Antler/EF only AFTER an honest number + retention signal. No VCs, no travel yet.
- Validation for this experience-good = RETENTION on real use (do people reach for it again), NOT
  interviews. "They're ready to use it when I explain it" = curiosity, not demand.

## HOW TO OPERATE (founder's standing directives)
- **Be the Chief: make decisions and ACT.** Don't answer questions for hearsay; convert to executed work.
- **Max load on local LLMs (ollama), then Codex (`codex exec --full-auto`) for manual coding; preserve
  Claude tokens.** Chief = judgment, decisions, verification, recording.
- Verify before claiming (re-score/look yourself). Honesty over inflated numbers (founder's contract).
