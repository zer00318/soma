# Context Engine — THE BLUEPRINT (definitive, buildable-today · 2026-06-23 PM)

*The single architecture for the `HELPERS → INJECTION → LLM` continuous on-device context engine.*
*Author: the Chief. Founder directive: injection FUSES + live WEB-EXPANDS helper outputs; the LLM STANDS ITS
GROUND on false premises. Product = broad CONTEXT (a memory for everything you encounter), not OCR.*

This document is the capstone. It does not re-derive the parts already specified — it **unifies** them and fills
the gaps between them:
- **Inputs:** the 195-param matrix (`ops/CONTEXT_ENGINE_MATRIX_RAW_2026-06-23.md`) → its **14-cluster synthesis**
  (`ops/CONTEXT_ENGINE_SYNTHESIS_2026-06-23.md`), repo reality + worked example
  (`ops/CONTEXT_ENGINE_GROUNDING_2026-06-23.md`), and the **already-designed injection layer**
  (`ops/CONTEXT_ENGINE_PHASE2B_INJECTION_LAYER_2026-06-23.md`: stages I0–I4 + the ANSWER/CORRECT/REFUSE contract).
- **Output:** one buildable architecture, the build order, the re-anchored sprint board WS0–WS7, and the eval gate.

---

## 0. THE THESIS IN ONE PARAGRAPH
A wearable continuously perceives the world through a **society of cheap, honest, typed helpers** (OCR, ASR,
detector, geocode, capture-quality). Their outputs are written to a **typed, append-only `Observation` event log**
— the single source of truth. An **injection layer** fuses co-occurring observations into situated entities, links
typed spans to identifiers, **expands them against world knowledge (local-snapshot-first, privacy-budgeted)**, tags
every fact `personal_evidence | world_context`, and compiles a **two-zone evidence packet**. A **structural premise
gate** picks the speech act — **ANSWER / CORRECT / REFUSE** — *before* generation, and the **LLM stands its ground**
on false premises because it is handed populated `refutation_cue`s, not asked to be brave. The heavy VLM and all
LLM phrasing/expansion run in a **duty-cycled async brain**; the live path is ANE-cheap and deterministic, because
the phone throttles to ~4–5W in ~1 minute. Nothing is ever deleted; truth-claims decay, facts don't.

```
                         ┌─────────────────── ON-DEVICE (live, ANE-cheap, deterministic) ───────────────────┐
  camera ─┐              │  CAPTURE-QUALITY gate ─► sharp/legible frames only (no dark/blur guessing)        │
  mic ────┼─► HELPERS ──►│  OCR · ASR · detector/track · geocode · (typed specialists, each self-refusing)  │
  GPS ────┘   (society)  │            │ each clears its own honesty gate; garble is REFUSED, not emitted     │
                         │            ▼                                                                       │
                         │   ┌────────────────────────────┐   append-only, encrypted, never-deleted          │
                         │   │  OBSERVATION EVENT LOG (SoT) │◄── hot/cold tiers, per-fact-type validity        │
                         │   └──────────────┬──────────────┘   (sqlite-vec + SQLCipher)                        │
                         └──────────────────┼───────────────────────────────────────────────────────────────┘
                                            │  durable, idempotent, secured sync (NOT plaintext / dev-token)
   ┌──────────────────────── ASYNC BRAIN (duty-cycled: heavy VLM, LLM, EXPAND) ───────────────────────────┐
   │  INJECTION LAYER   I0 FUSE ─► I1 LINK ─► I2 EXPAND ─► I3 TIER ─► I4 COMPILE  ──► two-zone packet       │
   │     (consensus = the DEFAULT fusion mechanic; calibrated fact-posterior, not per-channel floors)       │
   │                                            │                                                            │
   │  PREMISE GATE (structural, pre-generation) ┼─► ANSWER | CORRECT | REFUSE                                │
   │                                            ▼                                                            │
   │  LLM  — phrases from typed facts + cites provenance; world_context explains, never grounds a personal   │
   │         claim; holds its ground under restatement when a cited personal line contradicts the premise    │
   └────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. THE ROOT MOVE — the typed substrate (CL-1)
**Everything else is impossible on a string.** Today `build_evidence_dossier` (`ask_home.py:1510,:1586`) emits a
ranked delimited *text* dossier; entity resolution + consensus run as side paths feeding only the refusal gate.

**Build:**
1. **`Observation` event log as the single source of truth.** The typed model already exists
   (`src/trace_memory/domain/observation.py` — `Observation`/`Attribute`/`Confidence`/`Provenance`,
   `refutation_cue` at `:30`); the sqlite adapter seed exists (`adapters/sqlite_eventlog.py`, 102 lines). Make it
   load-bearing: every helper writes a typed `Observation` (with `t_ms`, provenance, bounding box / track-id,
   `kind`); both the device digest and the brain project **from this one log** (kills the two-divergent-rep problem,
   CL-10/state-11). **Invariant:** deleting all projections and rebuilding from the log reproduces the identical
   answer (state-1's measurable test).
2. **The assembler emits a structured packet, not a string.** Typed entities + per-fact merged confidence + the
   full provenance list, carrying **spatial adjacency edges** (box co-location) so cross-channel fusion stops
   re-mixing attributes across entities (injection-10/state-5 — the name/date binding problem). `ASSEMBLER_MAX_PER_
   CHANNEL=10` truncation that silently drops corroborating votes (grounding-11/failure-4) is removed.
3. **Persist resolved entities** (`state-7`). `entity_graph` already clusters typed entities but the result is
   thrown away after the G1 veto — write it to a durable entity table so facts accumulate across frames/sessions
   ("the same shop you passed earlier") and so resolution can **inform** answers, not only suppress them
   (injection-5).

> Buildable today: `sqlite-vec` (brute-force fine to ~10^5 vectors/personal store) + `SQLCipher`/WAL = encrypted
> append-only store; `MiniLM-CoreML` (tens of ms on A17/A18) keys entity clustering on-device. **No new models.**

---

## 2. CONSENSUS AS THE SPINE + a real confidence algebra (CL-2, CL-11)
The one validated honesty win — `consensus_read` (`consensus_recall.py:108`, 47%→60% strict, halluc 42%→~9–18%) —
is wired as a **side path** (anchored reads only, `ask_home.py:2750`). Promote it to the assembler's **default**
fusion mechanic across all channels, and fix the four ways its math is currently naive:

| Fix | Problem it kills | How (buildable today) |
|-----|------------------|-----------------------|
| **Confidence-weighted quorum** | `minrep=3 / ±5s` frame-count quorum collapses under thermal-throttled capture (fast glances never repeat 3×) | Apple Vision per-word confidence: one high-confidence read can substitute for repetition (injection-13/state-14) |
| **Viewpoint de-correlation** | A still camera reading one sign 30× = "30 votes"; a persistent mis-read becomes high-confidence "consensus" | De-weight votes by pose/sharpness similarity; count **independent sightings**, not frames (grounding-10/state-4, P8) |
| **Type-aware + box-aligned merge** | Substring fold over-merges distinct facts: `1881`→`1881 Hauptstrasse` sums votes for the wrong canonical | Don't fold across numeric-type boundaries; require box-overlap/token-alignment, not raw substring (injection-7) |
| **One calibrated fact posterior** | Four incommensurable confidence currencies; `G4` had to be disabled because there was no single number to threshold | Per-helper reliability diagram (ECE) vs frozen gold → fuse to one P(fact true); `domain/confidence.py` carries it (injection-6/grounding-1/state-10) |

This calibrated posterior is what the honesty gate (§4) thresholds on — replacing the ad-hoc per-rule floors
(`ASSEMBLER_CONF_MIN=0.6`, `MIN_REPEAT_SUPPORT`, disabled G4).

---

## 3. THE INJECTION LAYER (CL-3) — already specified; here's how it binds in
Stages **I0 FUSE → I1 LINK → I2 EXPAND → I3 TIER → I4 COMPILE** and the privacy/trust rules are fully designed in
`ops/CONTEXT_ENGINE_PHASE2B_INJECTION_LAYER_2026-06-23.md` §2. The blueprint adds three bindings:

- **EXPAND is local-snapshot-first** (CL-3): a cached **Wikidata/geo snapshot** answers the common case (institutions,
  landmarks, brands) with **zero network**; Brave ($5/1k, <1s) only for genuine misses, querying the **redacted typed
  span** (never pixels/GPS), text-only logged egress, with a hard local-only mode. Leak is measured as **bits of user
  context per enrichment**, not request count (injection-9/privacy-1,2,8). EXPAND runs in the **async brain**, cached,
  so the live path never stalls on the radio (injection-11/latency-5).
- **Corroborate the expansion against the device's own helpers before asserting** (injection-15): "MPI" + CoreLocation
  reverse-geocode → *which* Max-Planck (there are 80+). Frequency=confidence applied to the enrichment itself.
- **Two-zone packet is a hard wall** (CL-3, P6): `personal_evidence` (assertable as seen) vs `world_context`
  (assertable only as cited/hedged inference). A `world_context` token may **never** satisfy the verbatim-grounding
  check, so a web guess can't be laundered into "observed" (injection-8/grounding-6). Schema gets a source-class +
  external-TTL field so enrichments decay independently of capture (state-9).

---

## 4. THE HONESTY GATE + STAND-YOUR-GROUND (CL-4, CL-11)
**Standing ground is structural, not a prompt** — the codebase already declared prompt-tuned refusal dead
(`ask_home.py:2273`) and the literature agrees (SYCON-Bench / Cancer-Myth: no frontier LLM self-corrects a false
premise >30% of the time; injection doc §6). So:

- **Premise gate, pre-generation** (injection doc §3): extract the question's presupposition, check it against the
  `personal_evidence` zone → **ANSWER** (supported) / **CORRECT** (contradicted) / **REFUSE** (silent). The mode is an
  instruction handed to the LLM; the LLM does not get to choose its disposition.
- **Populate `refutation_cue`** (the single most-repeated gap — state-2/grounding-7/injection-12/entity-11) from real
  signals: presence_confidence below floor (`ask_home.py:2668`), a consensus read that contradicts the premise, OCR
  "MURAL/POSTER" where the question assumes a real object. CORRECT mode stands on a *cited* personal line, never a hunch.
- **Store absence as a fact** (state-12): honest helper refusals (`TEXT: NONE`, "no usable speech") become typed
  `Observation(kind='absence')` so the engine can assert "I looked and it was not there," not just "I have no data."
- **Symmetric error + channel-attributed refusals** (grounding-3/9): every refusal names the missing/low-confidence
  channel and a recovery action ("move closer / hold steady"); **over-refusal becomes a first-class metric** (the gate
  today only DEMOTES — false negatives are invisible, turning the honesty moat into a uselessness moat).
- **Authoritative-channel veto** (grounding-15): an honest OCR refusal vetoes a guessing VLM caption for that
  fact-type, closing the side channel through which guesses re-enter.
- **Surface cross-helper contradiction as uncertainty** (grounding-13) instead of silently picking by fixed priority.

---

## 5. THE PHYSICS: live / brain split, durability, privacy (CL-5, CL-9, CL-10)
The ~4–5W sustained ceiling and sub-5-tok/s on-device VLM are **not bugs to fix — they dictate the architecture.**

- **Duty-cycle by cost** (CL-5): live path = ANE-cheap helpers + **deterministic** (non-LLM) fusion; the per-distinct-
  frame LLM call in `consensus_read` (up to 20/query) moves to the async brain or a regex/box-aligned extractor.
  Heavy VLM = salience-triggered async enrichment. Salience becomes the explicit allocator of the thermal token-bucket,
  with **read-value (text density/legibility) as a first-class term** (CL-6/attention-14) and a capture-quality
  meta-helper that **refuses dark/blurry frames** instead of guessing (CL-14/acq-1, the no-sharpness-measure blind spot).
- **Never-delete hot/cold + per-fact-type validity** (CL-9): the native 100-fact cap + 1800s eviction is *amnesia* and
  contradicts the founder's "never delete; decay = retrieval cost" decision. Hot in-memory set + sqlite-vec cold store;
  validity windows are **per kind** (a building plaque is durable; a clock/board/occupancy is volatile). Stale volatile
  facts demote from "assertable" to "last seen at T" (grounding-12/injection-14) — useful without over-asserting.
- **The split is currently a lie** (CL-10): phone = dumb sensor, Mac = whole engine. Make the **event log the durable
  shared store** both paths project from; **idempotent** ingest (kills double-replay, topology-3); a **secured**
  device↔brain channel — today it is **plaintext HTTP + a hardcoded `dev-token`** (privacy-3/topology-14), a real
  security hole to close before any demo on an untrusted LAN. Offline = graceful local answering, not spool-and-pray.

---

## 6. BUILDABLE-TODAY STACK (the physics is on our side everywhere except the VLM)
| Capability | Component (ships now) | Number |
|-----------|----------------------|--------|
| OCR (live, +confidence) | Apple Vision `VNRecognizeText` / ML Kit | 0.31s +per-word conf / 0.05s |
| ASR | WhisperKit / iOS 26 SpeechAnalyzer | 2.2% WER, <0.5s |
| Embeddings | MiniLM-CoreML (ANE) | tens of ms |
| Store | sqlite-vec + SQLCipher/WAL | ~10^5 vec brute-force, encrypted |
| Entity linking | OpenTapioca/BLINK-style → local Wikidata | offline |
| Expansion (live miss) | Brave Search API | $5/1k, 95% <1s, no profiling |
| **Heavy VLM** | on-device VLM | **sub-5 tok/s, throttles ~1 min → async brain only** |

Everything except the heavy VLM is real-time on-device today. That single hard wall is *why* the live/brain split
exists — it is a thermal necessity, and it validates the existing design rather than contradicting it.

---

## 7. BUILD ORDER → re-anchored sprint board (WS0–WS7)
Cluster build order (synthesis §"BUILD ORDER"): **substrate → consensus-spine → stand-your-ground → expansion →
physics/durability → gate+eval → quality tail.** Mapped onto the existing board (`ops/CONTEXT_SPRINT_2026-06-23.md`):

| WS | Was | Re-anchored to the spine |
|----|-----|--------------------------|
| **WS0** | Native hero builds/deploys | Unchanged — unblocked (ContentView `[URL?]` fix); commit it. |
| **WS1** | Re-verify live capture; fix OCR accept=0 | + **capture-quality meta-helper** (CL-14): measure sharpness/legibility, refuse dark/blur. |
| **WS2** | Generalize the honest gate | = **CL-2 + CL-11**: consensus as default fusion + calibrated posterior + channel-attributed refusals + over-refusal metric. |
| **WS3** | Egocentric spatial-relations channel | = **CL-1 adjacency edges** (box co-location) feeding fusion — the binding substrate, not a bolt-on. |
| **WS4** | Cross-modal binding → episodes | = **CL-1 event log + persistent entities** (state-7) + cross-modal LINK (I1). |
| **WS5** | On-device Ask → cited answer/refusal | = **§4 premise gate + refutation_cue + two-zone packet**, verified on device. |
| **WS6** | Pitch surface + demo script | + the **context-first demo metric** (eval-13) so the core claim is falsifiable. |
| **WS7** | Trustworthy capture + founder gold + the number | = **CL-13**: bigger text-rich capture, **frozen human gold n≥100**, real `ask_home.ask` scored — **the pitch gate**. |
| **+WS8** | *(new)* | **CL-3 EXPAND**: local Wikidata/geo snapshot + Brave-on-miss + corroborate-before-assert. The centerpiece; depends on WS2–WS5. |
| **+WS9** | *(new)* | **CL-5/9/10**: thermal duty-cycle calibration, never-delete hot/cold, secured idempotent sync (close the `dev-token`/plaintext hole). |

**Sequencing rule:** WS3+WS4 (substrate) gate everything; WS2 (consensus+gate) and WS5 (stand-your-ground) come next
and are the demo; WS8 (expansion) is the magic but depends on the substrate; WS7 (real eval, big n) is the
go/no-go for "pitch-ready." Do **not** re-tune the 15-Q eval — it is overfit (grounding-14/eval-3).

---

## 8. THE EVAL GATE (CL-13) — what makes it pitch-ready
The current eval scores a **standalone consensus stub, not the shipped brain** (eval-4), on **n=15, not held out**
(±13% CI, eval-3/grounding-14). The gate to pitch-ready:
1. **Score the real `ask_home.ask`**, end to end, not a side stub.
2. **Frozen human gold, held-out, n≥100** answerable + trap questions (Apple Vision OCR must run **locally** — it
   fails in the Codex sandbox).
3. **Report 95% CIs** on every headline number (the founder is a physicist; he will ask for error bars).
4. **New metrics the matrix demands:** binding/attribution accuracy (eval-8), over-refusal rate (grounding-9),
   completeness (truncated read ≠ full correct, eval-12), false-premise CORRECT-rate vs false-contradiction rate
   (eval-7), expansion precision + privacy-cost (eval-9), and a **context-first** metric (eval-13).
5. **Target:** ≥40% strict recall / <10% hallucination **held on the full set with tight CIs** — the bar from the
   Phase-1 verdict, now measured honestly.

---

## 9. OPEN HARD-QUESTIONS (the risk register — what Phase-2 must measure, not assume)
These are the matrix's "Hard question (Phase 2)" cells, the things we genuinely do not yet know:
- **Does the typed packet beat the string** with the LLM held constant, or is the win purely in what the LLM does
  with the same text? (injection-1) — measure before committing the whole substrate as a *correctness* play vs an
  *enablement* play.
- **What fraction of real queries actually carry a usable anchor / reach consensus** (injection-2), and does forcing
  quorum on caption/world channels **over-refuse**? (the generalization risk)
- **What fraction of fused facts are actually expandable to a correct enrichment**, at what latency — is the magic
  >10% of queries or <10%? (injection-3)
- **Per-sign read-count distribution under thermal throttling** — does confidence-weighted quorum recover fast
  glances without admitting garble? (injection-13/state-14)
- **CORRECT mode's cost:** does standing ground raise *false* contradictions on true-premise questions? (injection-4)
- **Helper calibration:** does fused confidence predict correctness better than the single best channel (Brier/ECE)?
  (injection-6/grounding-1)
- **Over-refusal rate** at the chosen thresholds (grounding-9) — the uselessness-moat risk.

The discipline: **build the substrate (WS3/4) and the consensus-spine (WS2) first** because they are no-regret;
**measure** the open questions on the n≥100 gold (WS7) before scaling the expansion layer (WS8). Everything is
buildable today; the only hard wall is the VLM's thermal envelope, which the live/brain split already respects.

---
*Companion docs: synthesis (`…_SYNTHESIS_…`), grounding/repo-reality (`…_GROUNDING_…`), injection internals
(`…_PHASE2B_INJECTION_LAYER_…`), sprint board (`CONTEXT_SPRINT_…`). This blueprint supersedes scattered
architecture notes as the single spine.*
