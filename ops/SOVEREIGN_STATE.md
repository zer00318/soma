# SOVEREIGN STATE — autonomous orchestrator resume anchor
*Read `ops/PRODUCT_NORTH_STAR.md` FIRST (what the product IS — the corrected model), then
`ops/ANTI_TUNNEL_LEASH.md` (how to not tunnel), then THIS (where we are). Most recent [STATE_MANIFEST]
at the BOTTOM. Branch chief/p0-honesty-sprint.*

> **Architecture in one line (corrected 2026-06-24):** HELPERS extract (open-ended society) → INJECT
> BINDS them at capture into one provenance-tagged scene/event representation (the binding brain) →
> LLM thinks over it and refuses honestly past the edge of capture. Capture richness is PRIMARY
> (the moment is irreversible); world-reach is the BACKSTOP. Pitch = the architecture's wow, not
> hardware. Privacy line = no raw MEDIA stored/leaves; derived TEXT is free.

## Mission
A pitch-ready [Context → Prompt → Answer] ambient-memory prototype. Target = a flawless, zero-latency
3-minute investor demo of the paradigm (see Red-Team verdict: bulletproof DEMO, not a perfect general product).

## Standing facts (don't re-derive)
- Brain: `scripts/ask_home.py` (gemma3:12b via ollama). Honesty fixes live & verified: S1 consensus-default
  + token-aligned merge, S2 `premise_gate.py` stand-your-ground, B1 assembler absence-guard. ~40% on open Qs.
- Brain server (phone): `TRACE_BIND=0.0.0.0 TRACE_BRAIN_PORT=8765 .venv/bin/python scripts/trace_brain_server.py`.
- Cockpit demo: `.venv/bin/python scripts/cockpit_ask_server.py` → :8799 (+ LAN). Layman page + curated chips.
- Native app: `trace-native-fastvlm`, on the iPhone 17 (D3A506B2…) signed under Personal Team
  zer00318@proton.me (LXAAJP44KG). FRAGILE: hub IP hardcoded, LAN IP roulette (192.168.50.250 ↔ 172.20.10.6).
- Founder-walk memory (demo corpus): `/tmp/ocr_memory.json` (979 lines, 185 frames). Cockpit uses it when live idle.
- Codex CLI: `codex exec --sandbox workspace-write -c approval_policy=never - < brief.md` (no ollama in its sandbox).
- Local LLMs: ollama gemma3:12b-it-qat, gemma3:27b-it-qat. Verify everything yourself (agent self-tests ≠ proof).

## Demo script (the 3-min paradigm, scripted + to be made zero-latency)
1. READ: "What years next to Robert Sauer?" → 1898-1970 (it remembered what it saw)
2. MEANING (cross-lingual): "What did Röntgen discover?" → X-rays, read off the German sign
3. HONESTY: "What was the wifi password on the wall?" → "I don't have that" (won't make it up)
4. STAND-YOUR-GROUND: "Was that plaque dated 1899?" → "No — I read 1881-1945" (won't be gaslit)
5. (stretch) ENRICHMENT: a sign → what it IS (EXPAND, not built; pre-compute one for the demo)

---
[STATE_MANIFEST]
- cycle: 1 (2026-06-24)
- micro-milestone: Initialize sovereign engine; build the ZERO-LATENCY demo answer cache (instant scripted Q&A).
- architecture version: v0.1 — Context(founder-walk OCR) → Prompt(ask_home assembler+consensus) → Answer(gemma3:12b), honesty gates S1/S2/B1. Demo surface = cockpit :8799.
- next 3 autonomous actions:
  1. Codex: add demo-cache instant-serve to cockpit_ask_server.py (reads ops/cockpit/demo_cache.json; exact/normalized hit → instant, else live).
  2. Local brain: pre-compute the 5 scripted demo answers → ops/cockpit/demo_cache.json (one-time, then taps are instant).
  3. Verify zero-latency (curl timing < 50ms on cached Qs) + screenshot; then harden the stand-your-ground answer if it didn't fire.
- roadblock being cleared: 18s/answer gemma latency makes any live demo unwatchable → pre-compute scripted answers for guaranteed zero-latency (RULE 4 demo-god / ring-buffer substitution).

---
[STATE_MANIFEST]
- cycle: 2–3 (2026-06-24) — DONE
- micro-milestone DONE: ZERO-LATENCY bulletproof demo engine. demo_cache.json (6 grounded beats) served instant
  (~1ms, was 18–48s) via cockpit cache layer; chips == cache keys so every tap is curated+instant. Added the
  enrichment "magic" beat (read name → who they were, two-zone honest seam) + honest privacy footer. Wrote the
  3-min narration `ops/PITCH_DEMO_SCRIPT.md`.
- arch version: v0.2 — Context→Prompt→Answer with a demo-cache fast path (instant, curated, grounded) in front of
  the live brain (real fallback). Demo surface = cockpit :8799.
- VERDICT: the CONTROLLED 3-min demo is essentially pitch-ready (instant, correct, paradigm beats, honest). The
  general product is still ~40% (roadmap). These are different deliverables — the demo is the ask; the product is next.
- next 3 autonomous actions:
  1. Codex: build a REAL `scripts/scrub_pii.py` (emails / phone+ID number runs / obvious PII → redacted, with
     unit tests, NOT enabled on the public-sign demo corpus) so the privacy claim becomes literally true.
  2. Harden the demo's resilience: a tiny supervisor so cockpit+brain auto-restart (survive the 5h/reset), and a
     network-independent demo (cockpit on localhost needs no hotspot IP).
  3. Re-measure the live brain honestly (n≥the walk) to quantify the real-product gap vs the demo; log to state.
- roadblock being cleared: privacy footer claimed PII-scrub that wasn't built (honesty breach) → softened to true
  claims now + building the real scrub so the claim is honest. And: non-deterministic gemma garbling demo answers
  → fixed by the curated cache.

---
[STATE_MANIFEST]
- cycle: 4 (2026-06-24) — DONE, committed `cad8104`
- micro-milestone DONE: the privacy claim is now LITERALLY TRUE + provable. Red-Team verification of the prior
  cycle found `scrub_pii.py` existed + unit-tested but was wired into NOTHING (correct code, never ran on stored
  data). Wired it into BOTH storage seams: live phone-ingest (`trace_brain_server._capture`/`_records_to_kf`,
  scrubbed before RAM + disk) and the demo-memory build (`cockpit_ask_server._build_demo_memory`, the artifact
  the brain reasons over). Fixed a demo-breaking false positive (grouped-phone heuristic ate the truncated
  plaque date `1845 - 192` → year-range guard). 0 false positives on the real 1564-line corpus (was 1).
  Proof: `evaluation/test_scrub_wiring.py` (end-to-end on real artifacts) + `test_scrub_pii.py` (9/9). Claim text
  upgraded "by design/being built" → "scrubbed before storage" in cockpit footer + PITCH_DEMO_SCRIPT.
- arch version: v0.3 — Context→Prompt→Answer with (a) demo-cache fast path, (b) consensus reads-or-refuses brain,
  (c) on-device PII redaction ENFORCED at every storage seam. Demo surface = cockpit :8799.
- next 3 autonomous actions (recommended order; #3 needs the founder):
  1. Demo resilience audit: confirm cockpit_supervise.sh/keepalive actually auto-restart cockpit+brain across a
     reset, and that the demo runs network-independent on localhost (no hotspot-IP dependency). Verify, don't assume.
  2. Honest live-brain re-measure (deliberate, ~20-min gemma job, NOT a blind kick-off): run the walk through the
     REAL ask_home (consensus + premise gate) and log correct/refuse/wrong vs founder gold → quantify product gap.
  3. [NEEDS FOUNDER] Bigger text-rich capture + human gold (n=15→~50). This is the pitch-readiness GATE for the
     general product; I can prep the capture+gold pipeline but cannot fabricate human gold. Surface to founder.
- roadblock being cleared: "PII scrubbing" was an unwired module → an honesty breach waiting to be asked about in
  the pitch. Now enforced at source + verified, so the privacy moat (RULE 4) is real end-to-end, not aspirational.

---
[STATE_MANIFEST]
- cycle: 5 (2026-06-24) — COURSE CORRECTION (founder Red-Team override, Rule 3) — EXPAND BUILT + WIRED + VERIFIED
- RESULT: `scripts/inject_expand.py` (EXPAND/TIER/COMPILE, on-device gemma oracle, 2-zone, grounded+confident-or-
  silent) built; 6 honesty tests pass. WIRED into the engine: `ask_home.ask_with_understanding` (additive; grounds
  the personal zone from SCENE/OBJECTS when the base over-refuses, so the 2 zones stay coherent) + cockpit do_ask +
  native brain-server /ask all route through it. Verified end-to-end on the REAL Tokyo native capture (VISION
  channel, zero OCR): "what kind of place is this?" -> grounded "you saw a night street with storefronts..." +
  fenced world knowledge (Swatch/McDonald's/The Body Shop). 16/16 tests green. Commit below. NOT a dead module.
- the correction (owned): I was demonstrating ONE channel (OCR consensus) and calling it the product. WRONG.
  The product is the multi-modal [Context -> Prompt -> Answer] engine. OCR is solved + closed (founder); the
  YouTube-video path is a degenerate single-channel input — abandoned as a deliverable.
- grounded reality (from code, not memory): the engine is ALREADY built + wired — ask_home.py fuses ~12 specialists
  (SCENE/VLM caption, OBJECTS/detector, temporal, spatial+egomotion, audio/speech, entity-graph, counting,
  self/wearer, structured-recall, premise-gate, consensus). Native captures carry SCENE:+OBJECTS: channels, not
  just OCR. The architecture/blueprint is DONE. So "the other 99%" is NOT design or breadth — it is ONE unbuilt
  layer + integration.
- THE unbuilt paradigm piece: the INJECTION / world-knowledge EXPAND layer (`inject_*.py` does not exist). It is
  the "Prompt" in Context->Prompt->Answer — it turns remembered perception into UNDERSTANDING (see a storefront/
  plaque/poster -> know what it IS/MEANS), grounded to evidence, two-zone honest (personal_evidence vs
  world_context), private by construction (on-device LLM world-oracle, zero egress).
- arch version: v0.4 — adds INJECTION (EXPAND) on top of the fused multi-modal substrate. Loop: capture (12
  channels) -> FUSE evidence -> EXPAND with world knowledge -> premise-gate -> answer (two zones).
- next 3 autonomous actions:
  1. Build `scripts/inject_expand.py` — the two-zone EXPAND layer (on-device gemma oracle, grounded, honest,
     channel-agnostic), with tests. DONE this cycle if it passes.
  2. WIRE it into ask_home.ask for "understanding/what-is" questions (additive; never alters personal claims) so
     it is NOT a dead module (the scrub_pii lesson). Demonstrate end-to-end on a real native capture.
  3. Surface the paradigm beat on the cockpit demo surface: "what IS this place?" answered from vision+world
     knowledge, two-zone, that pure memory cannot give.
- roadblock being cleared: the pitch had memory but not UNDERSTANDING — nothing that makes an investor feel the
  paradigm. The EXPAND layer is that "magic." Building the real thing, not a slide.

---
[STATE_MANIFEST]
- cycle: 6 (2026-06-24) — built the LEASH + actually VERIFIED EXPAND (caught + fixed a real hallucination)
- LEASH: goal=both deliverables (demo magic + an honest guard); verified=adversarial audit n=4 on real gemma
  (evaluation/expand_audit.py), NOT a single demo; founder-#1=YES (founder explicitly asked for self-check +
  anti-tunnel mechanism this cycle).
- what shipped: (1) `ops/ANTI_TUNNEL_LEASH.md` — the Chief's 7-question self-check catching BOTH over-narrow (OCR
  trap) and over-broad (architecture-astronomy) + the recurring "declare done on one demo" flaw; structurally
  enforced via a mandatory `LEASH:` line on every manifest. (2) Verified EXPAND for real: the audit caught gemma
  CONFIDENTLY FABRICATING a made-up company ("Zlorptech Systems GmbH", conf 0.95) — the honesty moat's throat. Fix:
  a refute-by-default skeptical corroboration pass (`_corroborated`) in `inject_expand.world_gloss`; self-reported
  confidence is worthless, a fresh skeptical existence check is the gate. Re-audit 4/4: real entities survive,
  fabrications go silent, unseen referents dropped. 7 unit + 4 audit cases green.
- arch version: v0.5 — EXPAND now hallucination-gated (recognize-or-stay-silent), matching the OCR channel's
  reads-or-refuses discipline. The whole engine is now self-calibrating-honest across channels.
- leashed next (was "continue with all" → reordered by the leash): (1) surface the verified paradigm beat on the
  cockpit demo card (deliverable #1); (2) premise-gate 3-mode standing-ground at build_evidence_dossier; DEFER
  LINK (optimization, not the bottleneck — leash Q3/Q6).
- roadblock being cleared: I was about to build a demo-card on an UNVERIFIED capability (the fake-number trap in
  paradigm clothing). The leash forced verification first; verification found a moat-breaking hallucination. Caught
  pre-pitch, not on stage.

---
[STATE_MANIFEST]
- cycle: 7 (2026-06-24) — UNDERSTANDING RESET (founder corrected the Chief 3× for shrinking the product). No code
  this cycle; the deliverable was getting the MODEL right and writing it down so no future instance tunnels again.
- LEASH: goal=both deliverables (this cycle protects them by fixing the shared understanding that was producing
  wrong work); verified=N/A this cycle (definition work, not a capability claim — explicitly NOT declaring anything
  "built/verified"); founder-#1=YES (founder explicitly ordered "write all the things we discussed + revamp the md
  files so the other you has proper context — these are things we should have done day 1").
- what shipped (docs only, by design): (1) `ops/PRODUCT_NORTH_STAR.md` — THE canonical model, read-first: product =
  open-domain QA over lived experience; irreversibility orders capture(PRIMARY) vs world-reach(BACKSTOP);
  HELPERS(extract, open-ended) → INJECT(**the binding brain** — binds helper outputs at capture into one
  provenance+confidence representation; this is the piece the Chief mis-cast as a "router" TWICE) → LLM(thinks,
  plans own path, refuses past the edge of capture); "more is better" sharpened to "BOUND richness"; privacy =
  raw-media line, text free; full limitations/failure-modes §5; PRIMARY vs SECONDARY (thermal/eyewear secondary).
  (2) Revamped `ops/ANTI_TUNNEL_LEASH.md` — added the failure modes actually exhibited this session
  (example-fixation, mirroring/yes-man, closed-list/schema-thinking, hardware over-rotation, critique-theater) as
  leash questions #4–#6, points to the north star. (3) Updated memory: [[product-extent-do-more-not-less]] (new),
  [[injection-layer-standing-ground]] (INJECT=binding-brain correction prepended), MEMORY.md index.
- arch version: v0.6 (understanding) — no engine change; the SPEC of INJECT is now "binding brain at capture", which
  the current `inject_expand.py` only PARTIALLY implements (FUSE/EXPAND, no full scene-graph binding, no cross-time
  identity). That gap is now named honestly in north-star §9.
- next (NOT started — for the founder to steer): the real INJECT binding layer (scene-graph at capture, provenance +
  binding-confidence propagated to the LLM) is the primary build; cross-time identity is its hard sub-problem; the
  honest number at n≥50 remains THE gate. Do NOT mistake the partial EXPAND for the binding brain.
- roadblock being cleared: the Chief kept producing wrong work because its MODEL of the product was too small
  (closed-schema capture + INJECT-as-router + privacy-as-tradeoff + example-as-spec). Fixed at the source — the
  governing docs — so the correction is durable, not re-explained every session.

---
[STATE_MANIFEST]
- cycle: 8 (2026-06-24) — DELEGATE + HONEST-COCKPIT (founder near Chief's usage limit → delegate to Codex+local
  LLMs, keep Chief footprint small; founder asked for the cockpit to show REALISTIC projections after "months of
  tunnel vision").
- LEASH: goal=BOTH — serves #1 (the demo/honest-progress surface the founder reads) and #2 (Stage-3 probe is the
  first real measurement toward the trusted number); verified=Codex self-verifies the cockpit (JSON parses + HTTP
  200 + sections present) AND the Chief will spot-check engine.json for HONESTY before declaring done (agent
  self-test ≠ proof); founder-#1=YES (explicitly asked: update the cockpit with realistic projections + start work,
  delegate most of it).
- DELEGATIONS:
  1. DONE + VERIFIED LIVE (Chief spot-checked honesty; restarted stale server pid→91441; /engine, /engine.json,
     /api/status all HTTP 200; served HTML renders pipeline/not_built/UNMEASURED/NOT MET/Stage-3). Codex
     (bash bk2vj1599) on `ops/CODEX_BRIEF_cockpit_reality.md`:
     rewrite `ops/cockpit/engine.json` + `cockpit_engine.html` to the corrected architecture (6-stage pipeline w/
     honest per-stage state: 0 partial, 1 partial, 2 not_built, 3 not_built=PRIMARY GAP, 4 partial, 5 built-small-n),
     the verified list w/ caveats, the honest number (n=15, 60%/18.2%, gate BOUNDARY; the GATE = n≥50 human gold,
     UNMEASURED), the two deliverables (demo READY / number NOT MET), realistic projection. Brief carries hard
     honesty rules. ON COMPLETION: Chief reads the resulting engine.json to confirm nothing was inflated.
  2. QUEUED (not fired — disciplined, one job at a time near budget) — `ops/CODEX_BRIEF_stage3_binding_probe.md`:
     the first product measurement (minimal deterministic-first BIND pass over a real observation log; score binding
     precision + whether low-confidence binds correctly abstain). Step 0 = locate a box-bearing capture log; if none
     exists, that's itself a finding (Stage 1 localization must precede). Launch next cycle.
- arch version: unchanged (v0.6 understanding); this cycle is delegation + honest reporting, no engine change by the
  Chief.
- next: (a) verify Codex's cockpit output for honesty; (b) launch the Stage-3 binding probe; (c) the big-n eval
  (n≥50 + human gold) remains THE gate and needs a founder capture.
- roadblock being cleared: the cockpit showed a STALE/old-framing reality (n=15 against a narrow target, dirty git
  counts, pre-correction milestones). Founder couldn't see true progress after months. Fix = an honest, current
  reality surface — delegated so it costs the Chief almost nothing.

---
[STATE_MANIFEST]
- cycle: 9 (2026-06-24) — IN FLIGHT
- LEASH: goal=#2 trustworthy honest number (and keeps deliverable #1 honest in the cockpit); verified=ONLY the
  harness state so far (local process alive, Ollama attached, incremental JSON write proved by the first records,
  plus a live audit that caught and fixed a refusal-scoring bug before the aggregate hardened) — NOT the product
  number; founder-#1=YES (the autonomous continuation prompt makes this the live task).
- micro-milestone IN FLIGHT: launched the real-brain founder-gold eval locally against
  `data/walks/walk_outside_20260614/memory/kf_memory.json` using
  `evaluation/run_founder_gold_brain.py`. First launch pid `92561` started at `2026-06-24 14:37:52 CEST`.
  Early live audit caught an evaluator honesty bug: the explicit reach-failure note
  `"I had trouble reaching my memory just now."` was being mislabeled `WRONG`, inflating hallucinations.
  Patched `scripts/ask_home.py` + the harness refusal detector/resume scorer, then resumed at `14:48 CEST`
  as pid `99719`. Output path `evaluation/ras/founder_gold_brain_run.json` is resumably live and the partial
  self-healed (`id=1`: `WRONG` → `REFUSED`). Current partial: `id=0` = `REFUSED`, `id=1` = `REFUSED`,
  `id=2` = `WRONG`, `id=3` = `CORRECT`. Observed cadence is minutes per item
  (`169.1s`, `255.9s`, `57.5s`, `243.2s`). No aggregate number yet.
- arch version: unchanged (v0.6 understanding) — this cycle is measurement, not an engine change.
- next 3 autonomous actions:
  1. Let the local harness continue; do NOT duplicate the run while pid `99719` is healthy and the partial JSON keeps
     advancing.
  2. When the run finishes, hand-audit 5–8 verdicts against founder gold + memory evidence before trusting the
     aggregate.
  3. Then update `ops/cockpit/engine.json` honest_number, verify `/engine` on :8799, and advance
     `ops/AUTONOMOUS_CONTINUATION.md` to the next queued task.
- roadblock being cleared: the first fair product-proxy number is long-running local compute on the 27B real brain,
  so the critical thing this cycle is preserving exact resume state and refusing to invent progress before the
  aggregate exists.

---
[STATE_MANIFEST]
- cycle: 10 (2026-06-24) — TARGET CORRECTION + LIVE44 IN FLIGHT
- LEASH: goal=#2 trustworthy honest number; verified=founder-corrected target locked, question counts verified
  from source files (day=19, walk=25), old stored memories independently audited as `offline_replay`, live-helper
  harness smoke-tested on BOTH clips, and a one-question end-to-end scorer probe proved the local
  `gemma3:12b-it-qat` answer + `gemma3:27b-it-qat` judge path works; founder-#1=YES (explicit redirect: use the
  day-in-life + Garching walk questions and honor the live-helper pace rule).
- micro-milestone IN FLIGHT: abandoned the old founder-gold `n=48` measurement as the headline after the founder
  clarified the fair target. The honest proxy now is the **44-question live-helper battery**:
  `evaluation/ras/day_in_life_20260618.txt` (19) + `evaluation/ras/walk_outside_20260614.txt` (25). The live
  harness is `evaluation/run_live_replay_battery.py`, which rebuilds derived text from the raw clips at wall-clock
  pace and scores the local brain on that fresh memory, rather than using the repo's old stored memories (those are
  marked `mode=offline_replay`, `real_time_proven=false`, so they are NOT fair evidence for the headline number).
  Capture contract currently proven live on this Mac: OCR + ASR + audio-events. Notably, local gemma3 multimodal is
  too slow (~17–32s/frame spot-check) to count as a live helper here, so VLM captions are excluded from the
  headline memory by design and any scene/object questions that depend on them should refuse. That lower score, if
  lower, is the honest result under the founder's rule. The active full run was launched via the local `.venv`
  runner; progress lands in `ops/cockpit/eval_live44_day.json`, `ops/cockpit/eval_live44_walk.json`, and the final
  aggregate in `evaluation/ras/live44_summary.json`.
- arch version: unchanged (v0.6 understanding) — measurement only. This cycle clarifies the FAIR contract for the
  product number: live-helper-constrained derived text, not offline frame-by-frame helper replay.
- next 3 autonomous actions:
  1. Let the local live44 run continue and monitor the status JSONs until both clips finish.
  2. Hand-audit 5–8 judged rows across day+walk before trusting the aggregate.
  3. Update the cockpit's `honest_number` with the live44 result + caveat, then move to the next queued item.
- roadblock being cleared: the repo already held richer offline-replay memories that could have produced a prettier
  but unfair score. The founder explicitly closed that loophole: helpers must keep pace with live capture. This
  cycle locks the measurement to that constraint so the number is defensible.

---
[STATE_MANIFEST]
- cycle: 11 (2026-06-24) — COCKPIT OVERHAUL DONE, LIVE44 PAUSED ON HOST INSTABILITY
- LEASH: goal=BOTH — the cockpit overhaul directly serves deliverable #1 (a truthful founder surface) and keeps #2
  honest; verified=`/engine.json` now exposes the actual product story + runtime live44 status, the HTML surface was
  rewritten around the real architecture, the scorer bug that over-credited refusals was fixed and tested, and the
  scorer now has a per-question wall-clock guard so a hung answer becomes a conservative miss instead of freezing the
  whole baseline; founder-#1=YES (explicit pushback: "the cockpit is bad and doesn't show anything meaningful based on
  the actual product", plus the host was hanging).
- micro-milestone DONE / PAUSED:
  1. DONE: cockpit reality surface overhauled. `ops/cockpit/engine.json` was rewritten around the actual product:
     open-domain QA over lived experience, the live-helper contract, what is real now vs not real yet, and the
     official number as `UNMEASURED`. `ops/cockpit/cockpit_engine.html` was rebuilt to render that story, and
     `scripts/cockpit_ask_server.py` now augments `/engine.json` with runtime memory/ollama/live44 status instead of
     just stale static facts. The founder-facing cockpit finally talks about the product, not repo trivia.
  2. DONE: live44 scorer honesty+reliability hardening. Found a real grader bug where a refusal like "it does not
     specify ... I cannot answer" was scoring `CORRECT` by repeating an accept cue ("calorie"). Patched
     `evaluation/auto_score.py` + regression test. Then found a second reliability bug: a single local-brain stall
     could freeze the whole battery. Patched `evaluation/run_live.py` with a per-question wall-clock guard so a stuck
     answer becomes `MISS` and the run can continue.
  3. PAUSED: relaunched the live44 battery after the timeout fix; it reached day capture and day scoring Q1, but the
     founder reported the whole OS was hanging and the local LLMs were effectively not running. Stopped the run on
     purpose to protect the machine. This is now a host-stability pause, not a measurement-design blind spot.
- arch version: unchanged at the product level; the important change is the measurement/control surface now matches
  the real architecture and surfaces live-helper truth instead of stale recall theater.
- next 3 autonomous actions:
  1. After the box recovers, relaunch the live44 battery with the new timeout-guarded scorer.
  2. When it completes, hand-audit 5–8 judged rows before trusting the aggregate.
  3. Update the cockpit official number only when a fair completed aggregate exists; keep `UNMEASURED` until then.
- roadblock being cleared: before this cycle, the founder could not tell what the product actually was from the
  cockpit, and the headline measurement could freeze indefinitely on one hung answer. Now both failures are named and
  reduced; the remaining blocker is machine stability.

---
[STATE_MANIFEST]
- cycle: 12 (2026-06-24) — WS1 SHIPPED + VERIFIED: the self/world binding guard
- LEASH: goal=protects deliverable #1 (the demo's honesty wow) and #2 (the honest number) by closing the moat's
  ONLY real failure — binds-or-refuses. verified=THREE independent ways: (a) 30-case CPU unit selftest incl. the
  WS1 adversarial red-team cases; (b) deterministic replay of the guard over ALL 88 recorded answers (day 19 +
  walk 25 + ceiling 44) — it flips EXACTLY the 3 day hallucinations (+1 ceiling MISS->MISS, more honest) and
  produces 0 regressions on any CORRECT/NEEDS_REVIEW answer; (c) live end-to-end through the real gemma3:12b brain:
  the 3 hallucinations became honest refusals, the 2 day-correct answers were untouched; and (d) a FULL fresh day
  re-score through the guarded brain: 2 correct / 0 wrong / 17 miss (was 2/3/14) — day hallucination 60% -> 0%.
  founder-#1=YES (sprint handoff names WS1 HIGHEST PRIORITY, surgical, protects the whole pitch).
- what shipped:
  1. `scripts/self_world_guard.py` — a STRUCTURAL guard (NOT a name blocklist; keys on question-class ×
     answer-shape × self_entity corroboration). Three rules: A self-name may assert a name only if self_entity
     corroborates it; B first/second-person authorship/ownership of observed content is refused when the memory has
     ZERO self-corroboration; C a NAMED co-present person is refused (no channel localizes a named person — no boxes,
     no diarization, no face-ID). Honest refusals explain WHY ("a name I read on a sign is the world's, not yours").
  2. Wired into `scripts/ask_home.ask` via a thin tail-wrapper (`_ask_impl` does the work; `ask` runs the guard over
     WHATEVER path produced the answer) so it covers consensus/assembler/specialist paths uniformly. Also wires in
     the previously-dead `self_entity` module as the corroboration channel.
  3. The asymmetry that makes it both honest AND non-regressing: on the blindfolded memory self_entity is empty
     (name=None, 0 ego frames) so "what is my name -> Nezam Pinias (a sign)" REFUSES; on the caption-rich ceiling
     memory self_entity corroborates "Joe" (addressed in a farewell) + 76 ego frames so the same question KEEPS
     "Joe". Same rule, opposite outcomes, both correct.
- adversarial verification: a bounded red-team agent found real gaps (self-name synonyms, relational co-presence
  verbs, second-person ownership phrasings, a `mine`=gold-mine over-fire). All fixed and baked into the selftest as
  permanent regression cases. Documented (NOT chased) limitations: generic possessives ("my car"), generic
  "who did I meet/talk to" (screen/calendar-answerable), and quoted world-text containing "by me" — left to the
  honest-refusal default rather than risk over-refusing grounded answers (the over-broad trap).
- arch version: unchanged at the product level; Stage-3 attribution gap is narrowed at the QUERY seam (refuse the
  ungrounded binding) — the CAPTURE-time binder (WS2 INJECT) is still the deeper fix and remains next.
- next 3 autonomous actions:
  1. Let the walk re-score finish (harness-tracked) and confirm walk stays 0 hallucinations; commit WS1.
  2. WS2: an interim Stage-3 TEMPORAL/identity binding probe on current data (no boxes yet) — the brief's buildable half.
  3. WS6: run the dead-weight audit READ-ONLY and surface high-confidence-safe deletions to the founder (do NOT
     auto-delete 5.5G I didn't create).
- roadblock being cleared: the brain confidently turned the WORLD into the SELF (a sign's name into "my name"). That
  single class of error was the whole hallucination count on the day clip and the most pitch-damaging kind of lie.
  It is now structurally impossible without corroboration, verified end-to-end.
