# SOMA: An Input-Only Wearable Memory — Architecture, Rationale, and References

*A comprehensive technical exposition of the SOMA architecture: its conceptual
foundations, formal design, implementation strategy, evaluation methodology,
and its relationship to prior art. The companion diagram-first walkthrough is
[`ARCHITECTURE_VISUAL.md`](ARCHITECTURE_VISUAL.md).*

---

## Abstract

SOMA is a wearable memory system built on a single uncompromising invariant:
**raw media never persists and never egresses; only typed text may leave the
device.** On-device perception converts the live world into open-vocabulary,
provenance-bearing text observations at the moment of capture; the raw pixels
and audio are discarded within milliseconds. A nightly consolidation process
binds scattered observations into a typed evidence graph by spatio-temporal
co-occurrence, attaching a calibrated confidence to every link and refusing
weak ones. A recall engine answers unconstrained natural-language questions
from this bound text alone, citing the observations that support each claim
and refusing honestly when the answer was never perceived. The architecture is
realized as a hexagonal, event-sourced Python monolith (`src/soma/`), with a
salience-gated perception loop (`soma_perception/`) and a legacy answer engine
being replaced through a strangler-fig migration. Success is measured by two
metrics designed to make failure diagnosable: RAS (recall accuracy minus
fabrication) and OAG (the oracle-answerability gap between raw footage and the
retained text). This document states the thesis behind each decision, derives
the architecture from first principles, maps it to the codebase, and situates
every major choice in the research and engineering literature.

---

## Table of contents

1. [Introduction and problem statement](#1-introduction-and-problem-statement)
2. [Conceptual foundations](#2-conceptual-foundations)
3. [Prior art and how SOMA differs](#3-prior-art-and-how-soma-differs)
4. [Design invariants](#4-design-invariants)
5. [The pipeline: from photons to answers](#5-the-pipeline-from-photons-to-answers)
6. [The domain model](#6-the-domain-model)
7. [Software architecture: hexagonal, event-sourced, strangler-fig](#7-software-architecture)
8. [The perception subsystem and the attention scheduler](#8-the-perception-subsystem-and-the-attention-scheduler)
9. [Consolidation: the binder ("SLEEP")](#9-consolidation-the-binder-sleep)
10. [Recall: grounded answering with refusal](#10-recall-grounded-answering-with-refusal)
11. [Privacy architecture](#11-privacy-architecture)
12. [Evaluation methodology](#12-evaluation-methodology)
13. [Engineering governance](#13-engineering-governance)
14. [Open problems and honest risks](#14-open-problems-and-honest-risks)
15. [Glossary: napkin term → production term](#15-glossary)
16. [References](#16-references)

---

## 1. Introduction and problem statement

People forget most of their lives. Where the keys were left, what the doctor
actually said, whether the door was locked, the name attached to a face met
once — the moments that matter are sparse, unpredictable in advance, and gone
by the time they are needed. The obvious remedy — record everything — fails
twice: continuously stored video is a surveillance liability that no one should
wear and no bystander should tolerate, and raw footage is the wrong artifact
anyway. Nobody rewatches their life; they *ask questions about it*. The
valuable artifact was never the footage — it was the bound, queryable meaning.

SOMA's problem statement, then, is precise:

> Build a system that perceives a person's day through always-on cheap senses,
> converts everything to words the instant it happens — never keeping one frame
> of video or one second of audio — consolidates those words into
> understanding, and later answers arbitrary questions from that understanding
> with citations, or refuses honestly.

The central hypothesis (stated as unvalidated in `ops/ROADMAP.md` §2, because
intellectual honesty about it is the whole game):

> Perception can be decomposed into channels that reconstruct *lossless-enough
> context* — a complete, continuous spatial/temporal/audio scaffold — such
> that a tractable reasoner answers arbitrary retroactive questions, including
> hard spatial ones, at near-zero hallucination.

Everything in this document is machinery for validating or falsifying that
hypothesis as fast as possible.

## 2. Conceptual foundations

### 2.1 The standard model of perception

The founding sketch begins from the observation that a brain never touches the
world directly: all information arrives through senses, and for a manufactured
system the practical senses are cameras (eyes) and microphones (ears), because
those are the senses we can cheaply build and because most task-relevant
information flows through them. SOMA copies this shape deliberately: *World →
senses → brain*, with one radical amendment — the brain keeps only the
linguistic output of the senses, never the sensory stream itself.

This has a respectable cognitive-science pedigree. Human episodic memory is
not a video archive; it is a sparse, reconstructive, semantic encoding of
experience [1][2]. Tulving's distinction between episodic memory (events
located in time and place) and semantic memory (consolidated knowledge) [1]
maps directly onto SOMA's two stores: the time-stamped observation log
(episodic) and the bound evidence graph (semantic). Consolidation during sleep
— replaying the day's traces and binding them into durable structure — is a
real property of biological memory systems [3], and SOMA's nightly "SLEEP"
binder is a deliberate imitation of it. Event Segmentation Theory [4] supports
another SOMA choice: humans encode experience as discrete events bounded by
change, which is why capture is *change- and attention-gated* rather than
uniform.

### 2.2 Text as the retention format

Choosing *text* as the sole persistent representation is the load-bearing
decision. The arguments for it:

1. **Privacy is structural, not promised.** A store that physically contains
   no pixels cannot leak pixels. This is privacy-by-design in Cavoukian's
   original sense — protection embedded in the architecture, not bolted on as
   policy [5] — and data minimization in the GDPR Article 5(1)(c) sense [6]:
   collect the meaning, not the medium.
2. **Text is the interlingua of modern reasoning.** Large language models
   reason over text natively; a text store makes every future model, local or
   frontier, a drop-in brain [7].
3. **Text is cheap.** A day of typed observations is kilobytes to megabytes;
   a day of video is tens of gigabytes. Losslessness of *context* (not media)
   becomes affordable to keep forever.
4. **Text is auditable.** A human can read exactly what the system knows about
   them; no one can read what a neural embedding of their kitchen contains.

The cost is equally explicit: anything the perceivers failed to verbalize is
gone forever. The entire evaluation apparatus (§12) exists to measure exactly
that loss.

### 2.3 Attention as the economic principle

"Maximum context" and "detail follows attention" are in tension: you cannot
run a deep vision model on every frame of an all-day stream on phone hardware,
and most moments do not matter anyway. SOMA's resolution (`ops/NORTH_STAR.md`):
**capture everything cheaply, perceive deeply only what attention marks.**
Cheap, always-on narrow channels (OCR, ASR, sound events, sensors) provide the
continuous scaffold; an expensive vision-language model is invoked only where
a salience signal — dwell, novelty, change — marks a target as worth deep
perception. This mirrors saliency-based models of biological visual attention
[8] and foveated perception generally: a wide cheap periphery and a narrow
expensive fovea, with a scheduler deciding where the fovea points. The
scheduler is treated as the moat — a first-class component, not an
afterthought.

## 3. Prior art and how SOMA differs

**Lifelogging.** MyLifeBits [9] and the Microsoft SenseCam [10] pioneered
total capture of personal experience, and SenseCam showed real memory-aid
value in clinical populations. Both, however, are *storage-first*: they retain
the raw media, inheriting the surveillance problem, the retrieval problem
(nobody rewatches), and the cost problem. SOMA inverts the premise: capture is
total, *retention* is linguistic.

**Egocentric vision research.** Ego4D [11] and its successors established
episodic-memory benchmarks over egocentric video ("where did I last see X?"),
demonstrating both the demand for the capability and the current cost of
answering from raw video. SOMA's bet is that answering from *derived text* can
approach the raw-video oracle — and OAG (§12) measures the distance.

**Retrieval-augmented generation.** SOMA's ASK stage is structurally RAG [12]:
retrieve evidence, generate from it, cite it. The differences are that the
corpus is machine-perceived rather than authored, provenance is mandatory at
the datum level, and refusal is a first-class outcome tuned toward zero
fabrication rather than maximum answer rate (selective prediction, [13]).

**Commercial wearable recorders/assistants.** Products that persist audio
recordings or stream video to the cloud occupy the surveillance quadrant SOMA
is architecturally incapable of entering. The market thesis
(`ops/MARKET_AND_SCOPE.md`) is precisely that the input-only quadrant is
empty: always-on perception with nothing to subpoena, leak, or replay.

**Knowledge graphs.** The evidence graph is a property graph of
entity–predicate–object triples with confidence and provenance — standard
knowledge-representation practice [14] — but deliberately open-vocabulary:
observation kinds and predicates are not drawn from a fixed schema, because a
fixed question-type surface was explicitly rejected (`ops/NORTH_STAR.md`).

## 4. Design invariants

These are locked; code that violates them does not merge.

- **I1 — No raw persistence.** Raw pixels/audio are discarded the instant
  words are extracted. (Enforced in capture code; defense-in-depth in
  `.gitignore`; live proof is a Phase 1/4 gate — see §14 on current honesty.)
- **I2 — Text-only egress.** Only `TextEgress` — typed text carrying source
  event IDs — may cross the device boundary. Enforced by
  `EgressGuard` (`src/soma/application/egress_guard.py`), which raises
  `PrivacyViolationError` on any other payload.
- **I3 — Append-only truth.** The observation log is immutable and is the
  single source of truth. All derived structure (graphs, indexes) is a
  disposable, replayable projection.
- **I4 — Provenance everywhere.** Every observation, binding, answer citation,
  and egress payload carries the event IDs it derives from. An unsourced claim
  is a bug by construction (`Binding.__post_init__` rejects empty evidence).
- **I5 — Calibrated confidence; refusal over fabrication.** Every binding has
  a confidence in [0,1]; weak links are refused, not hardened. A confident
  wrong answer is catastrophic; "I don't know" is a win. Hallucination → 0 is
  the invariant across all phases.
- **I6 — Unconstrained questions.** No fixed question taxonomy. Open-vocabulary
  observations + grounded retrieval + calibrated refusal, not a menu.
- **I7 — Nothing is built until a missed question demands it.** The
  anti-diversion law: every helper, sensor, and feature must be authorized by
  a diagnosed failure on a real question (`ops/ROADMAP.md` §10).

## 5. The pipeline: from photons to answers

The founding sketch decomposes execution into black boxes; each is now a named
subsystem. In order:

1. **Sensing.** Video (eyes) and audio (ears), plus device sensors
   (IMU/pose/GPS) — the cheap channels that are kept losslessly because they
   are tiny. Egomotion is a first-class input, not an afterthought: it is what
   answers "which floor / which side" [15].
2. **Extraction ("Extraction Black Box").** Frame gating discards blurry,
   low-signal frames; the remainder yield *coordinates + timestamps + context*
   — the spatio-temporal scaffold every later stage hangs facts on.
3. **Macro understanding.** A small VLM produces a scene gist — "a macro
   picture of what's happening" — only when attention, dwell, or change
   justifies the cost (§8).
4. **Specialist helpers.** Task-specific perceivers are called as needed: OCR
   for visible text, ASR for speech, a sound-event tagger, an object
   detector/tracker. Each emits *text marked by coordinates* — typed
   `Observation`s. The helper set is discovered empirically, never guessed
   (I7): the questions the system misses name the next helper to build.
5. **Binding.** The Binder fuses observations across channels by co-occurrence
   in time and space — "binding the coordinates, physicality and temporality
   together" — producing raw material for consolidation. This is the classic
   binding problem of multi-sensor fusion [16] restated over text.
6. **Node creation ("Node Creation Black Box").** Consolidation turns raw
   material — "a first thought that can be marinated on" — into living nodes:
   entities and bindings that *combine to derive new things* (the napkin's
   "1 + 1 = 4"): which hum was the laptop fan, which blue thing was the bag,
   which name belongs to which face. It runs continuously in the background
   but does its deep work nightly. Its store is encrypted so that only the
   user's app can decipher it (§11).
7. **Selective forgetting.** The discarder drops *marinated content that
   proved useless — never the raw material*. In production terms: projections
   are disposable; the append-only log is forever (I3).
8. **Information supply ("Information Supplier Black Box").** At question
   time, retrieval navigates the evidence graph and assembles **just enough
   context** for the reasoner — not the whole day, which no context window
   holds and no local model needs [12].
9. **Reasoning.** "The LLM does what LLM does": a commodity reasoner at the
   end of the pipe — local first (Gemma 3 [17], Qwen2.5-VL [18]), with a
   measured text-only escape hatch to a frontier model when local quality is
   the wall (I2 guarantees the hatch is safe).
10. **Answer or refusal.** Every claim must trace to cited observations
    (grounding gate, Phase 3); otherwise the system refuses.

## 6. The domain model

The domain layer (`src/soma/domain/`) is deliberately tiny — seven frozen
dataclasses, each a value object [19] whose constructor is the boundary where
invariants are enforced:

- **`Observation`** — the atom of memory. Open-vocabulary `kind` and
  `subject`, a tuple of `Attribute` name/value pairs, capture time `t_ms`, an
  optional `spatial_anchor`, a `Confidence`, a `Provenance`, and an optional
  `refutation_cue` (a hint about what evidence would *disprove* it — falsifiability
  designed into the datum). Construction rejects empty kinds, negative times,
  and any mismatch between observation time and provenance time.
- **`Provenance`** — event ID, source channel, capture time. Nothing exists
  without it (I4).
- **`Confidence`** — a probability constrained to [0,1] at the type boundary.
  The intent is *calibrated* confidence in the sense of [20]: a 0.8 should be
  right about 80% of the time, because thresholded refusal (I5) is only
  meaningful over calibrated numbers.
- **`Entity`** — a stable identity (id, kind, label) that observations resolve
  to during consolidation.
- **`Binding`** — the edge: subject–predicate–object with exactly one object
  target (an entity *or* free text), a confidence, and a non-empty evidence
  tuple. `is_usable(minimum_confidence)` is the refusal gate in domain form.
- **`Query` / `Citation` / `RecallAnswer`** — the ASK contract: answers carry
  citations to node IDs and timestamps.
- **`TextEgress`** — the only exportable type: non-empty text plus non-empty
  source event IDs (I2 + I4 in one constructor).

## 7. Software architecture

Three architectural patterns govern `src/soma/`, each chosen for a specific
failure mode it prevents.

### 7.1 Hexagonal (ports and adapters)

The layout follows Cockburn's hexagonal architecture [21] (equivalently, Clean
Architecture's dependency rule [22]): `domain/` is pure and imports nothing
concrete; `application/` orchestrates use cases against `ports/` — seven
`typing.Protocol` interfaces (`Perceiver`, `Ocr`, `Asr`, `VlmRunner`,
`TextReasoner`, `MemoryStore`, `RecallBackend`); `adapters/` implement the
ports against real infrastructure (Apple Vision OCR, MLX VLM, Ollama, SQLite,
a cloud text reasoner). The payoff for this codebase in particular: the same
domain and application code must ultimately run against a Swift/iOS device
stack, a Mac processing stack, and pure in-memory test doubles. Ports make
substrate migration a matter of new adapters, not rewrites — and the
perception scheduler is explicitly written to be "portable 1:1 to Swift"
(`soma_perception/scheduler.py`).

### 7.2 Event sourcing + CQRS-style projections

The capture core is event-sourced [23]: every perceiver emission is appended
to an immutable SQLite log (`adapters/sqlite_eventlog.py` — the public API has
no update or delete). Derived read models — the evidence graph, vector indexes
(`adapters/vector_index.py`) — are projections in the CQRS sense [24]:
disposable, rebuildable by replay, free to change shape as understanding
improves. This buys, for free: deterministic replay (the backbone of offline
evaluation), audit (I4), crash-safety, and the discarder semantics of §5.7 —
you can always throw away a bad consolidation and re-marinate, because the raw
material is never touched.

### 7.3 Strangler fig

The functioning-but-legacy answer engine — `scripts/ask_home.py`, ~2,900 lines,
47 broad excepts — is not rewritten big-bang; it is contained behind the
`Recall` use case via the `LegacyAskHome` adapter and replaced capability by
capability: Fowler's strangler-fig pattern [25]. The application boundary is
honest about this: `binder.py`, `capture_scheduler.py`, and
`grounding_gate.py` exist today as named Phase 2/1/3 entry points, so the
target architecture is visible in the code before it is implemented.

## 8. The perception subsystem and the attention scheduler

`soma_perception/` is the live CAPTURE loop:

- **`worker.py`** — always-on cheap detection: an object detector/tracker
  (currently YOLO-family via Ultralytics [26] on the Mac substrate;
  MobileCLIP-S0 zero-shot naming [27] on the device substrate, chosen because
  it is ANE-fast, emits words not prose, and grows vocabulary without
  retraining) maintains persistent tracks with dwell and motion statistics.
- **`scheduler.py`** — the moat. Pure logic, no I/O, injected clock. Salience
  is scored as `dwell_progress × (0.6·novelty + 0.4·stability)`; a token
  bucket [28] enforces a hard hourly enrichment budget so the loop survives
  all-day on phone thermals. Decisions ride a **progressive enrichment
  ladder** — `overview → attributes → minutiae` — where each level costs a
  budget token and demands ~3× the accumulated dwell of the previous: depth of
  attention literally buys depth of knowledge.
- **`enricher.py`** — the expensive eye: crop + level → local multimodal model
  (Gemma 3 via Ollama [17][29]) → **delta facts only**. Levels 2–3 prompts
  include what the graph already knows and ask only for what is new; "nothing
  new" is an acceptable answer; and the prompts encode hard-won
  anti-hallucination rules ("a confident wrong material is worse than none").
- **ASR** — speech-to-text via Whisper-class models [30]; sound-event tagging
  covers the non-speech channel (cry/alarm/hum).
- **Spatial scaffold** — on device, ARKit provides 6-DOF pose and
  relocalizable world maps [15]; egomotion is captured continuously as a cheap
  channel (I7 authorized it: spatial questions were the diagnosed (A) misses).

## 9. Consolidation: the binder ("SLEEP")

The binder's job is cross-channel identity resolution over text: cluster the
day's observations by temporal and spatial co-occurrence, resolve them to
entities, emit `Binding`s with calibrated confidence, and refuse weak links
outright (I5). Design commitments, from `ops/NORTH_STAR.md` and
`ops/ROADMAP.md` §5:

- **Accelerator, not gatekeeper.** Night-bind builds an index that speeds
  navigation; it is never the only path to context. The reasoner can always
  fall back to the raw observation scaffold, so a bad consolidation can slow
  answers but cannot destroy information.
- **More signals ≠ better answers.** Every added signal needs a confidence;
  an undisciplined binder turns context into noise and drives hallucination up,
  not down. Refusal of weak links is the design's immune system.
- **Always running, better nightly.** Incremental binding runs in the
  background; the deep pass runs nightly when the device is charging and
  thermal budgets are irrelevant — the same economics that shaped biological
  sleep consolidation [3].

Status honesty: as of Phase 0 both binder prototypes still produce zero
entities/bindings (`docs/PHASE0_REPORT.md`); the binder is the Phase 2
target, and the current evaluation numbers are achieved *without* it — which
is itself evidence for the "brain, not sensors" diagnosis of §12.

## 10. Recall: grounded answering with refusal

ASK is an agentic loop, not a single prompt: the day does not fit any context
window, so the reasoner *navigates* — timeline first, then egomotion track,
then deep visual notes for a moment, cross-checking audio — iterating until it
can answer **with citations** or must refuse (`ops/ROADMAP.md` §5). The
architecture is RAG [12] hardened into a verification pipeline:

1. **Retrieval** over projections (temporal index, vector index, entity graph).
2. **Assembly** of *just enough context* — evidence dossiers, not data dumps.
3. **Generation** by a swappable `TextReasoner` (local Gemma/Qwen first; the
   text-egress hatch to a frontier model is a measured decision, not a
   default).
4. **Grounding gate** (Phase 3, `application/grounding_gate.py`): claim-level
   verification that every assertion in the draft answer traces to evidence
   nodes — the architectural response to the attribution problem in generative
   QA [31], targeting hallucination in the [32] sense.
5. **Selective answering** [13]: beneath the confidence floor, the system
   refuses. RAS scoring (§12) makes refusal strictly better than fabrication,
   so incentives and metric agree.

Every answer also logs *what the brain looked at*, which is what makes failure
diagnosis mechanical rather than anecdotal.

## 11. Privacy architecture

The moat is that surveillance is *architecturally impossible*, not merely
promised. Defense in depth, layer by layer:

1. **Ephemerality at the source (I1).** Raw media exists in memory for the
   milliseconds between capture and text extraction. There is no "record"
   path. (The honest caveat of §14 applies until the live gate proves it.)
2. **Typed egress (I2).** `TextEgress` is the only type the boundary accepts;
   `EgressGuard` rejects everything else at runtime, and the payload must name
   its source events — so even exported text is auditable back to capture.
3. **Encryption at rest.** `adapters/encrypted_text.py` implements AES-256-GCM
   authenticated encryption [33] (SHA-256-derived key, random 96-bit nonce,
   version-authenticated as associated data, with a legacy-format read path).
   The napkin's "encryption, i.e. people using our app can decipher" is this
   codec: the memory is unreadable to anything but the user's own app.
4. **Repository hygiene.** `.gitignore` blocks raw video/audio/HEIC globally
   as defense-in-depth, and the commit gate verifies zero media binaries
   staged (`docs/PHASE0_REPORT.md`).
5. **Regulatory alignment.** Text-only, minimal, purpose-bound retention is
   data minimization [6]; user-decipherable-only storage aligns with
   privacy-by-design [5]. What is never stored can never be breached,
   subpoenaed, or repurposed.

## 12. Evaluation methodology

The evaluation design is the most opinionated part of the system: it is built
so that **every failure names the work that fixes it.**

**RAS — Recall Accuracy Score.** `RAS = (correct − made-up) / total` over a
blind adversarial question battery on a real capture. Fabrication is
*subtracted*, not merely un-credited: a made-up answer costs what a correct
one earns. Hallucination must approach zero; the qualitative bar is "a
stranger asks about your day and is amazed, with near-zero made-up answers."

**OAG — Oracle-Answerability Gap** (`src/soma/eval/oag.py`). Among questions
an offline oracle *with the raw frames* can answer, the percentage the
on-device text memory cannot. OAG isolates capture loss from reasoning
failure: raw media is oracle-only evaluation input and never enters production
recall. This is the direct measurement of §2.2's stated cost — what
verbalization threw away.

**(A)/(B) diagnosis.** Every miss is mechanically classified: **(A)** the fact
was never captured (→ build the missing channel) or **(B)** the fact was in
the store and the brain failed to use it (→ fix binding/retrieval/refusal).
The answer-time "what did the brain look at" log makes this classification
evidence-based. Current honest baseline (92s walk clip, 25 adversarial
questions): RAS 40.0, hallucination 27.3%, **8 of 9 misses diagnosed (B)** —
the wall is the brain, not the sensors; the one (A) was head-pose, which
authorized the egomotion channel (I7 in action).

**Sufficiency → necessity → efficiency** (`ops/ROADMAP.md` §4). First prove
the hypothesis with brute force offline (deep VLM on every frame, full
sensors — thermal limits don't apply to a recorded clip). Then ablate one
channel at a time to discover the empirically load-bearing helper set. Only
then optimize, bringing back the salience scheduler to approximate the
necessary set cheaply. Capability is never confused with efficiency, and
pruning is measured, never intuited.

**Anti-overfit guard.** Frozen gold sets with hash-verified integrity
(`evaluation/oag/v2/gold/`), and a cold, never-tuned-on second capture must
pass before any external claim — the Phase 0 report explicitly flags the
current validation clip as tuning-contaminated rather than hiding it.

## 13. Engineering governance

The merge gate (`make check`, mirrored in the pre-push hook and CI) enforces:
formatting and linting (ruff), `mypy --strict` on domain and application,
cyclomatic-complexity and function-length ceilings, no dead production code
(vulture), frozen-gold hash verification, focused evaluator tests, and ≥80%
domain/application coverage (87% at Phase 0). Process governance is equally
explicit: one canonical roadmap file read first and updated last every
session, and the plan-gate — before any build, name the roadmap item and the
missed question that authorizes it (I7). The gate exists because the failure
mode it prevents was actually observed: a "3D world render" was built that no
question needed, and was killed.

## 14. Open problems and honest risks

- **The central hypothesis is unvalidated.** Lossless-enough text context may
  not exist for hard spatial/visual questions; OAG is the falsifier.
- **The live privacy invariant is not yet proven.** `.MOV` files and
  replay-based evaluation artifacts predate the architecture; they are
  migration inputs and oracle material, and the README states plainly that the
  live no-raw-persistence invariant is a target with a gate, not a current
  fact.
- **The binder does not exist yet** (Phase 2). Everything currently answered
  is answered from unbound observations plus the legacy engine.
- **Local models may be the wall.** Gemma-12B / Qwen-VL-7B may cap answer
  quality; the mitigation (text-egress hatch, I2-safe) is designed but must be
  *measured against* local, not assumed.
- **Hallucination is at 27.3% against an invariant of ~0.** The diagnosis
  says the fix is binder/refusal calibration, not more sensors — Phase 2/3's
  burden of proof.
- **Bystander ethics.** Input-only design removes stored media, but perceiving
  other people into text at all carries consent questions the product must
  face beyond architecture (retention policy, on-device redaction of
  bystander speech, disclosure norms) [34].
- **Overfit risk.** One hero clip dominates tuning; the cold-capture guard is
  the control, and it has not passed yet.

## 15. Glossary

| Napkin / product term | Production term | Code |
|---|---|---|
| Extraction Black Box | Capture pipeline (perceivers + frame gating) | `soma_perception/`, `ports/perceiver.py` |
| Specialized eyes / helpers | Perceiver channels (OCR, ASR, detector, sound events) | `ports/{ocr,asr,vlm_runner}.py` |
| Macro picture → VLM | Salience-gated scene gist / enrichment | `soma_perception/{scheduler,enricher}.py` |
| Text marked by coordinates | `Observation` (`t_ms`, `spatial_anchor`) | `domain/observation.py` |
| Binder | Spatio-temporal cross-channel binding | `domain/binding.py`, `application/binder.py` |
| First thought / raw material to marinate | Append-only observation log | `adapters/sqlite_eventlog.py` |
| Node Creation Black Box | SLEEP consolidation → EvidenceGraph projection | `application/binder.py` (Phase 2) |
| Living cell, 1+1=4 | Entity + confidence-weighted bindings composing into derived facts | `domain/{entity,binding}.py` |
| Encryption "our app can decipher" | AES-GCM text codec | `adapters/encrypted_text.py` |
| Discarder of meta | Disposable projections; immutable log kept | I3, §7.2 |
| Information Supplier Black Box | Recall retrieval + grounding gate | `application/{recall,grounding_gate}.py` |
| Just Enough Context | Evidence-dossier assembly for the reasoner | `ports/recall_backend.py`, legacy `scripts/ask_home.py` |
| LLM does what LLM does | Swappable `TextReasoner` (local first, guarded egress) | `ports/text_reasoner.py`, `adapters/{ollama,cloud_text}.py` |

## 16. References

[1] E. Tulving, "Episodic and Semantic Memory," in *Organization of Memory*,
Academic Press, 1972; and E. Tulving, *Elements of Episodic Memory*, Oxford
University Press, 1983.

[2] F. C. Bartlett, *Remembering: A Study in Experimental and Social
Psychology*, Cambridge University Press, 1932. (Memory as reconstruction, not
playback.)

[3] J. G. Klinzing, N. Niethard, J. Born, "Mechanisms of systems memory
consolidation during sleep," *Nature Neuroscience* 22, 1598–1610, 2019.
https://doi.org/10.1038/s41593-019-0467-3

[4] J. M. Zacks et al., "Event perception: a mind-brain perspective,"
*Psychological Bulletin* 133(2), 2007. (Event Segmentation Theory.)

[5] A. Cavoukian, *Privacy by Design: The 7 Foundational Principles*,
Information & Privacy Commissioner of Ontario, 2009.
https://iapp.org/resources/article/privacy-by-design-the-7-foundational-principles/

[6] Regulation (EU) 2016/679 (GDPR), Article 5(1)(c) — data minimisation.
https://gdpr-info.eu/art-5-gdpr/

[7] T. Brown et al., "Language Models are Few-Shot Learners," *NeurIPS*, 2020.
https://arxiv.org/abs/2005.14165

[8] L. Itti, C. Koch, "Computational modelling of visual attention," *Nature
Reviews Neuroscience* 2, 194–203, 2001.

[9] J. Gemmell, G. Bell, R. Lueder, "MyLifeBits: a personal database for
everything," *Communications of the ACM* 49(1), 2006.
https://doi.org/10.1145/1107458.1107460

[10] S. Hodges et al., "SenseCam: A Retrospective Memory Aid," *UbiComp*,
2006. https://doi.org/10.1007/11853565_11

[11] K. Grauman et al., "Ego4D: Around the World in 3,000 Hours of Egocentric
Video," *CVPR*, 2022. https://arxiv.org/abs/2110.07058

[12] P. Lewis et al., "Retrieval-Augmented Generation for Knowledge-Intensive
NLP Tasks," *NeurIPS*, 2020. https://arxiv.org/abs/2005.11401

[13] A. Kamath, R. Jia, P. Liang, "Selective Question Answering under Domain
Shift," *ACL*, 2020. https://arxiv.org/abs/2006.09462 (Answer-or-abstain as a
first-class objective.)

[14] A. Hogan et al., "Knowledge Graphs," *ACM Computing Surveys* 54(4), 2021.
https://arxiv.org/abs/2003.02320

[15] Apple, *ARKit — ARWorldMap and world tracking* (6-DOF pose,
relocalization). https://developer.apple.com/documentation/arkit

[16] D. L. Hall, J. Llinas, "An introduction to multisensor data fusion,"
*Proceedings of the IEEE* 85(1), 1997.

[17] Gemma Team, Google DeepMind, "Gemma 3 Technical Report," 2025.
https://arxiv.org/abs/2503.19786

[18] Qwen Team, Alibaba, "Qwen2.5-VL Technical Report," 2025.
https://arxiv.org/abs/2502.13923

[19] E. Evans, *Domain-Driven Design: Tackling Complexity in the Heart of
Software*, Addison-Wesley, 2003. (Value objects; enforcing invariants at
construction.)

[20] C. Guo, G. Pleiss, Y. Sun, K. Q. Weinberger, "On Calibration of Modern
Neural Networks," *ICML*, 2017. https://arxiv.org/abs/1706.04599

[21] A. Cockburn, "Hexagonal Architecture (Ports and Adapters)," 2005.
https://alistair.cockburn.us/hexagonal-architecture/

[22] R. C. Martin, *Clean Architecture*, Prentice Hall, 2017.

[23] M. Fowler, "Event Sourcing," martinfowler.com, 2005.
https://martinfowler.com/eaaDev/EventSourcing.html

[24] M. Fowler, "CQRS," martinfowler.com, 2011.
https://martinfowler.com/bliki/CQRS.html

[25] M. Fowler, "Strangler Fig Application," martinfowler.com, 2004/2024.
https://martinfowler.com/bliki/StranglerFigApplication.html

[26] Ultralytics YOLO documentation. https://docs.ultralytics.com/ (Lineage:
J. Redmon et al., "You Only Look Once," *CVPR*, 2016,
https://arxiv.org/abs/1506.02640)

[27] P. K. A. Vasu et al., "MobileCLIP: Fast Image-Text Models through
Multi-Modal Reinforced Training," *CVPR*, 2024.
https://arxiv.org/abs/2311.17049 (Apple; ANE-optimized zero-shot naming.)

[28] A. S. Tanenbaum, D. J. Wetherall, *Computer Networks*, 5th ed., Pearson,
2011, §5.4 — token-bucket traffic shaping.

[29] Ollama — local model runtime. https://ollama.com/

[30] A. Radford et al., "Robust Speech Recognition via Large-Scale Weak
Supervision (Whisper)," *ICML*, 2023. https://arxiv.org/abs/2212.04356

[31] B. Bohnet et al., "Attributed Question Answering: Evaluation and Modeling
for Attributed Large Language Models," 2022. https://arxiv.org/abs/2212.08037

[32] Z. Ji et al., "Survey of Hallucination in Natural Language Generation,"
*ACM Computing Surveys* 55(12), 2023. https://arxiv.org/abs/2202.03629

[33] M. Dworkin, *NIST SP 800-38D: Recommendation for Block Cipher Modes of
Operation — Galois/Counter Mode (GCM) and GMAC*, NIST, 2007.
https://doi.org/10.6028/NIST.SP.800-38D

[34] R. Hoyle et al., "Privacy behaviors of lifeloggers using wearable
cameras," *UbiComp*, 2014. https://doi.org/10.1145/2632048.2632079

### Internal primary sources

- `ops/NORTH_STAR.md` — product source of truth: the three-stage machine, the
  core attention principle, metrics, prototype tiers.
- `ops/ROADMAP.md` — canonical implementation spec: central hypothesis, (A)/(B)
  instrument, sufficiency→necessity→efficiency method, phase gates, governance.
- `ops/MARKET_AND_SCOPE.md` — market quadrant and moat argument.
- `ops/enrichment_scheduler_design.md` — salience scheduler design note.
- `docs/PHASE0_REPORT.md` — verified Phase 0 state, gate output, known debt.
- `README.md` — orientation and current privacy status.
