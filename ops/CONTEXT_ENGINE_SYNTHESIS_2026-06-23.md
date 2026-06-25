# Context Engine — Phase 1 SYNTHESIS (cross-lens, 2026-06-23 PM)

*Inline synthesis of the 195-parameter raw matrix (14 lenses) — no agents, by the Chief.*
*Source: `ops/CONTEXT_ENGINE_MATRIX_RAW_2026-06-23.md`. Repo reality + worked example: `ops/CONTEXT_ENGINE_GROUNDING_2026-06-23.md`.*
*Directive: build the `HELPERS → INJECTION → LLM` continuous context engine (injection FUSES + live WEB-EXPANDS; LLM STANDS ITS GROUND). Product = broad CONTEXT, not OCR.*

The 14 blind lenses converge. 195 parameters collapse to **14 cross-cutting clusters**, **8 core paradoxes**,
and one repeated structural fact: **the substrate is a flat ranked string, and almost every claimed capability
of the thesis is impossible to build on a string.** Fix the substrate and ~60% of the matrix dissolves.

---

## THE ONE-LINE DIAGNOSIS
Today: `helpers → build_evidence_dossier (ranked text lines) → LLM`, with the one validated honesty primitive
(frequency-consensus) wired as a **side path** on a minority of queries, and the three thesis-defining layers
(typed fusion, live expansion, stand-your-ground) **either absent or wired backwards** (entity resolution exists
but only as a refusal veto; refutation_cue is defined but never populated). The Mac is the whole engine; the phone
is a dumb sensor. The honesty numbers are real but measured on n=15.

---

## THE 14 CLUSTERS (clustered matrix)

Each cluster: the tension · the member parameters · the resolution direction (detailed in the blueprint).

### CL-1 — Substrate: typed Observation/Entity event-log vs. flat ranked string  ★ROOT
- **Members:** injection-1, grounding-11, state-1, state-5, state-7, state-13, injection-5, injection-10
- **Tension:** Every downstream capability (expansion, premise-check, confidence fusion, citation) needs a fact to
  attach to. Today there is no fact — only `build_evidence_dossier` lines (`ask_home.py:1510,:1586`). The typed
  `Observation`/`Entity`/`Attribute` model **already exists** (`src/trace_memory/domain/observation.py`) but the
  live assembler never produces it; the hexagonal core is ~90% stubs.
- **Resolution:** Make a typed, append-only `Observation` event log the **single source of truth**; the assembler
  emits a structured evidence *packet* (entities + per-fact merged confidence + full provenance), not a string.
  This is the architectural fork that gates the other 13 clusters.

### CL-2 — Consensus as the spine + a real confidence algebra
- **Members:** injection-2, grounding-5, injection-6, grounding-1, state-10, injection-7, grounding-10, state-4,
  injection-13, state-14, retrieval-9, retrieval-10, failure-1, failure-10
- **Tension:** `consensus_read` (the validated 47%→60% / halluc 42%→~9-18% win, `consensus_recall.py:108`) fires
  **only** on the anchored read path (`ask_home.py:2750`). Everywhere else the dossier *ranks*, never *votes*. And
  even where it votes, the math is naive: substring-fold over-merges distinct facts (`188`→`1881-1945`), dwell
  multiplicity is counted as independent corroboration (a still camera reading one sign 30× == 30 votes), quorum
  (`minrep=3`, `±5s`) is a frame-count constant decoupled from the thermally-variable capture rate, and the four
  helper confidence currencies (Vision per-word, detector `seen_count`, vote tally, `presence_confidence`) are
  incommensurable.
- **Resolution:** Promote consensus to the assembler's **default** fusion mechanic across all channels; replace
  frame-count quorum with **confidence-weighted, viewpoint-de-correlated** voting (Apple Vision per-word
  confidence as the calibration anchor); make merge **type-aware + box-aligned** (don't fold across numeric
  boundaries); fuse heterogeneous confidences into **one calibrated fact-level posterior**.

### CL-3 — Live expansion (the centerpiece): local-first, two-zone, corroborated, privacy-budgeted
- **Members:** injection-3, injection-8, state-9, grounding-6, injection-9, privacy-1, privacy-2, privacy-7,
  privacy-8, privacy-14, retrieval-11, injection-15, failure-5, topology-5
- **Tension:** The single most novel claimed layer **does not exist** (grep-confirmed zero network I/O). When
  built naively it (a) detonates the on-device privacy promise — every enrichment leaks "what the user is reading
  / where they are" to a third party — and (b) launders web guesses into "observed" facts, breaking the honesty
  moat, and (c) is a hallucination-injection vector (untrusted web text into the grounded packet).
- **Resolution:** **Local Wikidata/geo snapshot first** (zero network for institutions/landmarks/brands), Brave
  **only** for genuine misses, user-visible + rate-limited + PII-redacted. A **two-zone evidence packet**
  (`OBSERVED` the LLM may assert as seen vs. `WORLD-KNOWLEDGE` it may only assert as inference). **Corroborate the
  expansion against the device's own helpers** (OCR "MPI" + CoreLocation reverse-geocode → which Max-Planck?)
  before asserting — frequency=confidence applied to the enrichment itself.

### CL-4 — Stand-your-ground: premise-check + refutation_cue + absence facts
- **Members:** injection-4, injection-12, grounding-4, grounding-7, state-2, state-12, entity-11, failure-11, eval-7
- **Tension:** The thesis' defining LLM behavior (contradict a false premise, don't silently refuse) has **no code
  path**. `refutation_cue` (`observation.py:30`) is the exact slot for it — **defined, never produced or consumed**
  (the single most-repeated gap, flagged by 4 lenses). The engine only answer-or-refuses; absence ("I looked and
  it was *not* there") is unrepresentable, so there is nothing to stand on. Prompt-asserted contradiction is
  already declared dead (`ask_home.py:2273`).
- **Resolution:** A **premise-verification stage** before phrasing: detect when the question presupposes an entity
  the packet's evidence refutes; **populate `refutation_cue`** from real signals (presence_confidence below floor;
  a consensus read that contradicts the premise; OCR "MURAL/POSTER" where the question assumes a real object);
  store honest helper refusals as typed **`Observation(kind='absence')`**. Structural, not prompt.

### CL-5 — Thermal envelope: the master constraint that shapes the whole architecture
- **Members:** thermal-1 … thermal-13, injection-11, acq-9, latency-9, retrieval-3, attention-5, state-6, state-13, eval-6
- **Tension:** Continuous capture throttles to **~4-5W sustained in ~1 min** (A18 Pro); on-device VLM is **sub-5
  tok/s**. Injection competes with capture for the same ANE/watts — `consensus_read` issues up to 20 LLM calls per
  query. Always-on full-frame VLM is **thermally impossible**. The architecture "looks fine on a plugged-in Mac
  and dies on a phone in a pocket after 60 seconds."
- **Resolution:** This is not a bug to fix; it is the **physics that dictates the design**: heavy VLM = duty-cycled
  async **brain**; live path = **ANE-cheap deterministic helpers + deterministic (non-LLM) fusion**; LLM phrasing +
  expansion happen in the async brain, off the live critical path. (Validates the existing live-bounded /
  brain-unbounded split as a *thermal necessity*, not a choice.)

### CL-6 — Salience as the compute allocator
- **Members:** attention-1 … attention-14, helpers-5, latency-11, eval-5
- **Tension:** Live sampling is **fixed-clock, salience-blind** (every 4s sim / dwell-gated native). The thermal
  token-bucket *is* the real attention budget but its calibration is unvalidated; salience has **no
  text-density/read-value term** (the product's core target is not a first-class salience input), no speech/deictic
  reference, no hand-interaction lift, no barge-in/interrupt path, and there are **two divergent salience
  implementations** (Swift + Python) that must stay in sync.
- **Resolution:** Make salience the explicit allocator of the thermal budget, with **read-value (text density,
  legibility, novelty-per-content) as a first-class term**, priority lanes (honest-refusal-critical vs ambient),
  a barge-in path, and **one** shared salience definition.

### CL-7 — Helper society: typed specialists vs. one monolithic VLM
- **Members:** helpers-1 … helpers-14, acq-8, acq-11, entity-3
- **Tension:** The "society of specialists" is largely **one VLM masquerading as many** (helpers-1); there are
  taxonomy holes (missing modalities, no behavioral/wearer-state channel, no cross-modal voice→face→name binding,
  no re-identification channel), schema drift / unparseable emissions, and **no meta-helper for "is this frame
  worth perceiving."** Helper confidences are non-comparable (→ CL-2). Single mic = no spatial audio selectivity.
- **Resolution:** Real typed specialists emitting into the CL-1 substrate; a cheap **capture-quality meta-helper**
  (gate before the expensive VLM pass); a re-identification/track channel; explicit confidence currency per helper.

### CL-8 — Latency: two SLOs + closed-loop backpressure
- **Members:** latency-1 … latency-14, eval-10, eval-13
- **Tension:** **Two distinct SLOs are conflated** — *time-to-context* (ambient liveness) vs *time-to-answer*
  (query response). Capture is **open-loop** (fixed cadence, no backpressure beyond queue-age eviction);
  expansion latency sits on the **synchronous answer path** and is externally variable; the double-pass grounding
  gate doubles answer latency; jitter (not mean) governs perceived liveness; there's no admission control. The
  answer-path end-to-end latency is **unmeasured** (only OCR live-latency is proven).
- **Resolution:** Separate the two SLOs explicitly; move expansion off the synchronous path (async brain, CL-5);
  closed-loop backpressure with priority lanes; admission control with an end-to-end deadline.

### CL-9 — Temporal validity: per-fact decay + never-delete hot/cold
- **Members:** state-3, state-8, grounding-12, injection-14, state-6, retrieval-7, failure-8
- **Tension:** Validity is **two global constants** (90s active / 1800s stale) applied uniformly — a building
  plaque (valid for years) decays like a passing pedestrian (valid for seconds). Recency eviction **deletes**
  facts, contradicting the founder's "never delete, decay = retrieval cost" decision; the most important
  single-sighting facts are evicted first. Truth-claims are asserted present-tense with **no recency discount**
  ("the board says gate 12" read 40 min ago). Time is quantized to 15s buckets at write.
- **Resolution:** **Per-fact-type validity windows** (read-text durable, clocks/screens/occupancy volatile);
  **hot/cold tiering** (sqlite-vec cold store, nothing deleted, retrieval cost rises with coldness); demote stale
  volatile facts from "assertable" to "last seen at T" instead of refusing or over-asserting.

### CL-10 — Topology: the split is a lie; make a durable, secured, reconcilable shared store
- **Members:** topology-1 … topology-14, state-11, privacy-3, privacy-6, privacy-13, latency-13
- **Tension:** Today the phone is a dumb sensor and the **Mac is the whole engine**; brain memory is volatile +
  newest-bounded (no durable cross-device store); two divergent representations (native digest vs brain JSON) with
  **no reconciliation contract**; spool replay has **no idempotency key** (re-replay double-ingests) and must stop
  the daemons (unserialized SQLite writers); the LAN channel is **plaintext HTTP with a hardcoded `dev-token`**;
  hub address is hand-typed; offline degradation is binary spool-and-pray.
- **Resolution:** A **durable shared event log** (CL-1) as the single source of truth both paths project from;
  idempotent ingest; a **secured** device↔brain channel (not plaintext, not `dev-token`); graceful local-answer
  degradation when the brain is offline.

### CL-11 — The honesty gate: calibrated, symmetric, channel-attributed
- **Members:** grounding-2, grounding-3, grounding-8, grounding-9, grounding-13, grounding-15, failure-6,
  failure-12, failure-13, failure-14
- **Tension:** `ASSEMBLER_COMMIT=1` biases the LLM to answer, leaving **one** structural net between it and a
  hallucination (G4 disabled, prompt restraint removed). The gate only ever **DEMOTES** — it has **no instrument
  for over-refusal** (false negatives are invisible by construction → the honesty moat becomes a uselessness
  moat). Refusals are **canned strings** that don't name the missing channel (no recovery action for the user).
  G2 verbatim-grounding is substring-matching (value-present-but-misattributed passes). An honest OCR refusal can
  be **silently overridden** by a guessing VLM caption. The gate **fails OPEN on every error**.
- **Resolution:** Replace per-rule floors with a **single calibrated fact-posterior threshold** (CL-2); make every
  refusal carry **channel attribution + recovery cue**; instrument **over-refusal** as a first-class metric;
  surface cross-helper **contradiction as uncertainty**; enforce **authoritative-channel veto** (an honest refusal
  in the authoritative channel vetoes guesses from redundant channels for that fact-type).

### CL-12 — Retrieval/indexing at continuous scale
- **Members:** retrieval-1 … retrieval-13, state-13
- **Tension:** Self-corpus IDF is unstable on a continuously-growing memory; full-rebuild cache invalidation (no
  incremental index); embedding-unit mismatch (what's embedded ≠ what's asked); cross-lingual query→evidence
  bridge is single-model-fragile (yet it's the core value: read German, ask English); no query-intent routing
  across heterogeneous indexes; no recency weighting in ranking; embedding-model drift silently breaks the cache.
- **Resolution:** Incremental indexed store (sqlite-vec) replacing whole-file JSON; stable IDF / append-aware
  indexing; intent routing; recency-aware ranking; a versioned embedding model so drift invalidates explicitly.

### CL-13 — Evaluation honesty: measure the real brain, on a trustworthy n
- **Members:** eval-1 … eval-14, grounding-14, failure-15
- **Tension:** The eval scores a **standalone consensus stub, not the shipped `ask_home.ask`** (eval-4); gold is
  built by the same model class being evaluated (auto-gold circularity); **n=15, not held out** (±13% CI — not
  defensible to a physicist founder who will ask for error bars); RAS double-counts hallucination as
  (correct−wrong), inflating the headline; **no metric** for binding/attribution accuracy, yield-per-watt,
  over-refusal, unprompted-speech, completeness (truncated reads scored as full), or the **context-first** demo
  claim (the pitch's core claim is currently unfalsifiable as built).
- **Resolution:** Wire the real `ask_home.ask` and score **that**; held-out **n≥100** with **frozen human gold**;
  report 95% CIs; add binding-accuracy, over-refusal, completeness, and a context-first metric.

### CL-14 — Acquisition fidelity at the source
- **Members:** acq-1 … acq-12, helpers-13, thermal-10
- **Tension:** **Sharpness/blur is never measured** — only inter-frame change is (so the system can't tell a sharp
  frame from a blurry one); rolling-shutter + walking-pace skew corrupts verbatim text geometry; exposure/auto-gain
  is uncontrolled (bright signs blow out); fixed wide FOV caps legible-text distance; cadence may miss transient
  text; **no clock-skew model across helper streams** (fusion binds the wrong moment); stale config (VGA assumed,
  HD1080 captured); OCR language set hardcoded; no low-light refusal (dark-frame guessing).
- **Resolution:** A capture-quality meta-helper (CL-7) that measures sharpness/legibility and **refuses dark/blurry
  frames** rather than guessing; a unified clock/timestamp model for fusion (also CL-10); pay to **select** sharp
  frames rather than process-then-discard.

---

## THE 8 CORE PARADOXES (and the resolution thesis for each)

| # | Paradox | Resolution thesis |
|---|---------|-------------------|
| P1 | **Always-on perception vs. ~4-5W thermal/battery wall** | Duty-cycled heavy VLM in an async brain; ANE-cheap deterministic fusion on the live path. The split is a *thermal necessity*, not a preference. (CL-5) |
| P2 | **Perfect-recall memory vs. on-device privacy / breach blast-radius** | Never-delete **hot/cold** tiers, fully on-device, encryption-at-rest with real key management. Decay = retrieval cost, not deletion. (CL-9, P-priv) |
| P3 | **Live web/knowledge expansion vs. egress** (the centerpiece's own paradox) | **Local snapshot first** (zero network for the common case); Brave only for misses, redacted + rate-limited + user-visible. Measure leak as *bits of user context per enrichment*. (CL-3) |
| P4 | **Flexible open-vocab helpers vs. typed answer/grounding logic** | Open helpers emit **into** a typed `Observation` substrate; a **calibrated confidence algebra** bridges the two so heterogeneous emissions become one comparable fact. (CL-1, CL-2) |
| P5 | **Freshness (present-tense truth) vs. durability (perfect recall)** | Keep the fact forever; **decay the truth-claim**. Per-fact-type validity windows demote stale volatile facts to "last seen at T" without deleting them. (CL-9) |
| P6 | **Helpful inference (expansion, stand-your-ground) vs. hallucination** | **Corroborate-before-assert** + **two-zone provenance** + **refutation_cue-grounded** contradiction. Inference is allowed only when a second independent source agrees or the packet's own evidence backs it. (CL-3, CL-4) |
| P7 | **Honesty moat (refuse when unsure) vs. uselessness moat (over-refusal)** | A **symmetric error instrument** (measure over-refusal as rigorously as hallucination) + a **single calibrated posterior threshold** + channel-attributed refusals that give the user a recovery action. (CL-11, CL-13) |
| P8 | **Frequency = confidence vs. correlated redundancy** (dwell, persistent mis-read) | Count **independent** corroboration, not raw frames: de-weight by viewpoint/sharpness similarity; a high-confidence single read can outvote many low-confidence repeats. (CL-2) |

---

## BLIND-SPOTS — the "things-not-conceived" worth surfacing (highest signal)

- **`refutation_cue` defined but never produced** — flagged independently by **4 lenses** (state-2, grounding-7,
  injection-12, entity-11). The single most-repeated structural gap; the substrate for stand-your-ground exists and
  is inert.
- **No sharpness/blur measure at capture** (acq-1) — the system literally cannot tell a sharp frame from a blurry
  one; it gates on inter-frame *change*, not legibility.
- **No clock-skew / unified timestamp model** across helper streams and across device↔brain (acq-12, latency-8,
  topology-4) — fusion can bind attributes to the wrong moment.
- **No negative/absence facts** (state-12) — "I looked and it was not there" is unrepresentable, so absence-premise
  contradiction is structurally impossible.
- **No over-refusal instrument** (grounding-9) — every refusal is scored "safe"; a 40%-refusing product is
  invisible to the gate.
- **No binding/attribution accuracy metric** (eval-8) — "right fact, wrong entity" is not in any score, yet it is
  the documented capture-binding failure class.
- **No yield-per-watt / helper-ROI metric** (eval-6) — which perceivers earn their thermal cost is unmeasured.
- **Security blind spots:** hardcoded `dev-token` auth (topology-14) + plaintext LAN HTTP (privacy-3) → the
  cross-device channel is effectively open on the LAN; spool replay has no idempotency key (topology-3).
- **No barge-in / interrupt path** (attention-12) — perception cannot be preempted by a live event.
- **n catastrophically small + not held out** (grounding-14, eval-3, failure-15) — every threshold is potentially
  noise-fit on 15 questions; this is the meta-failure gating "pitch-ready."

---

## BUILD ORDER (what unlocks what — detailed in the blueprint)

1. **CL-1 substrate first.** It is the root; ~60% of the matrix is "impossible on a string." Everything else
   attaches to the typed `Observation` packet + event log.
2. **CL-2 consensus-as-spine + confidence algebra** — promote the one validated win to the default; it is the
   honesty engine the gate (CL-11) thresholds on.
3. **CL-4 stand-your-ground** — cheap once the substrate carries `refutation_cue` + absence facts; it is the
   demo-defining behavior.
4. **CL-3 expansion** — the centerpiece, but it depends on CL-1 (something to attach enrichment to) and the
   two-zone/privacy machinery; build local-snapshot-first.
5. **CL-5/CL-9/CL-10 physics + durability** — thermal duty-cycle, per-fact decay, durable shared store: the
   substrate that lets it survive on a real phone over a real session.
6. **CL-11/CL-13 honesty gate + real eval** — calibrate and *measure on a trustworthy n*; this is the pitch gate.
7. **CL-6/CL-7/CL-8/CL-12/CL-14** — capture/salience/helpers/latency/retrieval quality: the long tail that makes
   it good rather than merely correct.

→ **Next:** `ops/CONTEXT_ENGINE_BLUEPRINT_2026-06-23.md` turns this into a buildable-today architecture, then
re-anchors the sprint board WS0–WS7.
