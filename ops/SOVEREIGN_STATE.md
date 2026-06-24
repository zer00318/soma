# SOVEREIGN STATE — autonomous orchestrator resume anchor
*Read this FIRST on any resume. Most recent [STATE_MANIFEST] at the BOTTOM. Branch chief/p0-honesty-sprint.*

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
