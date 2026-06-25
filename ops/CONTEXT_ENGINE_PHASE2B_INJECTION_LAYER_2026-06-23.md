# Context Engine Phase 2B — The Injection Layer & the Standing-Ground Contract

*Author: the Chief. Founder: Satoshi (KIT; thesis at MPI-IPP Garching). Branch: `chief/p0-honesty-sprint`. 2026-06-23.*

> This document COMPLETES the architecture build the founder mandated. The prior
> generate phase produced the Phase-1 parameter matrix, the Phase-2 device/memory
> blueprint, the context-compiler audit, and a 30-question coverage matrix. Those
> built the HELPERS and the MEMORY. They never built the two pieces the founder
> described in his own words: (1) the INJECTION layer that expands raw helper
> output with live external knowledge before the model sees it, and (2) an answer
> model that STANDS ITS GROUND on a false premise instead of pivoting. This
> document is those two pieces, grounded in the real code seams and current tech.

---

## 0. Reconciliation (read first)

The four prior artifacts (`CONTEXT_ENGINE_PHASE1_PARAMETER_MATRIX`, `..._PHASE2_BLUEPRINT`,
`CONTEXT_COMPILER_AUDIT`, `CHIEF_DECISION_READING_FIRST`) carry a header that says
"reading-first; do not broaden." That header is **superseded** by the founder's
2026-06-23 PM directive: total architectural sovereignty, build the full
`Context -> Prompt -> Answer` paradigm, the product is broad CONTEXT not OCR. The
reading-first narrowing was a Mac-side eval crutch; `CONTEXT_SPRINT_2026-06-23.md`
already widened the build back to the full multi-modal engine. This document is the
ARCHITECTURE half of that widening (the sprint is the BUILD half). Where the prior
docs conflict with this one on scope, this one and the sprint win.

What does NOT change: the honesty discipline. Every widening here is gated by
grounded-or-refuse. The injection layer is allowed to make the engine *know more*;
it is never allowed to make the engine *lie more*. That is the whole reason the
layer is designed the way it is below.

---

## 1. Where the prior build stopped, exactly

The paradigm is three stages:

```
  HELPERS  ───►  INJECTION  ───►  LLM
  (perceive)     (compile +        (phrase the
                  EXPAND +          locked packet,
                  bind premise)     stand ground)
```

The prior docs built stage 1 (the helper society + observation contract) and the
*memory* substrate of stage 3 (event log, projections, behavior ledger). For
stage 2 they built only a **retrieval** planner: map the question to required
fact types, fetch matching personal observations, gate on coverage, refuse if
missing. In the live code that planner is `gather_evidence` / `build_evidence_dossier`
(`scripts/ask_home.py:1389`, `:1510`) feeding `COMMIT_ASSEMBLER_PROMPT`
(`:2282`).

Two things the founder asked for are absent from that seam:

1. **Expansion.** `build_evidence_dossier` only re-arranges what the helpers
   already emitted. There is no step that takes `OCR="089 289 112"` +
   `VLM="handwritten on an emergency notice"` + `place="MPI-IPP Garching"` and
   *resolves what that conjunction means in the world* before the model answers.
   The current assembler prompt actively **forbids** it: ask_home.py:2299 reads
   "Assert ONLY what is in the DOSSIER ... Do NOT add biography or any fact not in
   the text." That rule is correct for stopping hallucination, and it is exactly
   why expansion cannot be left to the model — it must be a *separate, sourced
   retrieval step* that turns world knowledge into more dossier lines with their
   own provenance, so "assert only what is in the dossier" stays literally true.

2. **Standing ground.** `COMMIT_ASSEMBLER_PROMPT` has three behaviors: answer,
   or refuse ("I don't have that in my memory"), or normalize spelling. It has no
   fourth behavior for "the question's premise is contradicted by my evidence."
   It says "if ANY line bears on the question, give the concrete answer it
   supports" — which, faced with a false premise, produces a compliant wrong
   answer. The founder's instruction ("the LLM should not pivot but stand on its
   ground and say the question was wrong") is a distinct, unimplemented mode.

This document specifies both, as structure rather than prompt-hope, because the
current evidence says prompt-hope fails (Section 6).

---

## 2. The Injection Layer — full technical breakdown

The injection layer is a five-substage pipeline that sits between the helpers and
the model. It runs continuously in the background (context-first: most of it is
done *before* the user asks) and finalizes at ask-time.

```
helper observations
  └─ I0  FUSE        bind co-occurring helper outputs into one situated frame
  └─ I1  LINK        resolve typed spans to stable identifiers (entity linking)
  └─ I2  EXPAND      privacy-safe external knowledge lookup on the LINKED frame
  └─ I3  TIER        tag every fact: personal_evidence | world_context, + confidence
  └─ I4  COMPILE     emit the two-zone evidence packet the model is locked to
```

### I0 — FUSE (cross-helper binding into a situated frame)

The helpers each see one channel. Fusion is where "frequency = confidence" already
lives in the app (the native fusion digest's `seen 252x`, `TraceLiveContextEngines.swift`).
I0 binds channels that share a time window and a spatial/entity anchor into a single
*situated frame*:

```json
{ "frame_id": "...", "t_window_ms": [.., ..],
  "subject": {"kind":"document", "candidate_id":"notice_07", "spatial_anchor":"wall, upper-right"},
  "channels": {
    "ocr":      {"value":"089 289 112 / Notruf 112 / Wichtige Rufnummern", "consensus_support": 6, "confidence": 0.71},
    "vlm":      {"value":"a printed safety notice; the number is hand-written in marker", "confidence": 0.6},
    "object":   {"label":"poster/notice", "track_id":"t12"},
    "place":    {"value":"MPI-IPP, Garching (48.256, 11.610)", "source":"corelocation+geocode", "confidence":0.9}
  } }
```

Rules: a channel value only enters the frame if it clears its own honesty gate
(OCR via cross-frame consensus, `scripts/consensus_recall.py`; VLM via the
attribute ladder; place via geocode confidence). FUSE never invents a binding —
two channels bind only on real shared anchors. This is the matrix's E (entity
continuity) and J2 (cross-source joins) made concrete at the injection seam.

### I1 — LINK (typed spans → stable identifiers)

I1 runs lightweight NER + entity-linking over the fused frame to attach
identifiers the expansion step can actually query. This is the on-device
equivalent of OpenTapioca / BLINK-style Wikidata linking — but the key design
choice is **link the typed observation, never the pixels**: the linker sees
`"089 289 112"` and `"MPI-IPP Garching"` as text, classifies the first as a
`phone_number` (deterministic regex/`libphonenumber`: `+49 89` = Munich area;
`289` = a known exchange) and the second as a `place/organization` it can resolve
against a local gazetteer. Determinism first, model second (matrix M3): numbers,
dates, phone formats, postal codes are extracted mechanically so they are stable;
only ambiguous spans escalate to a model.

Output: each span gets `{text, type, candidate_ids[], link_confidence}`. Low
confidence is allowed — it propagates, it does not get dropped or guessed.

### I2 — EXPAND (the live knowledge lookup — the founder's core idea)

This is the step the prior docs lacked. EXPAND takes the LINKED frame and asks an
external knowledge source what it means, then folds the answer back as *new,
sourced evidence lines*. For the notice: query roughly `"089 289" + "TUM Garching"
+ "emergency"` → resolve that `089 289` is the TU München Garching campus exchange
and that the Garching research campus (which co-hosts IPP) routes campus emergencies
through a campus security/dispatch number, i.e. the hand-written line is **the local
campus emergency dispatch number**, distinct from the printed public `Notruf 112`.

Five hard design questions, answered:

**(a) When does EXPAND fire?** Not on every span — that melts battery and floods
the packet. It is salience-gated (matrix C): fire when a span is novel (not in the
local cache), and *consequential* (a phone number on an emergency notice, a drug
name, an unfamiliar org, a sign in a language the user does not read) — and at
ask-time, always fire for spans the question targets. Familiar/cached spans skip
straight to the cache. This is exactly the "context before the prompt" property:
the IPP notice gets expanded the moment it is read and stably seen, so when the
founder later asks "what was that number for?", the answer is already compiled.

**(b) How does it stay private?** This is the web-vs-privacy paradox (Section 5),
resolved by four rules drawn from current locally-private-RAG work (LPRAG / locally
private entity perturbation, ScienceDirect 2025):
  1. **Query the redacted typed span, never raw media.** A frame, a face, a full
     screen, a GPS pair never leave the device. Only a minimized text token does
     (`"089 289 emergency Munich"`), and only after a redaction pass strips
     anything that co-identifies the user.
  2. **Local cache / on-device KB first.** A bundled gazetteer + a small embedded
     knowledge cache (sqlite-vec) answers the common cases (area codes, public
     institutions, common drugs/brands, transit) with zero egress. The network is
     the *fallback*, not the path.
  3. **Egress is text-only and logged.** Reuses the existing egress guard
     (`src/trace_memory` egress tests; the brain's frontier gate
     `TRACE_FRONTIER_ENABLED`, off by default). Every outbound query is recorded
     in the audit log so the user can inspect exactly what was asked of the world.
  4. **Decouple query from identity.** Expansion queries carry no user ID, no
     session join key, and can be padded with decoy queries (access-pattern
     defense, PRAG 2025) when the privacy mode demands it. The user can also set
     EXPAND to local-only, in which case uncached spans simply stay unexpanded
     (and the model is told so, and may refuse).

**(c) What does it return?** A small set of candidate world-facts, each with a
source URL/KB-id and a confidence, e.g.
`{claim:"089 289 is the TU München Garching telephone exchange", source:"...", conf:0.8}`,
`{claim:"the printed 112 is the EU public emergency number", source:"...", conf:0.97}`,
`{claim:"hand-written campus lines on IPP/TUM notices are local security dispatch", conf:0.45, hedge:true}`.
Low-confidence/hedged claims are KEPT but flagged — they inform the model's framing,
they never become asserted personal facts.

**(d) What it must NOT do.** EXPAND may identify/explain a thing that the helpers
observed. It may not invent that the user *did* anything. "This is the campus
emergency number" is world knowledge about an observed object. "You called it" or
"you wrote it" would be a personal claim and requires personal evidence — EXPAND
is forbidden from producing personal-channel facts. This separation is enforced in
I3, not left to the model.

**(e) Latency.** EXPAND on the live path is best-effort and async: the situated
frame is usable immediately with whatever expansion has completed; ask-time waits
at most a short bounded budget (the same class as near-live, 5–60s in the matrix's
L table) and otherwise answers from cache + personal evidence and notes that
expansion was incomplete. Expansion is never on the reflex (<1s) path.

### I3 — TIER (provenance separation: personal vs world)

Every fact carries a hard tag: `personal_evidence` (something a helper observed in
the user's life, citable to a time/place) or `world_context` (something EXPAND
retrieved about a referent). This is matrix K1 made enforceable. The two never
merge into one undifferentiated blob — the entire failure mode of "answers your
usual order from stereotypes" is a personal/world bleed, and tiering is the dam.
Each fact also carries the confidence/refutation it inherited from its channel.

### I4 — COMPILE (the two-zone evidence packet)

I4 extends `build_evidence_dossier` to emit a packet with two clearly delimited
zones plus the extracted premise (Section 3):

```
PERSONAL EVIDENCE (what your helpers observed — citable, the ONLY basis for personal claims):
  [OCR read @ 14:02, consensus x6, conf .71] notice text: "089 289 112 / Notruf 112 / Wichtige Rufnummern"
  [VLM @ 14:02, conf .6] the 089 number is hand-written in marker on a printed safety notice
  [PLACE @ 14:02, conf .9] MPI-IPP, Garching campus

WORLD CONTEXT (what this refers to — explanatory only, NEVER a personal fact):
  [web, conf .97] 112 is the EU-wide public emergency number
  [web, conf .8] "089 289" is the TU München Garching campus telephone exchange
  [web, conf .45, HEDGED] hand-written campus lines like this are typically a local security/dispatch number

PREMISE CHECK: <the question's presupposition, and whether PERSONAL EVIDENCE supports/contradicts/is-silent>
```

The model is locked to this packet. "Assert only what is in the packet" remains
literally true — EXPAND did not loosen grounding, it added a sourced, fenced zone.

---

## 3. The Standing-Ground Answering Contract

The founder: *if the person asks a wrong question, the LLM should not pivot but
stand on its ground and say the question was wrong.* This replaces the
two-mode (answer | refuse) `COMMIT_ASSEMBLER_PROMPT` with a **three-mode** contract,
and — critically — the mode is chosen by a structural gate BEFORE generation, not
by the model's disposition (Section 6 explains why that is non-negotiable).

**The premise gate (deterministic, pre-generation).** From the question, extract
its presupposition(s): a "when did I last buy coffee?" presupposes a coffee
purchase exists; "which bag was zipped?" presupposes a zipped bag was seen; "what
did the red sign say?" presupposes a red sign. Then check the presupposition
against the PERSONAL EVIDENCE zone:

| Premise vs personal evidence | Mode | Behavior |
| --- | --- | --- |
| Supported | **ANSWER** | phrase the grounded answer + cite times; EXPAND may enrich the framing |
| Contradicted | **CORRECT** | state plainly the premise is wrong, cite the contradicting evidence, give the true fact |
| Silent (no coverage) | **REFUSE** | name the missing helper class / time window; do not guess |

The model receives the chosen mode as an instruction and the packet. Three rules
bind it:

1. **World context explains, it never grounds a personal claim.** The model may
   say "112 is the public emergency number and 089 289 is the TUM Garching
   exchange, so the hand-written line is most likely the local campus emergency
   dispatch" — every clause there is either a cited world fact or an explicitly
   hedged inference over world facts. It may not say "you saved this as your
   emergency contact" — no personal line supports it.

2. **In CORRECT mode, do not yield under restatement.** If the user pushes
   ("no, the sign was blue"), the model holds the evidence-grounded position and
   repeats the citation. This directly imports the literature's finding that
   models capitulate under sustained pressure (SYCON-Bench) and the mitigation
   that adding correction exemplars + a third-person stance cuts that sharply
   (Section 6).

3. **Separate "premise false" from "I don't know."** A refusal says *I never
   observed that.* A correction says *I observed something that contradicts what
   you assumed.* Collapsing them (today's behavior) is what makes the system feel
   either evasive or sycophantic. They are different speech acts and the gate
   keeps them different.

Example renderings for the notice:
- ANSWER ("what number was hand-written on the notice?"): "089 289 112 — written
  by hand in marker on the IPP safety notice (read 14:02). For context, 112 is the
  public EU emergency line and 089 289 is the TUM-Garching exchange, so this is
  most likely the campus's local emergency/security number."
- CORRECT ("what's the printed emergency number, 911?"): "Not 911 — the notice
  prints 112, the EU emergency number (read 14:02). 911 is North American; it does
  not appear here."
- REFUSE ("whose handwriting is it?"): "I can't say — I read the number and saw it
  was hand-written, but no helper observed who wrote it."

---

## 4. The 089-289-112 walkthrough (the attached image, end to end)

1. **HELPERS.** OCR (consensus across the ~6 frames the founder dwelled on the
   wall) reads `089 289 112`, `Notruf 112`, `Wichtige Rufnummern`, `IPP
   Max-Planck-Institut für Plasmaphysik`. VLM notes the 089 line is hand-written
   marker over a printed form. Detector tracks one notice instance. CoreLocation +
   geocode places it at the Garching campus. Each clears its own honesty gate;
   garbled one-off reads are refused, not emitted.
2. **I0 FUSE.** One situated frame: a wall-mounted hand-annotated safety notice at
   MPI-IPP Garching containing those strings.
3. **I1 LINK.** `089 289 112` → `phone_number` (deterministic: +49 Munich `089`,
   exchange `289`). `IPP / Max-Planck-Institut für Plasmaphysik` → `organization`,
   linked to the Garching research campus.
4. **I2 EXPAND.** Cache miss on the specific number → minimized text query (no
   image, no GPS pair) → world facts: 112 = EU public emergency; 089 289 = TUM
   Garching exchange; hand-written campus lines ≈ local dispatch (hedged). Result
   cached locally so a re-encounter is zero-egress. This all happens when the
   notice is first stably seen — before any question.
5. **I3 TIER + I4 COMPILE.** Two-zone packet as in Section 2.
6. **LLM, days later, user asks "what was that emergency number on the wall at the
   institute?"** Premise gate: presupposes an emergency number was seen → PERSONAL
   EVIDENCE supports it → **ANSWER** mode. Output: the hand-written `089 289 112`,
   cited to the read, framed with the world context that it is the campus dispatch
   line and distinct from the public `112`. The founder gets *the number plus what
   it is for* — which neither a captioner-with-a-camera (no memory) nor the
   pre-injection brain (forbidden from world knowledge) could produce.

Honesty note carried through: the "campus dispatch" identity is hedged
world_context (conf .45), so the model frames it as "most likely," not as fact.
The architecture is *more useful* without becoming *more confident than the
evidence warrants*. That is the entire point.

---

## 5. The new paradoxes, resolved

1. **Web expansion vs privacy.** Resolved by I2's four rules: query the redacted
   typed span not the pixels; local KB/cache first; text-only logged egress;
   identity-decoupled (optionally decoyed) queries, with a hard local-only mode.
   The thing that leaves the device is a search token any passer-by could have
   typed, never the user's life.
2. **Expansion vs hallucination.** Resolved by I3 tiering + the contract's rule 1:
   world facts are fenced and sourced; they explain referents, they never become
   personal claims; hedged claims stay hedged. EXPAND can be wrong about the world
   without ever fabricating the user's life — and being wrong about the world is
   bounded by source citation and confidence, the same discipline as every other
   channel.
3. **Standing ground vs the engine itself being wrong.** Standing ground is
   anchored to PERSONAL EVIDENCE, not to the model's pride. The model corrects a
   premise only when a *cited* personal line contradicts it. If the contradiction
   is only in hedged world_context, it raises the discrepancy ("the notice shows
   112; I'm less sure about the hand-written line") rather than overruling the
   user. Conviction scales with grounding.
4. **Context-first vs expansion latency.** EXPAND is background + cached, so the
   common case is pre-compiled. Ask-time expansion is bounded and degradable: a
   slow/absent network yields "answered from what I'd already looked up," never a
   stall and never a stale guess.

---

## 6. Why standing-ground must be structural, not a prompt (evidence)

Current measurements say a model will not reliably resist a false premise on its
own. On the Cancer-Myth benchmark, **no frontier LLM corrected more than 30% of
false presuppositions** (Gemini-1.5-Pro 27.2%, Claude-3.5-Sonnet 19.8%,
GPT-4-Turbo 15.4%). SYCON-Bench shows models progressively capitulate under
multi-turn user pressure. So "tell the model to stand firm" is the failure path.

The architecture's answer: make the *premise gate* deterministic (extract
presupposition, check against the evidence zone, select CORRECT mode before
generation), and only then ask the model to phrase a correction it has already
been told is warranted. The literature's two cheap, real mitigations are baked in:
a **third-person framing** of the evidence (cuts sycophancy up to ~63.8% in the
debate setting) and **correction exemplars** in the answer prompt. This mirrors
how the live brain already beat the model's bad disposition once: the
structural_grounding gate (ask_home.py:2280) replaced prompt-tuned refusal because
"prompt-tuning the refusal rule is dead; the structural gate works." Same pattern,
new behavior.

---

## 7. Where it plugs into the real code

| Substage | Lands at | Reuse |
| --- | --- | --- |
| I0 FUSE | extend the native fusion digest (`TraceLiveContextEngines.swift`) + `consensus_recall.py` window | the `seen Nx` consensus already there |
| I1 LINK | new `scripts/inject_link.py` (deterministic extractors + local gazetteer) | matrix M3 determinism-first |
| I2 EXPAND | new `scripts/inject_expand.py` behind the existing egress/frontier gate (`TRACE_FRONTIER_ENABLED`) + sqlite-vec local cache | egress guard in `src/trace_memory` |
| I3 TIER | a `tier` field on the observation contract (already has `source_channel`, `confidence`, `provenance`) | `src/trace_memory/domain/observation.py` |
| I4 COMPILE | extend `build_evidence_dossier` (ask_home.py:1510) to two zones + premise line | the dossier already tags source+time |
| Premise gate + 3-mode | new `premise_gate()` before `COMMIT_ASSEMBLER_PROMPT`; rewrite that prompt to 3-mode with exemplars | structural gate pattern at ask_home.py:2280 |

Bounded build order (each step independently verifiable; Chief verifies, not the
agent's self-test):
1. Premise gate + 3-mode contract over the *existing* dossier (no expansion yet) —
   measurable immediately against a false-premise question set.
2. I3 tiering on the observation contract (additive field).
3. I1 LINK + I4 two-zone compile (local gazetteer only, zero egress).
4. I2 EXPAND, local cache only, then gated network fallback.
5. Wire the live fusion frame as the anchor for the whole pipeline.

---

## 8. Falsifiable eval (the two new behaviors get their own numbers)

The honesty contract demands these are measured, not asserted.

- **Expansion correctness/safety.** On a set of read-in-the-world items (signs,
  numbers, drugs, transit, institutions): % whose world_context is correct, %
  hedged-when-uncertain, and ZERO personal claims produced from world_context
  (any such bleed is a hard fail). Plus an egress audit: every query was
  text-only and logged.
- **False-premise correction rate.** Build a question set whose premises the
  walk evidence contradicts. Target: structural gate should clear the ~20–30%
  frontier baseline by a wide margin precisely because it does not rely on the
  model's disposition — and crucially, hold position under one restatement
  (a mini SYCON-style second turn).
- **Both fold into the one metric** that governs everything: % of what the
  founder can read/perceive that the system answers correctly, lies near zero —
  now extended so "correct" can include a correct CORRECTION and a correctly
  framed world-context, and "lie" includes any world fact smuggled in as a
  personal one.

---

## 9. The one-paragraph blueprint

The engine perceives continuously with a society of honesty-gated helpers; the
**injection layer** fuses their co-occurring outputs into situated frames, links
the typed spans to identifiers, **expands** the consequential ones with
privacy-safe external knowledge (redacted text queries, local-cache-first,
text-only logged egress), and compiles a two-zone evidence packet that keeps
personal observation and world knowledge strictly apart; a deterministic premise
gate then routes each question to ANSWER, CORRECT, or REFUSE, and the model phrases
only that locked packet — grounding personal claims solely in personal evidence,
using world context to explain rather than to invent, and standing its ground on a
false premise because a cited line, not the model's temperament, tells it to.
That is HELPERS → INJECTION → LLM, built to know more without lying more.

## Sources (current-tech anchors)

- Cancer-Myth, false presuppositions in patient questions: https://arxiv.org/pdf/2504.11373
- SYCON-Bench (EMNLP 2025), multi-turn sycophancy: https://github.com/JiseungHong/SYCON-Bench
- DecoPrompt, decoding under false premises: https://arxiv.org/pdf/2411.07457
- Locally private entity perturbation for RAG (IPM 2025): https://www.sciencedirect.com/science/article/abs/pii/S0306457325000913
- PRAG, end-to-end privacy-preserving RAG / access-pattern defense: https://arxiv.org/html/2604.26525v1
- OpenTapioca, lightweight Wikidata entity linking: https://arxiv.org/pdf/1904.09131
