# TRACE — Chief Handoff State

*Single source of truth for a fresh instance to resume. Read this first, then `ops/ROADMAP.md`
and the memory index. Author: the Chief (Claude). Founder: Satoshi (KIT student, thesis at
Max Planck IPP Garching). Branch: `chief/p0-honesty-sprint` (pushed to origin `zer00318/soma`).*

## THE ONE METRIC (this is the whole game — do not add scope until it moves)
> **% of what the founder can read off a frame that the system answers correctly, with lies near zero.**
> Today (vs founder human gold, crude pipeline): **~17% answered, ~26/48 honest refusals, ~11/48 wrong.**
> Target: **≥60% answered, <10% wrong.**

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

## NEXT (the narrow product's bar)
Make TEXT-recall clear **60% correct / <10% wrong** on the text-question subset (today 7/15=47%; failures
= OCR truncation + dense-UI dumps, both fixable). Levers: OCR tuning (truncation/orientation), a dense-UI
"summarize screen" mode, confidence gating (state a fact only when its channel is confident). Build the
text-recall capture+recall loop; delegate mechanical coding to Codex, inference local. Do NOT re-chase
broad scene-QA.

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
