# TRACE — System Reality, Component Deconvolution & Cockpit Spec
*Author: Chief (Claude). 2026-06-23. Branch `chief/p0-honesty-sprint`. No hand-waving; every
number is read from an artifact or the source. Live state: `ops/cockpit/engine.json` (run
`scripts/cockpit_engine.py`), rendered at `ops/cockpit/cockpit_engine.html`.*

## VERDICT (brutal)
**NOT pitch-ready. One layer is real, two are fragile, one number is untrustworthy.**
- REAL: the honesty moat. Cross-frame OCR consensus → text-recall **47%→60% correct**, hallucination
  **42%→~9–18%**, wired into `ask_home` with refuse-hard. The brain stopped inventing on reading Qs.
- UNTRUSTED: that 60% is on **n=15** founder-gold questions. 1 question = 6.7%. A "boundary pass" on
  n=15 is statistical noise, not a result you pitch. (Mitigation in flight: Munich ~50-Q eval.)
- FRAGILE: live capture rides a **deprecated Quartz API** (the "live-feed window failure"); the brain
  is a **2898-line monolith**; storage is **flat JSON, not a DB**; **zero latency instrumentation**.
- MISREAD TO CORRECT: the "31% hallucination ceiling" you cited is the **broad scene-QA** number
  (always-emitting VLM colour/scene channels). That product was **descoped**. On the narrow text product
  with consensus + refuse-hard, hallucination is ~9–18% strict and the *confident fabrications are gone*.
  Do not pitch a 31% number; it measures a thing we deliberately killed.

---

## TASK 1 — COCKPIT INFORMATION ARCHITECTURE
### 1A. The questions a founder must answer in <5 seconds (and where each lives)
Grouped by decision they drive. Each maps to a field in `engine.json`.

**Pitch-readiness (the only question that matters):**
1. What is the honest North-Star number right now? → `north_star.correct_pc / halluc_pc / gate`
2. Is it trustworthy (n, source)? → `north_star.n`, `.caveat`
3. How far from the gate, and improving or regressing vs baseline? → `.gate`, `.baseline_*`

**Pipeline health (can I demo without it lying or stalling):**
4. Is each stage LIVE / LOSSY / FRAGILE / BROKEN? → `pipeline[].status`
5. Where is latency spent (capture→OCR→consensus→answer)? → `pipeline[].latency_ms` *(UNINSTRUMENTED — blueprint below)*
6. Token→text compression ratio (how much pixel becomes how few tokens)? → *UNINSTRUMENTED — blueprint below*

**Truth/honesty (the moat):**
7. Which channels are self-calibrating vs always-emitting? → `channels[].honesty`
8. What is the live VLM/OCR confidence and is a low-confidence read about to be spoken? → `channels[].confidence` *(VNConfidence available, not yet surfaced)*
9. Refusal rate and refusal *correctness* (refusing what it couldn't read vs over-refusing)? → derive from `north_star.refused` + per-Q verdicts

**Memory/state (is the DB sane):**
10. How many observations stored, mutation state (append-only intact)? → *partial; storage is JSON*
11. Retrieval anchor in use (temporal vs global) and is it contaminating? → recall path flag

**Blockers/decision:**
12. What is the single highest-severity thing between me and a demo, and the fix? → `blockers[]` (P0 first)
13. What is the system waiting on ME for? → `waiting_on_founder`

### 1B. How they integrate visually (the new cockpit, already built)
`cockpit_engine.html` renders `engine.json`. Structure:
- **Verdict banner** (red) — one sentence, the honest state.
- **North-Star card** — big `%correct / %halluc`, gate pill (PASS/BOUNDARY/FAIL), n + baseline delta.
- **Pipeline table** — one row/stage, status pill, latency cell (`⊘ lat` = uninstrumented, honest).
- **Channels table** — honesty class pill (green=self-calibrating, amber=always-emits) = the moat at a glance.
- **Blockers** — severity-sorted cards, each `root:` → `→ fix:` (root cause + blueprint, machine-readable).
- **Waiting-on-founder** strip — the one action that unblocks progress.
Replaces the prior narrative `chief.json` (prose, zero actionable intel). The engine **never fakes a
metric**: anything unmeasured emits `null` + `UNINSTRUMENTED` so the gap is visible, not papered over.

---

## TASK 2 — COMPONENT DECONVOLUTION (exact division of labor)
Data flow: **camera → [capture] → [OCR + scene VLM] → [consensus] → kf_memory → [recall] → answer**.

### Local LLMs (ollama; the only inference, all on-device)
- **gemma3:12b-it-qat (8.9GB)** — LIVE per-frame *perception* during capture: SCENE/OBJECTS/TEXT caption
  (`trace_live_feed.py` PERCEIVE prompt). Fast enough for ~real-time; lossy/always-emits → its colour/scene
  output is **descoped** for text answers.
- **gemma3:27b-it-qat (18GB)** — on-demand *recall* answerer inside consensus (`consensus_read`). Strict
  extraction: "copy the specific value or output NOT IN MEMORY." Recall isn't real-time, so it can afford 27b;
  binds multi-line signs better than 12b.
- **bge-m3 / nomic-embed** — embeddings for semantic retrieve. (ollama embed was broken on this box →
  fallback paths exist.) Role: rank scenes by meaning when token-overlap fails.
- Containment principle: the LLM is held to **strict extraction**, never free-association. The honesty comes
  from the *prompt contract* (verbatim-or-refuse) + the *consensus gate* (≥3 frames or silence), not the model.

### Codebase / deterministic logic (the part that must NOT be a model)
- **Capture orchestration** — `trace_live_feed.py`: Quartz one-window grab, in-mem CGImage, 0-raw-media by
  construction (pixels never hit disk). `build_walk_eval.py` / `extract_frames`: cv2 frame-grab from video.
- **OCR** — `vision_ocr.py`: Apple Vision `VNRecognizeText`, verbatim, deterministic, self-calibrating.
- **Consensus** — `consensus_recall.py` (191 LOC, pure): windowing by timestamp, substring clustering of
  truncated reads, frequency vote, date-shape exception, noise/keyboard-row filter, refuse threshold. This is
  *deterministic regex+counting*, NOT a model — that's exactly why it's trustworthy.
- **Slot extraction** — `structured_recall.py` (481 LOC): regex extractors for identity/institution/dates/IDs
  with repeat-support clustering. The deterministic sibling of consensus for known slots.
- **State** — `kf_memory.json` per capture (flat list of `{t, frame, ocr, caption}`); `world_memory.json`
  (object inventory). **Currently JSON files, not a transactional DB** — a debt (see blockers).

### What I (the AI Chief) do
- Synthesize the streams into a verdict; design the consensus algorithm and the prompt contracts; run the
  A/B mitigation loops (single-frame vs consensus, 12b vs 27b, minrep sweeps); adjudicate honestly against
  founder gold; write the instrumentation; decide scope (kill broad scene-QA, narrow to text). I do NOT do
  bulk mechanical coding the codebase/Codex should own, and I do NOT hand subtle algorithms to blind Codex.

### Where this goes (monolith script → hardened graph assistant)
Target architecture (migration path, not a rewrite-from-scratch):
1. **Typed channel interfaces** — `Perceptor` (frame→observations), `Memory` (append/query), `Recaller`
   (question+anchor→grounded answer|refusal). Extract from `ask_home.py`'s 2898 lines.
2. **A node graph, not one function** — capture → {OCR, scene, detector} → bind → store → on-ask:
   retrieve(anchor) → consensus → verify → answer. Each node is independently testable + instrumented.
3. **A real local store** — SQLite (append-only event log already prototyped) + a vector index (sqlite-vec
   or faiss) for `Memory.query`, replacing per-question JSON scans.
4. **Confidence as a first-class edge** — every observation carries source confidence (VNConfidence, vote
   support); the Recaller refuses below threshold. Honesty becomes an architectural invariant, not a prompt.

---

## TASK 3 — ROADBLOCK AUDIT (root cause → engineering blueprint)
Severity: **P0 = blocks a demo/jury**, P1 = lies or stalls under load, P2 = debt.

### [P0] The number is untrustworthy (n=15)
- **Root:** the 60%/<10% gate is measured on 15 founder-gold questions; one question swings it 6.7%; a
  boundary pass is noise. You cannot put n=15 in front of an EXIST jury.
- **Blueprint:** Munich ~50-Q eval **in flight** — `build_walk_eval.py` ran on a 1080p60 walk, auto-selected
  text-rich frames, gemma-generated reading Qs; founder confirms gold against the embedded video; re-run
  `ocr_recall.py` (27b) for a number with confidence intervals. Then add a *held-out* second walk so the
  number isn't tuned. Target: ≥60%/<10% at n≥50, reported with the refusal-correctness split.

### [P1] Live-capture window failure (deprecated Quartz API)
- **Root:** `trace_live_feed.py` uses `CGWindowListCreateImage` (deprecated macOS 14+). Under Spaces/occlusion
  it returns blank/stale frames → the "live feed window" intermittently dies.
- **Blueprint:** port to **ScreenCaptureKit** (`SCStream` + `SCContentFilter` for the one window); async frame
  callback into the same in-mem CGImage path (0-raw-media preserved); add a watchdog that detects N blank
  frames and re-acquires the window. Keep Quartz as a fallback for <14.

### [P1] Assembler fabricates on non-reading questions (the residual hallucination)
- **Root:** consensus+refuse-hard covers reading/screen Qs *with an anchor*. Questions classified otherwise
  (counting, "lower plaque") still hit the free-form assembler, which guessed `1898-1970`-style sometimes
  right but `June 1901`/`Hi kaife` when wrong. That's the real hallucination source now.
- **Blueprint:** make refusal the default for ANY anchored question lacking grounded support: every channel
  returns `(value, confidence, provenance)`; the Recaller speaks only if some channel clears threshold WITH
  provenance, else refuses. Demote the free-form assembler to a *suggestion that must be verified against OCR*
  before it can be spoken. Measure: hallucination on the full question set, not just the reading subset.

### [P2] Local VLM quantization limit (12b mis-binds multi-line signs)
- **Root:** gemma3:12b-QAT picks the wrong line on dense signs (Q25: returned tram streets, not the BUS line).
  Quantization + small model = weak spatial/semantic binding.
- **Blueprint:** 27b for on-demand recall (already wired; recall isn't real-time). For live capture keep 12b
  but only for the *caption* channel, never the text answer. If 27b latency hurts, evaluate a 14–32b non-QAT
  or an MLX-served model. Track per-channel accuracy so we know which model to route to.

### [P2] 2898-line monolith brain
- **Root:** `ask_home.py` couples routing, retrieval, gates, answer-gen. Fragile; one crash drops every
  question to the narrow legacy path (masking failures as "honest refusals").
- **Blueprint:** extract `Perceptor/Memory/Recaller` interfaces (Task 2 forward path); each node unit-tested
  (`test_consensus_recall.py` is the template — 6 behavior tests, no model needed). Strangler-fig, not rewrite.

### [P2] Zero performance instrumentation
- **Root:** no timing/throughput anywhere; cannot show pipeline latency or token→text compression — both are
  pitch-relevant ("we turn a 1080p frame into ~30 tokens, on-device, in Xms").
- **Blueprint:** a `@span(stage)` decorator writing `{stage, ms, in_bytes, out_tokens, ts}` to
  `ops/cockpit/metrics.jsonl`; `cockpit_engine.py` aggregates p50/p95 latency per stage and the
  compression ratio (pixels in / tokens out). Then fields 5 & 6 above stop being `UNINSTRUMENTED`.

---

## THE PATH TO PITCH-READY (ordered, no fluff)
1. **Trust the number** — finish Munich gold (founder, ~10 min) → ≥60%/<10% at n≥50 + held-out second walk.
2. **Kill residual hallucination** — confidence-gate every channel; refuse-default for unsupported anchored Qs.
3. **Harden capture** — ScreenCaptureKit port + watchdog (kills the live-feed failure).
4. **Instrument** — `@span` + compression ratio, so the demo shows real latency/compression, not vibes.
5. **One retention signal** — does the founder reach for it again on real reads. That, not interviews, is validation.
Only after 1–4 is there a defensible EXIST-jury demo. The honesty story is the asset; everything else serves it.
