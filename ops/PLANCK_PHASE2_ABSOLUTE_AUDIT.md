# Planck Audit - Phase 2: Absolute Audit and Resurrection Strategy

Date: 2026-06-22

Evidence labels:

- **Verified**: reproduced from current code, artifacts, device state, tests, or build.
- **Inference**: the strongest conclusion supported by verified evidence, but not yet a measured fact.
- **Unknown**: the project has no credible evidence. Unknown is not a soft pass.

Question identifiers map one-for-one to `PLANCK_PHASE1_QUESTIONS.md`.

## Primary External Verification

The legal conclusions are risk flags, not legal advice. Current primary sources checked:

- [European Commission: what counts as personal data and processing](https://commission.europa.eu/law/law-topic/data-protection/reform/what-personal-data_en)
  confirms that identifiable/linkable derived data remains personal data and lists
  collection, recording, storage, retrieval, and transmission as processing.
- [European Commission: AI Act risk framework](https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai)
  confirms the risk-based regime and specific biometric/workplace restrictions.
- [German Criminal Code section 201](https://www.gesetze-im-internet.de/stgb/BJNR001270871.html)
  covers unauthorized recording of another person's nonpublic speech.
- [German Federal Data Protection Commissioner: video surveillance](https://www.bfdi.bund.de/DE/Buerger/Inhalte/Allgemein/Datenschutz/Videoueberwachung.html)
  describes video capture as an intrusion requiring a defined lawful purpose and GDPR/BDSG analysis.
- [Apple App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/)
  require explicit recording consent/indication, accurate permission purposes, privacy
  policy, minimization, consent withdrawal, and retention/deletion disclosure.
- [Apple local-network privacy key](https://developer.apple.com/documentation/BundleResources/Information-Property-List/NSLocalNetworkUsageDescription)
  says apps using direct local-host connections should provide a local-network purpose string.
- [Amazon Bee](https://www.aboutamazon.com/news/devices/bee-amazon-wearable-ai-device-new-features/)
  is an audio-memory product. Amazon says it captures conversations, retains transcripts
  and summaries but no audio, and builds longitudinal insights. It does not perform vision.
- [Ray-Ban Meta Gen 2](https://about.fb.com/news/2025/09/ray-ban-meta-gen-2-better-battery-life-video-capture/)
  is a camera, media-capture, and momentary AI-assistance product. Meta explicitly markets
  3K video capture. Its on-device OCR/caption work is relevant technology, not evidence of
  an automatic text-only autobiographical memory.
- [Google Android XR glasses](https://blog.google/products/android/android-xr-glasses-demo-io-2025/)
  are a prototype that can see, hear, and "remember what's important." Google has not
  published evidence that this means continuous derived memory, immediate scene-media
  deletion, local persistence, or a shipping product.
- [Brilliant Labs Halo](https://brilliant.xyz/products/halo) is the closest thesis-level
  competitor: the official product promises vision and audio, long-term memory, and
  memory-enhancement dialogue. Its [privacy policy](https://brilliant.xyz/pages/privacy-policy)
  says raw audio/video is not retained beyond immediate processing, while its product page
  identifies Noa as a cloud-based AI agent and its own launch material says encoded memories
  are stored on encrypted servers. That is a direct concept competitor but a different
  persistence boundary from Trace's local-first claim.
- [Ultralytics licensing](https://github.com/ultralytics/ultralytics) documents AGPL-3.0
  and enterprise options; [Apple MobileCLIP](https://github.com/apple/ml-mobileclip)
  carries separate code, data, and model license files absent from this repository.

## Correction: Define the Cell Before Calling It Empty

The earlier audit's market sentence was wrong. It treated every wearable with a camera,
microphone, AI, or memory language as a direct competitor. That is category sloppiness.
Amazon Bee cannot answer what was visually present. Ray-Ban Meta is optimized to capture
and share media and to answer in-the-moment questions. Google's public glasses are a
prototype, not evidence of an implemented longitudinal memory. None of those facts rebuts
Trace's exact conjunction.

The opposite absolute claim - "there is no product in this realm" - is also too broad.
Halo explicitly claims the same core job: see and hear the wearer's day, discard rich media,
retain encoded memory, and converse over it later. The material difference is that Halo's
agent and persistent encoded memory use cloud infrastructure, while Trace's defensible
architecture would keep derived memory local and permit no unreviewed raw or derived-data
egress.

The competitive claim therefore has four different meanings:

| Claim | Current verdict | Evidence required |
|---|---|---|
| No adjacent products | False | Bee, Meta, Google, and audio notetakers compete for attention, hardware tolerance, and memory budget. |
| No product with visual autobiographical memory | False as a claim | Halo markets exactly this; marketing is not proof of quality. |
| No product with visual memory plus immediate raw deletion | Not established | Halo claims this too. Its raw-data lifecycle needs independent verification. |
| No proven local-first product with continuous vision, no retained raw media, durable derived memory, and open retrospective QA | Plausibly true, not proven | A reproducible competitor teardown and same-session benchmark. |

That last row is the only credible whitespace statement. It is narrower and stronger than
"empty market": **the exact trust architecture appears commercially unproven.** It is not
a moat until Trace itself proves it works. A cell containing no successful product can mean
untapped demand, or it can mean that physics, battery, law, social acceptance, and irreversible
information loss make the combination unattractive.

## Atomic Reality: Sensor to Answer

This is the bottom-up product. Every higher-level claim inherits the weakest row below.

| # | Atomic unit in current code | Immediate behavior | Outward consequence |
|---:|---|---|---|
| 1 | `CameraController` supplies CMSampleBuffers | The app receives raw pixels in memory. | "No raw storage" can be true; "no raw capture" cannot. |
| 2 | `ContentView` forwards every sample to `GroundTruthRecorder.ingest` | A cached user-default decides whether an H.264 writer starts. | The production binary contains a raw-video persistence path. |
| 3 | Recorder path uses the app Documents directory | `walk_gt_<epoch>.mov` survives process exit. | Raw absence is a runtime state, not an architectural invariant. |
| 4 | Header renders a literal `0 raw media` | The UI never inspects Documents or the writer. | The trust badge can report success while raw video exists. |
| 5 | Vision/OCR/classification sample selected frames | Unselected frames are never represented. | Future questions about skipped moments are unrecoverable. |
| 6 | `localVisionRecord` maps detections into strings | Boxes, pixels, alternatives, and much confidence detail collapse into prose. | The memory is a lossy hypothesis, not a neutral compression. |
| 7 | Semantic refresh invokes FastVLM | A generative model chooses what is salient before future questions are known. | Caption omissions become permanent epistemic loss. |
| 8 | Native log and spool write JSON/NDJSON | Speech, locations, people, and observations persist as plaintext. | No-raw does not equal low-sensitivity or encrypted. |
| 9 | Phone payload includes timestamp, pose, battery, build, phase, and labels | The device has useful provenance at emission. | The capture side is richer than the retained memory. |
| 10 | Default hub URL is `127.0.0.1:8765` | On a physical phone this addresses the phone, not the Mac. | A default-configured device spools instead of completing the live product loop. |
| 11 | Phone sends `X-TRACE-Token: dev-token` | The server never checks it. | The visible token is security theater. |
| 12 | Server binds `0.0.0.0` with wildcard CORS | Any reachable LAN/browser client can call ingest, timeline, proof, and ask. | Private memory can be injected, read, or model-queried without identity. |
| 13 | `_capture` replaces the device timestamp with `time.time() - t0` | Original clock, pose, battery, build, labels, and most metadata are dropped. | Citation time is server-arrival time and replay changes history. |
| 14 | `_LIVE` is a bounded process dictionary | Restart loses the live timing base; record 601 evicts record 1. | "Memory" is partly volatile and silently truncated. |
| 15 | Each ingest rewrites `kf_memory.json` | A projection file is treated as the current source of truth. | No immutable event identity, atomic replay contract, or lineage exists. |
| 16 | `/proof` scans only the Mac moment directory | It never audits the phone container where the recorder writes. | `moat_intact` can be true while the actual capture device holds raw media. |
| 17 | `ask_home.ask` reads the generated projection | Retrieval operates on prior model summaries, not observations with claim-level proof. | Citations show relevant scenes, not necessarily evidence for each clause. |
| 18 | iOS calls Ask with `allowFrontier: true` | A local refusal can send the question and memory dossier to Anthropic/OpenAI. | "Data does not go to cloud" is false for the current executable when keys exist. |
| 19 | Frontier success replaces the refused local answer | Frontier output bypasses the local structural grounding gate. | The path most likely to sound capable has the weakest enforced evidence contract. |
| 20 | `src/trace_memory` contains 579 lines, including eleven one-line placeholder modules | The clean architecture owns little live behavior. | Green checks describe the shell, not the 2,500-line Swift view or 2,800-line answer script. |
| 21 | Default test discovery now targets all `tests` | 222 tests run after the Trace migration. | Test visibility is repaired, but native/security/privacy assertions remain absent. |
| 22 | The iOS simulator build succeeds as `de.zer00.trace` | The renamed binary is buildable and displays Trace. | Buildability is established; device privacy and end-to-end usefulness are not. |

The macro product fails if any indispensable row fails. Today rows 2-4 invalidate the raw-
deletion claim, rows 10-16 invalidate the durable trustworthy-memory claim, row 18 invalidates
the absolute no-cloud claim, and rows 5-7 remain the unresolved scientific bottleneck.

## Intended Product vs Executing Product

| Intended Trace property | Current executing property | Delta |
|---|---|---|
| Continuous wearable perception | Foreground iOS view with no declared background capture mode | Not all-day or autonomous. |
| Vision plus audio resolves who spoke | Vision records people; speech emits one unbound `nearby speech` transcript | No active-speaker detection, AV synchronization, voice/face binding, or diarization benchmark. |
| Raw media is immediately destroyed | Raw video writer is compiled and has created MOV files on the device | Direct contradiction. |
| Only derived memory persists | Plaintext observations, transcripts, GPS/address context, spools, logs, and mutable JSON persist | Derived data is still highly sensitive and unmanaged. |
| Data stays local | Vision is local; derived text goes phone-to-Mac; refusal can go to frontier APIs | Local-first is conditional, not enforced. |
| Memory is durable | Phone spools; Mac live state is volatile and bounded; JSON is rewritten | No single durable event history. |
| The user can ask about their life | Ask works against the current projection when the Mac stack is configured | Interaction exists, but setup and evidence quality are prototype-grade. |
| The system knows when it does not know | Local heuristics can refuse | Frontier fallback can replace refusal without the same structural gate. |
| Citations make answers auditable | Citations point to retrieved timestamps/scenes | They do not prove each generated claim or reconstruct deleted evidence. |
| The UI proves privacy | UI prints a constant count | Proof is disconnected from the device-wide storage boundary. |
| The clean architecture is production | `src/trace_memory` is mostly interfaces/placeholders | Live behavior remains in monoliths and compatibility code. |
| Progress is 75% or live RAS is 85.7% | No durable row-level artifact supports those figures | Perceived progress is narrative, not reproducible evidence. |

The founder's conceptual point about multimodality is valid: vision can make audio memory
materially more useful by locating the speaker, objects, gestures, and setting. The current
implementation does not yet cash that advantage. It transcribes speech and perceives vision
in parallel, then stores them as separate text records. Parallel sensors are not multimodal
binding.

## A - Actual Product and Atomic Hypothesis

**A1 - Verified:** Today this is a research/demo stack, not one coherent product. The
only end-to-end runnable surface is an iPhone perception app plus a manually started Mac
brain; the relational `trace_hub` has been promoted back to the active import path because
tests and scripts depend on it, while the pitch surface remains a separate Mac simulation.

**A2 - Verdict:** The falsifiable hypothesis should be: "A phone can convert an unseen
60-minute first-person session into text online, retain no raw media, and later answer at
least 80% of a 50-question blind battery with zero unsupported claims, on a fixed energy
budget." The repository has not tested that hypothesis.

**A3 - Verdict:** Kill the broad text-only hypothesis if three clean, held-out sessions
with exhaustive oracle review still have OAG above 25% after the best affordable capture
pass. The current 42-44% incomplete, tuning-exposed OAG is already adverse evidence, not
a pass.

**A4 - Inference:** The potentially differentiated cell is narrower than the original
audit stated: continuous visual perception, immediate rich-media deletion, durable local
derived memory, and grounded open-ended retrospective recall. Halo claims the first,
second, and fourth and stores encoded memory on servers; Trace does not yet enforce all
four. Capture scheduling, text memory, local inference, and RAG separately are not unique.

**A5 - Verified:** The code optimizes for an angel demo because the roadmap explicitly
names the angel as the prototype audience and the worktree contains pitch UI, scripts,
cockpit percentages, and rehearsed answers before held-out product validity exists. That
is fundraising theater ahead of product proof.

**A6 - Verdict:** The supported product must initially exclude all-day wear, strangers,
cloud fallback, person identity, autonomous action, 3D/spatial claims, and "ask anything."
The defensible first product is a consented, bounded-session visual memory experiment.

## B - Beneficiary, Buyer, and Behavior

**B1 - Unknown:** No customer research identifies a user with sufficient pain to accept
continuous camera, microphone, location, setup, and error costs.

**B2 - Verified:** The present buyer is effectively the investor, while the founder is
the operator and test subject. There is no evidence that wearer, bystander, caregiver,
employer, and payer incentives have been separated.

**B3 - Inference:** Low-stakes retrospective search, reminders, and accessibility could
tolerate refusal. Safety, health, interpersonal, legal, access-control, and identity jobs
cannot tolerate the observed misattribution and confident-state errors.

**B4 - Inference:** Persistent text about names, speech, exact places, routines, and
relationships will produce surveillance behavior changes even without video. Removing
pixels reduces one risk; it does not make the memory socially neutral.

**B5 - Unknown:** There is no demand evidence showing users prefer continuous physical
memory over deliberate notes, photos, voice capture, reminders, or narrower assistive
tools.

**B6 - Unknown:** No pricing interviews, paid pilots, repeat-use cohort, retention curve,
or willingness-to-pay evidence exists.

## C - Capture Contract

**C1 - Verified:** The app attempts Vision OCR, Core ML object detection, image
classification, FastVLM refreshes, speech recognition, device pose, GPS/geocoding, scene
state, and context logs. Availability and cadence differ by platform and runtime state;
there is no single per-second completeness contract.

**C2 - Verified:** On iOS, `TraceDetectorBridge` reports its subprocess worker unavailable.
Separate `ObjectDetectorV2`, Vision OCR/classification, FastVLM, Speech, Core Motion, and
Core Location paths remain. The milestone "YOLO+OCR+classify+VLM ON" is not backed by a
device capability report proving all helpers produced useful records simultaneously.

**C3 - Verified:** The phone emits absolute timestamps, but `trace_brain_server._capture`
discards them and stamps server-relative arrival time. Recall therefore orders network
arrival, not physical observation, after the live boundary.

**C4 - Verified:** There is no packet ID, sequence, source event ID, checksum, replay
marker, or idempotency key in the brain path. Duplicate, delayed, replayed, and reordered
packets are indistinguishable from new observations.

**C5 - Verified:** `_LIVE` is process memory. A server restart loses its timing base and
rolling list. The last JSON projection may remain, but the next packet starts a new
in-memory session and can overwrite the file with a new one-record history.

**C6 - Verified:** `LIVE_MAX=600` deletes the oldest live records from the server
projection. This directly contradicts perfect recall unless a separate durable event log
is wired; it is not.

**C7 - Verdict:** Capture completeness must be measured against synchronized oracle media
with per-channel expected/observed events, drop counts, latency, and reason codes. Current
status strings and output counts cannot establish completeness.

**C8 - Verified:** The phone payload carries source and metadata, but the brain reduces it
to `caption`, empty `ocr`, a synthetic frame ID, source, and relative time. Pose, battery,
GPS, original timestamp, active entities, motion, and confidence are lost to recall.

## D - Data Model and Durability

**D1 - Verified:** The append-only SQLite adapter is used only by unit tests. No live
entry point constructs `SqliteEventLog`; the claimed source of truth is architectural
scaffolding.

**D2 - Verified:** Live packets have no immutable event identity. The only IDs are
list-index-derived `f_N` labels, which change meaning after restart or truncation.

**D3 - Verdict:** `kf_memory.json` currently acts as event store, projection, API payload,
retrieval corpus, checkpoint input, and demo evidence. That role collapse is a core design
defect because mutability in one concern corrupts every other concern.

**D4 - Verified:** The server lock protects list mutation, not file replacement. Two
threads can leave the lock with snapshots of different lengths and complete writes out of
order; writes are also non-atomic. A shorter or partial file is possible.

**D5 - Verified:** There is no live schema version, migration registry, or compatibility
test. Parsers accept multiple ad hoc shapes and silently drop fields they do not recognize.

**D6 - Verified:** Some offline artifacts have source-fingerprint checks, but the live
memory and semantic index system has no universal transaction, checksum, or crash-recovery
contract. JSON parse errors often degrade to empty data.

**D7 - Verdict:** Neither final JSON nor checkpoint NDJSON is universally authoritative.
Each script chooses differently. Authority must be the immutable event log; every JSON
artifact should become a versioned, reproducible projection.

**D8 - Unknown:** There is no credible full-day backup, restore, replay, compaction,
retention, or disaster-recovery procedure. Existing runbooks cover individual demos and
cable copying.

## E - Egress, Encryption, and Exposure

**E1 - Verified:** `EgressGuard` and `TextEgress` do not wrap the brain server's Anthropic
or OpenAI requests, native LAN posts, or other script HTTP calls. The privacy boundary is
tested in isolation and bypassed in production-like paths.

**E2 - Verified:** Device logs and spools contain plaintext derived observations with
precise location/address context. The new AES-GCM codec is not used by native or brain
storage.

**E3 - Verified:** Nothing authenticates phone traffic. The phone sends
`X-TRACE-Token: dev-token`; the brain never reads it.

**E4 - Verified:** The server listens on all interfaces, returns wildcard CORS, exposes
timeline/proof/ask/capture routes, and imposes no authorization. Any reachable LAN client
can use them.

**E5 - Verified:** A LAN client can inject memories, read a timeline, request model work,
and potentially trigger cloud fallback. There is no rate limit, body-size limit, origin
check, CSRF defense, or per-device identity.

**E6 - Verified:** `performAsk()` calls `BrainClient.ask(... allowFrontier: true)`. This is
automatic opt-in, not explicit per-query consent.

**E7 - Unknown:** There is no cloud-egress audit log, minimization policy, redaction stage,
deletion confirmation, data-processing agreement record, or consent receipt.

**E8 - Verdict:** The current key lifecycle is "read a plaintext env file or environment
variable." There is no rotation, revocation, device binding, access audit, secure enclave,
or proof that deleted memory is cryptographically unrecoverable.

## F - Fidelity and Information Loss

**F1 - Verdict:** `Lossless` is false. A short generated caption is a lossy semantic guess,
not a reversible encoding of pixels. The term should be removed from all claims until a
defined fact set and measured retention bound exist.

**F2 - Verified:** Exact appearance, small text, off-axis context, unmodeled attributes,
fine spatial relations, identity cues, events between samples, tone, non-speech sound,
and any detail omitted by the current prompt are unrecoverable after deletion.

**F3 - Unknown:** There is no held-out OCR benchmark stratified by blur, size, glare,
orientation, script, and movement. A few successful Japanese/storefront reads do not
estimate field reliability.

**F4 - Verified:** The Tokyo result inferred shopping intent from store presence. Current
grounding rules are being patched after the failure; the system does not reliably separate
observation from intent.

**F5 - Verified:** Confidence code gives repeated same-channel captions limited weight in
places, but correlated models and shared inputs are not formally modeled. Repetition can
still dominate retrieval and dossier selection.

**F6 - Verdict:** Loss occurs at sensor sampling, helper extraction, record normalization,
phone-to-server field deletion, bounded retrieval, dossier clipping, model synthesis, and
answer cleanup. No stage has a measured information budget.

**F7 - Verified:** Current OAG is the intended oracle comparison and reports gaps above
42%, but both datasets are tuning-exposed and incomplete. It demonstrates substantial
loss, not sufficiency.

## G - Grounding, Citations, and Confidence

**G1 - Verified:** Citations are derived from retrieved scenes, not claim-level proof.
Retrieval relevance and answer entailment are conflated.

**G2 - Verified:** `answer_assembler` returns the dossier's `cited` scenes after generation
and structural gating. It does not identify which scene supports each clause, so unrelated
retrieved records can appear as proof.

**G3 - Unknown:** No independent claim-by-claim entailment evaluator is enforced in the
live path.

**G4 - Verified:** Frontier answers bypass `structural_grounding`; existing local citations
remain empty or stale, and a non-refusal string is accepted as an answer.

**G5 - Verdict:** Confidence is a set of heuristic channel weights and corroboration rules,
not a calibrated probability, despite the domain class docstring.

**G6 - Unknown:** No held-out reliability diagram, expected calibration error, Brier score,
or threshold-cost curve exists.

**G7 - Verdict:** Contradictions are handled inconsistently across custom parsers and
prompts. There is no temporal fact model with validity intervals and explicit competing
hypotheses.

**G8 - Verified:** Refusal depends on regex classes, special-case corpora, entity heuristics,
prompt behavior, and model output markers. Paraphrase consistency is not proven and prior
prompt edits produced large regressions.

## H - Human Interface and Honest Proof

**H1 - Verified:** The app renders `Text(". 0 raw media")` unconditionally. It is not an
audit result.

**H2 - Verdict:** It should show `UNVERIFIED` by default and `BREACHED` if any raw file is
found across the entire app container. Given the inspected device state, the correct
current label is `BREACHED`.

**H3 - Verified:** The microphone purpose string says audio is recorded with capture
sessions for later processing. That conflicts with the in-app no-audio-retention claim and
the current purported architecture.

**H4 - Verified:** The current lean UI has pause and clear-memory code, but no trustworthy
inspection/correction workflow, bystander record, complete derivative deletion, portable
export, or dispute trail.

**H5 - Verified:** It does not. The inspected phone silently accumulated 147 spooled
packets and logged connection failures while the Mac brain was absent.

**H6 - Verdict:** `watching` currently means the view task is active, not that capture,
helpers, durable storage, server ingest, or recall are healthy. It is misleading.

**H7 - Verified:** Some status strings differ internally, but user-facing refusal and
error semantics are not a coherent taxonomy. Many failures become empty data, fallback,
or generic refusal.

**H8 - Verified, partly repaired 2026-06-22:** The app now displays Trace and uses bundle ID
`de.zer00.trace`; internal target, executable, model framework, permission language, and
upstream info remain partly FastVLM. Product identity is improved but not fully separated
from its model scaffold.

## I - Identity, Binding, and Attribution

**I1 - Verdict:** There is no robust stable identity. Current approaches use lexical,
temporal, appearance, and entity-centric heuristics. Without retained visual evidence or
a durable embedding contract, re-identification is probabilistic and difficult to audit.

**I2 - Verified:** Existing code tries self-entity routing, same-event relations,
entity-centric extraction, and cross-frame re-ID. Historical failures show attributes and
logos still cross entities.

**I3 - Verdict:** No. Once one caption has mixed several people and objects, downstream
code cannot recover ownership reliably. Entity-centric extraction must occur while pixels
are present, and even then needs measured uncertainty.

**I4 - Unknown:** There is no held-out false-merge/false-split benchmark on multi-person,
re-entry, wardrobe-change, and occlusion scenes.

**I5 - Verified:** Names can come from nearby OCR, ASR, and linking heuristics. There is no
consent-based identity enrollment or independent verification policy in the live app.

Vision could reduce the speaker-identification problem by binding a time-aligned transcript
to a visibly speaking face. Current code performs no lip/activity detection, AV clock
alignment, diarization, or voice/face binding; it emits a generic `nearby speech` event.
The superior multimodal behavior is therefore a sound product hypothesis and a missing
implementation, not a present advantage.

**I6 - Inference:** Persistent person profiles are personal data; voice patterns or
identity templates may become biometric data when used for unique identification. The
project has no classification or impact assessment.

**I7 - Verified:** Corrections are not first-class events. A manual artifact edit can leave
semantic indexes, bound memory, entity projections, score files, and answers inconsistent.

## J - Jobs, Journeys, and End-to-End Reality

**J1 - Verified:** No non-developer journey works end to end. The current path needs Xcode,
an installed app, manual LAN configuration, Ollama models, Terminal-launched brain, and
interpretation of failures.

**J2 - Verdict:** No current runbook is authoritative. Documents refer to deleted capture
files, a hub that was incorrectly labeled archived despite active imports, Mac simulation,
and multiple superseded architectures.

**J3 - Verified:** No. During audit the launch agent was absent, PID files were stale, only
Ollama was listening, and the brain/cockpit were down.

**J4 - Verified:** Packets spool locally. There is no automatic robust cross-network path;
old runbooks depend on cable copy and replay.

**J5 - Verdict:** Spooling is append-only text, but replay is not proven automatic,
idempotent, or provenance-preserving in the current brain architecture. Packet IDs are
absent.

**J6 - Verified:** Setup requires many hidden assumptions: local absolute paths, model
names, ports, Wi-Fi reachability, Xcode selection, permissions, venv contents, untracked
models, certificates, and manual processes.

**J7 - Verdict:** Recovery is improvised. Some loops restart helpers and some packets spool,
but there is no transactional recovery state machine or user-safe failure protocol.

## K - Kill Criteria and Strategic Honesty

**K1 - Verdict:** Use hard gates: OAG <=25%, unsupported-claim rate 0/150 questions,
wrong-entity rate 0/50 identity questions, capture-to-store p95 <=5 s, ask p95 <=15 s,
8-hour battery drain <=60%, and setup <=10 minutes from a clean supported machine. Miss
two consecutive gates after one focused remediation cycle and narrow or kill the thesis.

**K2 - Verdict:** Three independently captured held-out sessions are the minimum to reject
the current broad hypothesis; five are preferable. One outdoor walk and one contaminated
montage cannot establish generality.

**K3 - Verdict:** If held-out OAG stays above 25%, replace "ask anything" with one validated
job such as consented meeting commitments or deliberate visual bookmarking.

**K4 - Verdict:** Acceptable wrong-person and wrong-state rate is effectively zero for a
memory product. A single error in a small test blocks release; a larger pilot needs an
upper confidence bound below 1% before sensitive use.

**K5 - Inference:** It has already crossed that line for the current demo: a 1.8 GB app and
18 GB Mac answer model are not evidence for wearable feasibility.

**K6 - Verdict:** Cap resurrection at two weeks to build one coherent slice and three held-
out sessions. If the hard gates do not improve materially, stop adding helpers.

**K7 - Verdict:** Remove any channel whose ablation changes no frozen held-out answer, and
remove pitch/cockpit machinery that does not directly produce or verify a gate artifact.

## L - Live System and Latency

**L1 - Verified:** No. The phone was perceiving locally but posting to its own loopback,
the brain was down, and all inspected packets were unsent. That is local capture with a
broken live boundary.

**L2 - Unknown:** No end-to-end percentile latency dataset exists. Individual scripts log
some inference times, but there is no joined trace from photon to answer.

**L3 - Unknown:** No credible eight-hour current-architecture battery/thermal/throughput
run exists.

**L4 - Verified:** There are time gates and token buckets, but no unified backpressure or
queue-capacity controller across camera, OCR, VLM, ASR, disk, network, and UI.

**L5 - Verified:** It does not survive. `_LIVE` is volatile and the JSON projection can be
reset after restart.

**L6 - Verified:** `/health` returns configured strings without model ping, storage check,
ingest self-test, or phone reachability. It is process liveness theater.

**L7 - Verdict:** Backlog must be bounded by user purpose and age, not a magic count.
Current 147-packet accumulation with no alert is already beyond acceptable for a live
claim.

## M - Models and Dependency Reality

**M1 - Verified:** Models include FastVLM 0.5B/MLX, YOLO11n Core ML, MobileCLIP, Apple
Vision/Speech, Gemma 12B/27B via Ollama, bge-m3, nomic embeddings, MLX Whisper, and optional
frontier models. The repository does not provide a complete license/accuracy/latency table.

**M2 - Verified:** `pyproject.toml` declares only `cryptography`; scripts require many
undeclared ML, media, OCR, Apple-framework, and scientific packages. The venv is the real
dependency manifest.

**M3 - Verdict:** A clean machine cannot reproduce the environment from tracked files.
Large models and generated Core ML packages are ignored, Python dependencies are not
declared, and setup scripts cover only fragments.

**M4 - Verified:** Model names and package APIs are hard-coded across scripts. There is no
compatibility matrix, artifact registry, fallback contract, or reproducible container.

**M5 - Verified:** No. The gate harness itself notes model sampling/reload noise despite
temperature zero and therefore caches pre-gate drafts. Exact determinism is an assumption.

**M6 - Verified:** Installed package metadata still reports `openai` while current
`pyproject.toml` does not. Editable installs and a long-lived venv left stale state.

**M7 - Verdict:** Redistribution is currently legally unready. The Apple fork references
missing `LICENSE`/`LICENSE_MODEL` files, MobileCLIP has separate code/data/model licenses,
and Ultralytics offers AGPL-3.0 or enterprise terms. A commercial build needs counsel and
a tracked bill of materials before distribution.

**M8 - Unknown:** No consistent small-model ablation proves the large on-device and Mac
models earn their size. Model choice has been iterative rather than governed by a frozen
quality-per-watt benchmark.

## N - Native App Architecture

**N1 - Verdict:** `ContentView.swift` is a 2,582-line product core because successive
experiments accumulated inside the UI layer. It owns capture, inference, persistence,
networking, context, scheduling, and recall interaction, making isolated verification and
safe change nearly impossible.

**N2 - Verified:** `CaptureMode`, `MobileCLIPNamer`, and `SpatialWorld` are deleted in the
worktree, but roadmap/workorder references and device artifacts still depend on their old
behavior. Deletion reduced source volume without completing contract migration or data
cleanup.

**N3 - Verified:** `GroundTruthRecorder` remains compiled, is called for each sample, reads
a persisted `gtRecordingEnabled` preference, and writes `.mov` to Documents. The lean UI no
longer exposes an obvious control, so stale state can retain raw media invisibly.

**N4 - Unknown:** There is no current device-only automated plan covering orientation,
background/foreground transitions, camera interruption, thermal pressure, permission
revocation, disk exhaustion, or crash recovery.

**N5 - Verdict:** iOS 18.2 was inherited/configured for current frameworks, not justified
by target-market analysis. It excludes older devices and shrinks pilot options without a
documented feature requirement.

**N6 - Verified:** The simulator app is about 1.8 GB, dominated by 1.27 GB FastVLM weights
and 491 MB Core ML weights. Device thinning will change the number, but no archived device
IPA size, launch memory, install time, or pressure test is recorded.

**N7 - Verified:** `NSAllowsArbitraryLoads=true` permits broad insecure HTTP, not a scoped
local exception. This weakens transport security for the whole app.

**N8 - Verified:** There are no native unit, UI, performance, energy, concurrency, or
privacy test targets in the project. A simulator build is the entire automated native gate.

## O - Operations and Observability

**O1 - Verdict:** No supervisor is authoritative. launchd, keepalive shell scripts,
cockpit, autonomous supervisors, and manual Terminal commands overlap and disagree.

**O2 - Verified:** Runtime JSON/PID files were stale while processes were absent. State
writers report past intention, not current liveness.

**O3 - Verified:** No trace ID crosses phone observation, spool, ingest, projection,
retrieval, model answer, gate decision, and citation. Root-cause diagnosis is therefore
manual and often ambiguous.

**O4 - Verified:** The source contains many broad exception handlers, silent `pass`, Swift
`try?`, and best-effort fallbacks. The earlier total assembler crash was hidden this way;
the same failure class remains structurally common.

**O5 - Unknown:** There are no reliable alerts for packet loss, privacy breach, model
health, disk growth, corruption, or stalled capture. Cockpit panels are not alerting
infrastructure.

**O6 - Verified:** Logs contain sensitive speech, location, addresses, object/person
descriptions, and internal errors in plaintext. Access is whoever can read the device,
workspace, backups, or LAN endpoint.

**O7 - Verdict:** Immutable events and signed audit results should be durable; PIDs,
heartbeats, caches, indexes, dashboards, and progress bars should be disposable. The
current repository often treats disposable state as evidence.

## P - Privacy, Security, and Legal Boundary

**P1 - Verdict:** The only currently supportable claim is: "some recall paths intend not
to reopen raw media." The app-level and system-level no-storage claims are false.

**P2 - Verified:** They cannot survive. Current source can write `.mov`; the installed
container held raw video and audio; the UI's proof is hard-coded; and the audit script
usually checks only one subdirectory.

**P3 - Verdict:** Derived text changes risk but does not remove surveillance. The European
Commission defines names, addresses, identifiers, and linkable data as personal data even
when encrypted or pseudonymized, and treats collection, recording, storage, retrieval, and
transmission as processing. TRACE stores a compact behavioral dossier.

**P4 - Verified:** The threat model is absent. Current code is vulnerable to LAN memory
poisoning, unauthenticated reads and inference, prompt injection through visible text,
plaintext device loss, cloud misrouting, and secret compromise.

**P5 - Verdict:** Commercial deployment in Germany requires qualified counsel and, at
minimum, a defined controller/purpose/lawful basis, transparency, minimization, accuracy,
retention, security, data-subject rights, bystander handling, and likely a DPIA for broad
systematic monitoring. None exists.

**P6 - Verdict:** The exact classification depends on use. German StGB section 201 can
criminalize unauthorized recording of another person's nonpublic speech. Workplace
monitoring is tightly constrained; identity templates may be biometric; health/workplace
uses may affect AI Act risk. "No raw media" is not a legal exemption.

**P7 - Verdict:** A defensible proof requires a hardware/software trust boundary, no raw
write API in the production entitlement/build, whole-container continuous audit, signed
build provenance, encrypted event storage, authenticated egress, reproducible tests, and
independent review. The current proof panel substantiates nothing.

**P8 - Verified:** Security, privacy, and legal checks are absent from `make check`, CI,
and the native build gate. The only privacy unit test exercises an unused Python type.

## Q - Quality, Evaluation, and Statistical Validity

**Q1 - Verified:** The project edited against both datasets and froze partial score files
afterward. They are regression fixtures, not independent validation.

**Q2 - Verified:** No truly blind held-out set exists. The manifest reserves one old clip
without a frozen battery or text projection, which is not a usable test.

**Q3 - Verified:** The 85.7 and 62.5 live RAS claims exist only in roadmap and cockpit
prose. No row-level answers, citations, grades, judge identity, or immutable hash exists.

**Q4 - Verified:** `ask_live.py` scores an answerable question correct whenever the system
does not refuse, regardless of factual correctness or citation quality. This can reward a
fluent hallucination.

**Q5 - Verified:** Founder labels and local-model judges are used in different artifacts.
No blinded double review, inter-rater agreement, adjudication policy, or claim-level
citation check is enforced.

**Q6 - Verdict:** Overfit is already likely. Comments name individual questions, people,
objects, bags, trains, clocks, zips, and desired regressions throughout the 2,868-line
answer engine. A frozen blind set must be sequestered from developers and prompts.

**Q7 - Verdict:** Tiny batteries have wide uncertainty. A 6/7 result is not meaningfully
distinguishable from mediocre reliability and cannot support "near zero" hallucination.
The project reports point estimates without intervals.

**Q8 - Verdict:** The oracle rule assumes answerability unless marked otherwise, but oracle
review itself has no reproducibility, second reviewer, uncertainty class, or raw-evidence
citation contract. It can mislabel ambiguous questions.

**Q9 - Verdict:** RAS should be secondary. Required primary metrics are oracle capture
recall, claim precision, wrong-entity/state rate, citation entailment, calibration,
end-to-end latency, packet durability, battery/thermal cost, privacy breaches, and user
task completion.

## R - Recall and Reasoning Architecture

**R1 - Verified:** The actual engine is a monolithic legacy script behind a thin `Recall`
adapter. The modular application service delegates without owning retrieval or grounding.

**R2 - Verdict:** It cannot be changed safely at current complexity. The 700-line dossier
function mixes parsing, retrieval, ranking, entity binding, formatting, exceptions, and
benchmark-specific behavior without exhaustive tests.

**R3 - Inference:** Both exist, but accumulated benchmark patches dominate. Regex routing
is defensible for strict channel isolation such as audio; object/question-specific synonym
and state rules reveal overfit.

**R4 - Verified:** Fallback was used to keep demos answering after failures. Broad catches
still suppress specialist errors and can convert outages into plausible refusals.

**R5 - Verified:** The main brain receives a bounded dossier with channel caps and clipped
text. It is not an agent navigating an immutable lossless store, despite roadmap language.

**R6 - Verified:** There is no prompt-injection boundary. OCR/captions and model-produced
text are placed into prompts; visible adversarial instructions can influence the model.

**R7 - Verdict:** No enforced end-to-end contract exists. Components use dictionaries and
strings with optional fields; unit contracts in `src/trace_memory` are not the live data path.

**R8 - Verdict:** Conflicts must remain first-class competing claims with provenance,
valid-time, source dependence, and calibrated posterior confidence. Current code often
selects, suppresses, or narratively resolves them.

## S - Storage, Retention, and Schema Lifecycle

**S1 - Verified:** Ignored storage is an unmanaged research lake: raw video/audio, hundreds
of frames, plaintext derived memory, indexes, checkpoints, models, databases, duplicates,
and stale device artifacts. There is no enforced lifecycle.

**S2 - Verdict:** Oracle media should be isolated outside the production app/repository
under explicit consent and deletion dates. Device leftovers are privacy breaches; duplicate
source videos and stale projections are operational debt; current labels do not separate
them reliably.

**S3 - Verified:** Complete selective deletion is impossible today. There is no lineage
index from a person/time/fact to every projection, cache, log, score, cloud payload, and
backup.

**S4 - Unknown:** No day/month/year storage model exists. Current short captures already
produce hundreds of MB of ignored data and the installed app retained raw media.

**S5 - Unknown:** The app does not set/document file-protection classes for logs and spool.
Live Mac JSON is plaintext. The project has not audited backups or at-rest protection.

**S6 - Verified:** Schemas evolve by tolerant parsing and comments rather than migrations.
There is no registry, compatibility matrix, or downgrade path.

**S7 - Verified:** Some artifact provenance is hash-pinned, but semantic indexes and live
memory are not universally versioned against source, model, prompt, code, and schema.

**S8 - Unknown:** No audit covers iCloud device backup, Mac iCloud Documents, Spotlight,
crash diagnostics, or system logs. The repository itself already suffered iCloud-related
Git corruption.

## T - Tests and Governance

**T1 - Verified:** Governance targets the future shell because Phase 0 deliberately
established architecture before migration. It now creates a false green signal because
the risky runtime remains excluded.

**T2 - Verified, repaired 2026-06-22:** Default discovery now targets `tests`, and a clean
run executes 222 tests rather than the former 23. `make test` remains a narrower merge gate
covering 33 unit/evaluator tests.

**T3 - Verified, repaired 2026-06-22:** `trace_hub` is again an active package because the
repository actually depends on it. The two newly exposed failures were fixed: dossier
absence wording now matches its tested contract, and event dedup uses capture time rather
than host wall-clock time. Full result: 222 passed, with 83 deprecation warnings.

**T4 - Verified:** No test proves phone metadata survives. Actual inspection proves it
does not.

**T5 - Verified:** No test covers authorization because the brain server has none.

**T6 - Verified:** The Node audit can scan a supplied directory, but routine readiness
checks default to one Application Support path. It missed raw files in Documents and is not
in CI or the UI badge.

**T7 - Verified:** The server, live feed, web app, native behavior, and frontier path remain
mostly untracked/uncovered or build-only. The native simulator build succeeds, but there
are no native tests. CI still centers Linux Python checks on `src` and the narrow gate.

**T8 - Verdict:** Needed tests include schema/property tests, malformed payload fuzzing,
concurrent ingest, crash injection, replay idempotency, mutation tests for every gate,
prompt-injection fixtures, whole-container privacy audit, and device energy runs.

**T9 - Verdict:** Product evidence is a clean-device, held-out, row-level, signed run that
passes functional, privacy, security, and energy gates. Placeholder compilation and 87%
coverage of 139 shell statements are not product evidence.

## U - Usability, Reliability, and Accessibility

**U1 - Verified:** No. The current system is developer-operated.

**U2 - Verified:** Helpers report statuses and may retry, but there is no complete degraded-
mode UX or post-revocation validation. Some permission denial simply disables a channel.

**U3 - Verified:** Purpose strings are incomplete/inconsistent; there is no in-app privacy
policy or complete data-flow disclosure. Apple's current review rules require accurate
purpose strings, consent, retention/deletion disclosure, and an accessible privacy policy.

**U4 - Inference:** A pause flag exists, but there is no hardware indicator or independent
proof that camera/mic tasks, pending network calls, and background work stopped. Trusting
the same UI that hard-codes privacy status is insufficient.

**U5 - Verified:** Status text exposes some helper state; there is no user-level budget,
thermal, disk, queue, or model-load forecast.

**U6 - Verified:** Apple Speech is initialized with `en-US`; the Mac Whisper path forces
English. Vision OCR may recognize more, but multilingual all-channel support is absent.

**U7 - Unknown:** Accessibility of citations and the dense live overlay has not been
tested. No accessibility test or product requirement exists.

**U8 - Verdict:** A memory product should target 99.9% capture-service availability for
bounded sessions and zero high-confidence unsupported identity/state claims. Current
evidence is far below that trust bar.

## V - Velocity, Version Control, and Decision Quality

**V1 - Verified:** Velocity is currently represented by briefs, result files, changed
lines, autonomous tasks, and cockpit percentages. None consistently maps to held-out
validated capability.

**V2 - Inference:** Major work stayed uncommitted because rapid local iteration outran
integration discipline. This makes results unreproducible and increases the chance that
the installed app, source, and claimed metric refer to different states.

**V3 - Verified:** `main` is checked out with a large WIP; `feat/eval-integrity` is six
commits ahead of its remote; nested Claude worktrees hold divergent snapshots. There is no
declared release commit matching the device.

**V4 - Inference:** A substantial fraction of effort goes to orchestration and narrative:
70 ops files, many briefs/results, multiple dashboards/supervisors, and pitch artifacts.
The frozen product evidence remains two contaminated/incomplete datasets.

**V5 - Verified:** Repeated pivots produced abandoned relational hub, spatial world, 3D
renderer, multiple capture modes, backup scripts, and competing roadmaps within days.

**V6 - Verified:** No rigorous decision ledger exists. Status logs mix hypothesis,
implementation, unverified claims, later corrections, and sales framing.

**V7 - Verdict:** Move the repository out of iCloud, keep one Git worktree, remove nested
worktrees from the product directory, make reproducible commits before device installs,
and attach every result to commit/model/data hashes.

**V8 - Unknown:** Lead time is not measured. The activity log is too inconsistent to
derive diagnosis-to-held-out-improvement time.

## W - Wearable Feasibility and Economics

**W1 - Unknown:** No current-architecture all-day budget exists for energy, heat, memory,
storage, or inference duty cycle.

**W2 - Verified:** Lightweight helpers and FastVLM run on phone, but final reasoning uses
an 8.9/18 GB Gemma model on Mac. The demo is phone-plus-workstation.

**W3 - Verified:** The pitch requires an iPhone 17, Mac with multiple local models, Ollama,
same-LAN setup, and manual operation. Pilot/product hardware and unit economics are not
defined.

**W4 - Unknown:** There is no evidence that quality survives a deployable wearable compute
envelope. Existing OAG is poor even with expensive offline processing.

**W5 - Verdict:** A product without the developer Mac needs authenticated cloud text
reasoning or a much smaller on-phone brain, plus durable phone storage. Neither production
path exists.

**W6 - Verified:** Scheduling logic and tests exist, but its causal benefit to held-out
answerability per joule is unmeasured. It is a hypothesis, not a moat.

**W7 - Verdict:** Proposed gates are device IPA <=750 MB, cold launch <=5 s, peak memory
within supported-device limits, 8-hour drain <=60%, no serious thermal state, and useful
observation latency <=5 s. Current project has not measured them.

## X - External Reality: Market, Competition, and Compliance

**X1 - Corrected verdict:** The exact proven cell may be empty; the concept space is not.
Bee is audio-only and is not a visual-memory substitute. Meta records photos/video and
offers momentary visual assistance, not automatic text-only autobiographical recall.
Google has shown a context-aware prototype but has not published the required data-flow.
Halo is the direct thesis competitor: visual/audio long-term memory with no retained raw
rich media, but a cloud agent and encrypted server-side encoded memory. Trace's plausible
whitespace is specifically local-first durable derived memory plus no retained rich media
plus open grounded recall. No controlled evidence yet proves another product occupies it,
or that users want it.

**X2 - Inference:** No-raw storage alone is copyable - Halo already claims it - and it is a
severe fidelity constraint. The defensible system would be the verified combination of
local persistence, useful capture under that constraint, claim-level provenance, user
control, and efficient wearable execution. None is a moat before independent proof.

**X3 - Unknown:** No segment evidence shows buyers value raw deletion enough to accept
high OAG. Bee and Halo both make non-retention central, which is evidence that suppliers
believe privacy matters, not evidence of willingness to pay for Trace's exact tradeoff.

**X4 - Verified:** Commercialization is blocked by missing repository notices and an
unresolved software/model bill of materials. Ultralytics' official repository states
AGPL-3.0 or enterprise licensing; Apple source refers to missing accompanying licenses.

**X5 - Inference:** Meta and Google can reproduce components and own hardware, models, and
distribution, but their current business and data architectures are not interchangeable
with a local-first trust product. Acquisition is possible only after exceptional validated
quality, trust, users, or compliance capability; none is shown today.

**X6 - Verdict:** Counsel must review German speech/image law, GDPR roles and lawful basis,
bystander notice/rights, DPIA, international transfers, AI Act classification, App Store
rules, model licenses, and pitch substantiation before any public/commercial claim.

**X7 - Unknown:** No same-session competitor benchmark exists. Halo is the first product
that must be tested against Trace on capture coverage, unsupported claims, retention,
latency, battery, and raw-data lifecycle. Until then both "empty" and "occupied" are partly
launch-copy arguments.

## Y - Yield, Scope, and Resurrection Preconditions

**Y1 - Verdict:** The smallest credible slice is: one consented 10-minute visual-only
session, on-device OCR/object/scene text, authenticated append-only phone storage, later
local text recall, claim-level citations, and whole-container raw-media audit. No speech,
identity, GPS, frontier, 3D, night binding, or "ask anything."

**Y2 - Verdict:** Quarantine archive, old runbooks, raw oracle data, backups, cockpit,
supervisors, web app, pitch server, 3D/spatial code, and unverified result documents from
the supported runtime. Keep them readable but outside product imports and default docs.

**Y3 - Verdict:** Use one versioned `ObservationEvent`: immutable UUID, device/session,
captured/received monotonic and wall times, channel/model/schema versions, typed text fact,
confidence/calibration version, provenance, optional spatial metadata, hash, and consent
scope. Every projection and answer cites event IDs.

**Y4 - Verdict:** Use three held-out captures: static home/office detail, moving public
scene with multilingual text, and multi-person consented interaction. Freeze 50 questions
each before processing, with dual oracle review.

**Y5 - Verdict:** The invariant is: production binary has no raw-media persistence API;
whole app container and egress are continuously audited; any breach fails closed, erases
the artifact, alerts the user, and invalidates the run.

**Y6 - Verdict:** One command must provision pinned dependencies/models, build/install,
start authenticated brain, capture or replay a fixture, ask the frozen battery, verify
claim citations, audit the entire storage/egress boundary, and emit a signed result bundle.
No such command exists.

**Y7 - Verdict:** Progress can be a percentage only after denominator, acceptance evidence,
commit/data/model hashes, and automatic gate calculation are fixed. The current 75% is
subjective and should be deleted.

## Z - Zero-State Failure Premortem

**Z1 - Verdict:** The most likely six-month killers are, in order: benchmark overfit hiding
information loss; privacy/security contradiction destroying trust; no coherent user job;
unusable phone-plus-Mac operations; and wearable compute economics.

**Z2 - Verified:** All five are present now: OAG above 42% on contaminated data; raw media
and plaintext sensitive logs; no customer evidence; broken live linkage/manual setup; and
a 1.8 GB app plus 18 GB Mac model.

**Z3 - Verdict:** The largest hidden assumption is that short model-generated text can
preserve unknown future-answer facts while deleting the only ground truth. If false, the
entire architecture optimizes an irreversible information bottleneck.

**Z4 - Verified:** The current green gate misses raw-media persistence, unauthenticated
LAN access, broken phone metadata, dead services, monolithic runtime complexity, missing
dependencies, and hallucinated live-score validity. Full Python discovery is now green;
that repair does not add the missing native, privacy, security, or end-to-end gates.

**Z5 - Inference:** Without founder labor the system stops: capture configuration, process
startup, model provisioning, question creation, oracle grading, failure interpretation,
and recovery are manual.

**Z6 - Verdict:** No. A new engineer would encounter multiple canonical documents,
placeholders labeled production, broken entry points, ignored models/data, stale state,
and unsubstantiated metrics. Code alone does not reveal a supported system.

**Z7 - Verdict:** Kill the pitch percentage, categorical empty-market claim, no-raw proof
badge, frontier fallback, person identity, raw recorder, and all unmeasured channels now.
Preserve the narrower local-first whitespace hypothesis and the bounded visual-memory
experiment; rebuild its contracts from the event boundary outward.

## Six-Month Failure Chain

1. The team continues tuning the same small batteries, so RAS rises while general capture
   loss stays hidden.
2. A demo or pilot exposes a raw file, wrong-person memory, or unauthenticated LAN record;
   the central privacy/trust claim collapses.
3. Engineering adds another gate, helper, dashboard, and result document instead of
   narrowing the job or repairing the event boundary.
4. The app remains dependent on a developer Mac and manual recovery, preventing real
   longitudinal use and therefore preventing real product learning.
5. Competitors ship integrated hardware and ambient memory while TRACE has neither proven
   differentiation nor a compliant distribution path.
6. The project dies with substantial code volume and no trustworthy answer to whether the
   core text-only hypothesis ever worked.

## Resurrection Strategy

### P0 - Stop the False Claims (24 Hours)

1. Remove the constant `0 raw media` UI and disable/delete `GroundTruthRecorder` from the
   production target.
2. Delete raw media from the installed app only after preserving explicitly consented
   oracle evidence outside the production container; record the deletion audit.
3. Disable frontier egress, bind the brain to loopback until authenticated transport
   exists, and stop using the phone against the current unauthenticated server.
4. Mark live RAS 85.7/62.5, 75% progress, categorical empty market, and
   "architecturally incapable" as unsubstantiated. The supportable market claim is the
   narrower unproven local-first cell defined above.
5. Move the repository out of iCloud and checkpoint the current WIP to a named forensic
   branch without calling it a release.

### P1 - Build One Trustworthy Spine (Days 2-4)

1. Define `ObservationEvent` and make an append-only SQLite log the only source of truth.
2. Preserve phone timestamps, sequence, UUID, channel, model, confidence, pose/place only
   when consented, and content hash through ingest.
3. Replace mutable JSON writes with atomic/versioned projections replayed from events.
4. Add mutual authentication, TLS or a local encrypted tunnel, request limits, rate limits,
   and per-session authorization. Remove wildcard CORS and ignored tokens.
5. Encrypt events at rest and define correction/deletion tombstones plus projection purge.
6. Create a whole-container privacy test that fails the app and CI on any raw media.

### P2 - Prove the Narrow Hypothesis (Days 5-9)

1. Restrict to visual-only, consented, 10-minute sessions and three frozen held-out sets.
2. Capture oracle media in a physically/logically separate evaluation tool, never the
   production app.
3. Score fact capture recall before testing the brain. If the fact is absent, no reasoning
   work is allowed.
4. Replace scene-level citations with claim-to-event entailment and preserve conflicts.
5. Use deterministic baselines first: OCR lookup, typed object facts, time ordering, and
   explicit refusal. Add generation only where it beats them with zero new false claims.
6. Publish row-level signed results with confidence intervals and no developer exposure to
   the held-out battery before freeze.

### P3 - Decide, Do Not Drift (Days 10-11)

1. Continue broad visual memory only if all three sets achieve OAG <=25% and zero
   unsupported claims.
2. If capture fails, narrow to deliberate visual bookmarking or abandon text-only deletion.
3. If capture succeeds but reasoning fails, replace the monolith with event-native query
   services and compare local versus consented text-only cloud reasoning.
4. If privacy or legal review blocks ambient use, pivot to controlled environments with
   explicit participant consent.

### P4 - Earn Wearability (Days 12-14 and After)

1. Measure quality per joule for every helper and ablate anything that does not change a
   frozen held-out answer.
2. Run an eight-hour device test with thermal, battery, memory, storage, drop, and latency
   traces.
3. Build a non-developer setup and recovery journey.
4. Complete legal/privacy impact assessment, software/model bill of materials, privacy
   policy, retention/deletion controls, and App Store disclosures.
5. Only then restore live wear, speech, identity, GPS, frontier reasoning, or pitch claims,
   one separately consented and measured capability at a time.

## Non-Negotiable Exit Gates

- Any raw media in the production container: stop and invalidate the run.
- Any unauthenticated memory read/write path: no device testing on shared networks.
- Any unsupported claim or wrong-entity/state answer in held-out testing: no pitch/release.
- Any result without commit/data/model/prompt hashes and row-level artifacts: no claim.
- OAG above 25% after the focused capture cycle: narrow or kill "ask anything."
- No user evidence after a coherent prototype: stop engineering and validate demand.
