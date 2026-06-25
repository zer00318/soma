# Context Engine Blueprint — HANDOFF (2026-06-23 PM)

*Wrap-up so a fresh chat continues without re-burning usage limits. Author: the Chief.*
*Founder directive that started this: build the `HELPERS → INJECTION → LLM` continuous context engine
(injection FUSES + live WEB-EXPANDS helper outputs; LLM STANDS ITS GROUND on false premises). Total
sovereignty to the Chief. Product is broad CONTEXT, not OCR. See `memory/founder-architecture-directive-20260623.md`.*

## ⚠️ COST LESSON (read first)
The big multi-agent Workflow **burns this plan's usage limits very fast** (Phase-1 grounding alone =
~377k subagent tokens / 18 agents; the run hit the session limit twice, "resets 4pm Europe/Berlin").
**Do NOT re-run the full fan-out.** Everything expensive is already cached on disk (below). For the
remaining work prefer **inline synthesis by the Chief** + a few **small bounded agents**, not a 14-wide fan-out.

## STATUS
- ✅ **Phase 1 grounding — DONE + persisted** → `ops/CONTEXT_ENGINE_GROUNDING_2026-06-23.md`
  - (A) Repo reality with file:line; (B) IPP-poster worked example with `089 289 112` truth verified +
    cited; (C) 2026 on-device tech envelope with real numbers + citations.
- ✅ **Phase 1 lenses — DONE + persisted** → `ops/CONTEXT_ENGINE_MATRIX_RAW_2026-06-23.md`
  - 14 blind first-principles lenses, **195 parameters**, each with why / failure / Phase-2 hard-question /
    current-tech hook, ⚠️-flagged blind-spots. Raw JSON also at `/tmp/matrix_raw.json`.
- ✅ **Phase 1 synthesis — DONE (inline, no agents)** → `ops/CONTEXT_ENGINE_SYNTHESIS_2026-06-23.md`
  - 195 params → **14 cross-cutting clusters** + **8 core paradoxes** (each with a resolution thesis) + a
    blind-spots list + a build-order. Root finding: the substrate is a flat string and ~60% of the matrix is
    "impossible on a string" — fix CL-1 (typed `Observation` event log) and most of it dissolves.
- ✅ **Phase 2 blueprint — DONE (inline, no agents)** → `ops/CONTEXT_ENGINE_BLUEPRINT_2026-06-23.md`
  - The definitive, buildable-today capstone: end-to-end pipeline (capture-quality gate → typed event-log
    substrate → injection I0–I4 → premise gate ANSWER/CORRECT/REFUSE → LLM → async brain), the thermal live/brain
    split as a *necessity*, the honesty-gate redesign, never-delete hot/cold + per-fact decay, secured sync,
    buildable-today stack table, the eval gate (real `ask_home.ask`, frozen gold n≥100, 95% CIs), and a risk
    register of the open hard-questions. **Re-anchors the board to WS0–WS9** (added WS8 EXPAND, WS9 physics/sync).
- ◻️ **REMAINING = execution, not design.** The blueprint is the spine. Next is building, in order:
  WS3/WS4 (typed substrate — no-regret) → WS2 (consensus-as-default + calibrated gate) → WS5 (premise gate +
  refutation_cue) → WS7 (big-n frozen-gold eval — the pitch gate) → WS8 (EXPAND). Use Codex + local LLMs for the
  coding; keep agents small + bounded; the design phase is over so no more wide fan-outs.

## THE VERIFIED HEADLINE (your poster proved the thesis)
`089 289 112` = the **TUM Werkfeuerwehr (Garching campus plant fire brigade) direct mobile-emergency line**
(`089 289` = TUM's switchboard exchange). The poster letterhead is **IPP – Max-Planck-Institut für
Plasmaphysik**, whose *own* exchange is `089 3299`, not 289. Reconciliation: **IPP shares the Garching
campus, so TUM's brigade covers it** → IPP's building, TUM's campus fire brigade. (Founder's "TUM hotline"
label = operator-right, institution-wrong — a good system says exactly that.) Full trace + the false-premise
"wifi password" stand-your-ground answer are in the grounding doc, §B.

## THE BRIDGE — repo grounding turned the thesis into a 5-item build list (with file:line)
1. **Fusion-into-facts** — today's "injection" (`ask_home.py:2698` assembler) is a ranked *text dossier
   string*, not unified entities. Build a fusion stage emitting `Observation`/`Entity` (`src/trace_memory/
   domain/*` already define these) → a structured evidence packet. Seeds: `consensus_recall.py:108`,
   `structured_recall.py:475` (both real frequency=confidence) — run them *inside* assembly, not as side paths.
2. **Live web/knowledge expansion — ENTIRELY ABSENT** (grep-confirmed; the novel layer). Build an `Expander`
   port: fused fact (phone number, institution, sign, logo) → web/knowledge lookup → new corroborating
   observations w/ provenance. `WebSearch`/`WebFetch` exist as tools but the engine never calls the network.
   Privacy paradox: every lookup leaves the device → prefer a cached local Wikidata snapshot + Brave only for
   live misses (Brave API: $5/1k, <1s; free tier is gone).
3. **Premise-check / stand-your-ground — ABSENT** in the engine (only in eval trap bank `ask_live.py:30`).
   Build a premise-verification step before phrasing: detect when the question presupposes a fact the evidence
   refutes; have the LLM assert the contradiction, not pivot. Today's gate gives a *silent canned refusal*.
4. **Consensus runs only on the anchored read path** (`ask_home.py:2750`). Make frequency-consensus the
   assembler's **default** fusion mechanic across all channels.
5. **Hexagonal core is ~90% stubs**; `Observation.refutation_cue` (`observation.py:30`) is defined but never
   produced/consumed. Migrate working `ask_home` logic behind the ports so fuse/expand/premise-check are
   composable stages, and populate `refutation_cue` so the stand-your-ground LLM has something to stand on.

## TECH ENVELOPE (the physics, from grounding §C)
Everything except the heavy VLM is **real-time + on-device today**: OCR (ML Kit 0.05s / Apple Vision 0.31s
+confidence), ASR (WhisperKit 2.2% WER <0.5s / iOS 26 SpeechAnalyzer), embeddings+store (MiniLM-CoreML +
sqlite-vec + SQLCipher). Hard walls: on-device VLM is **sub-5 tok/s** and the SoC **throttles in ~1 min** to
~4–5W sustained → always-on full-frame VLM is thermally impossible → heavy VLM = duty-cycled async brain,
live path = cheap honest helpers. (Validates the existing live-bounded / brain-unbounded split as a *thermal
necessity*.)

## HOW TO CONTINUE (cheapest path)
1. **Synthesize the matrix INLINE** from `ops/CONTEXT_ENGINE_MATRIX_RAW_2026-06-23.md` (195 params → ~10-14
   clusters + blind-spots list + core paradoxes). No agents needed; the Chief reads the raw and writes the
   clustered matrix.
2. **Phase 2 = resolve + blueprint**, anchored on the 5 gaps above. If using agents, keep them **small and
   bounded** (one cluster or one gap at a time), NOT a wide fan-out. Resolve the core paradoxes (always-on vs
   battery; rich memory vs privacy; web-expansion enrichment vs egress; flexible helpers vs typed answer
   logic; freshness vs durability; helpful inference vs hallucination).
3. **Deliverable** = `ops/CONTEXT_ENGINE_BLUEPRINT_2026-06-23.md` (definitive, buildable-today), then
   re-anchor the sprint board WS0–WS7 (`ops/CONTEXT_SPRINT_2026-06-23.md`) onto the helper/injection/LLM spine.
   - To resume the SAME workflow cheaply (grounding + 14 lenses return cached): `Workflow({scriptPath:
     "…/workflows/scripts/context-engine-matrix-phase1-wf_4aed8683-0d7.js", resumeFromRunId:
     "wf_4aed8683-0d7"})` — BUT the synth step is what over-ran; chunk it or do it inline instead.

## ALSO DONE THIS SESSION (sprint, still valid)
- Native hero **builds GREEN** today (Xcode 26.3) after fixing a `ContentView.swift:281` `[Any]`-inference
  regression (`[URL?]` fix, uncommitted in working tree). Deploy unblocked; "Metal-blocked" memory was stale.
- Discovery: `trace-native-fastvlm` is already a multi-modal on-device context engine (vision+detector+OCR+
  speech+location+fusion-digest w/ seen-counts), proven Munich 2026-06-04 (`TRACE_NATIVE_LIVE_REPORT.md`).
- Pitch bar redefined to the real multi-modal product (honest 50%, was a fake-target 73%). Board WS0–WS7.

## OPERATING REMINDERS
Max-load local LLMs (ollama gemma3:12b/27b) + Codex for bounded coding; preserve Claude tokens; the Chief
decides + verifies. Apple Vision OCR fails in Codex sandbox — run OCR locally. Don't spawn `until…do sleep`
waiters. Honest numbers over inflated ones.
