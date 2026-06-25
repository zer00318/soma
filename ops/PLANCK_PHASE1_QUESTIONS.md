# Planck Audit - Phase 1: Evidence Ledger and Foundational Questions

Date: 2026-06-22

This phase does not accept `NORTH_STAR.md`, `ROADMAP.md`, pitch copy, result files,
or cockpit percentages as truth. They are claims. Truth here means current source,
current artifacts, current device state, and commands reproduced during the scan.
Phase 1 stops at question formulation; it does not answer the questions below.

## Quantum Scan Disposition

- The workspace contains 40,273 files and 6.4 GB. The meaningful authored surface is
  327 tracked files plus current untracked work. The rest is dominated by 35,008 venv
  files, 702 nested Claude-worktree files, Xcode products, model weights, caches,
  databases, captured media, and generated projections.
- Authored text was inspected structurally and by execution path. Python was parsed by
  AST; Swift, shell, JS, HTML, plist, JSON, TOML, and Markdown were inventoried and
  cross-referenced. JSON/JSONL artifacts were schema-read and validity-checked. Binary
  media, databases, model weights, certificates, images, and build products were
  inspected by type, size, hash, metadata, containment, or build behavior rather than
  falsely described as line-readable source.
- The advertised gate passes: 32 selected checks, 87.1% coverage over 139 statements in
  `trace_memory.domain` and `trace_memory.application`, and a successful iOS-simulator build.
- The wider documented test command fails: 90 tests reached, with six import errors and
  one assertion failure. Default `pytest` silently follows `testpaths = ["tests/unit"]`
  and runs only 23 tests.
- `src/trace_memory` is mostly contracts and placeholders. `SqliteEventLog`, `EgressGuard`,
  `TextEgress`, `Observation`, `Binding`, and `Entity` do not run in the live product.
  Actual behavior remains in scripts and the native migration app.
- The current answer engine is a 2,868-line script. Its dossier builder is 700 lines
  with measured structural complexity 253; its grounding gate is 135 lines with
  complexity 60. Outside `src`, 85 functions exceed the advertised 60-line limit and
  157 exceed complexity 10, but governance does not check them.
- The installed iPhone app exists and the simulator target builds. The built simulator
  app is about 1.8 GB, targets iOS 18.2, and is still branded `FastVLM` in its bundle.
- A direct audit of the installed app container found a 12.9 MB `video.mov` and a
  546 KB `audio.m4a`. The UI's `0 raw media` badge is a literal string, and current
  source still contains `GroundTruthRecorder`, which can persist `.mov` files.
- The device also contains 1,964 plaintext native log lines, 147 unsent perception
  packets, precise GPS/address text, and a current failure posting to
  `http://127.0.0.1:8765`. The Mac brain and cockpit were not running during the scan;
  their recorded PID files were stale.
- The current brain server binds to all interfaces, has no enforced authentication,
  allows all CORS origins, ignores the phone's `X-TRACE-Token`, and accepts capture and
  ask traffic from the LAN. Rich phone timestamp, pose, location, source, and entity
  metadata are discarded when the server writes its recall memory.
- The native ask UI always sends `allow_frontier: true`. A frontier answer is not
  passed through the structural grounding gate and can be marked non-refused without
  a citation, despite the stated opt-in, grounded, cited text-egress contract.
- The claimed live RAS 85.7 and 62.5 results have no durable answer/grade artifact in
  the workspace or scratch area; they exist only in roadmap/cockpit prose. The gate
  regression cache is absent.
- Both frozen OAG datasets are tuning-exposed and incomplete. Current calculated gaps
  are 44.0% and 42.1%; neither is a clean held-out product result.
- Current Python packaging declares only `cryptography`, while the working scripts
  import a broad unpinned scientific, ML, Apple-framework, OCR, and media stack. There
  is no tracked license/notice file and no Python lockfile.
- The restored phone web app cannot import `phone_perceive` or `trace_memory.demo`; it also
  references missing web and certificate-generation assets. Legacy hub scripts and
  tests cannot import the hub after it was archived.
- The repository has five main-history commits spanning one day, one foundation tag,
  a large uncommitted worktree, an ahead feature branch, stale operational state, and
  a 296 MB archived corrupt Git store from the iCloud-hosted repository.

## A - Actual Product and Atomic Hypothesis

1. Is the product a private wearable memory, a Mac-hosted demo, an iPhone recorder, a
   live perception stream, a research harness, or a pitch artifact?
2. Which one-sentence hypothesis is falsifiable without smuggling in words such as
   `lossless-enough`, `amazed`, `moat`, or `near-zero`?
3. What observation would prove that text-only perception cannot support arbitrary
   retroactive questions at acceptable fidelity?
4. Is the valuable invention capture scheduling, derived-text memory, grounded recall,
   privacy architecture, or their integration, and which one is actually implemented?
5. Why does the code optimize for one angel demo before proving repeatable user value?
6. What is deliberately not the product, based on executable boundaries rather than
   repeatedly superseded documents?

## B - Beneficiary, Buyer, and Behavior

1. Who experiences a painful, frequent memory failure severe enough to wear a camera,
   grant microphone/location access, and tolerate false recall?
2. Is the user the wearer, a caregiver, an employer, an investor, or an acquirer, and
   whose incentives dominate product decisions?
3. Which job is valuable after an honest refusal rate above 40%, and which job becomes
   dangerous after one confident misattribution?
4. What behavior changes when users know strangers, speech, addresses, and routines
   become durable plaintext observations even without raw video?
5. What evidence shows demand for continuous physical-world memory rather than for a
   narrower reminder, note, accessibility, or search tool?
6. What willingness-to-pay, retention, or repeat-use evidence exists beyond founder
   enthusiasm and pitch preparation?

## C - Capture Contract

1. What exactly is captured per second on the current iPhone: frames, OCR, classifier
   labels, VLM prose, speech, pose, GPS, scene state, or only whichever helper happens
   not to fail?
2. Which capture channels operate on iOS, given that `TraceDetectorBridge` explicitly
   disables its subprocess worker there?
3. What is the source-of-truth timestamp when the phone timestamp is discarded and the
   brain invents a new relative time on arrival?
4. How are out-of-order, duplicate, delayed, offline, and replayed packets detected?
5. What happens to a fact observed during the server restart that resets `_LIVE`?
6. Why does `LIVE_MAX` truncate memory when the product claims perfect recall?
7. How is capture completeness measured rather than inferred from helper status text?
8. Can the system prove which field came from OCR, a detector, a VLM, ASR, or a model's
   reformulation after everything is collapsed into `caption`?

## D - Data Model and Durability

1. Why is the declared append-only event log unused by every live entry point?
2. What immutable event identity prevents duplicate observations across retries?
3. Is `kf_memory.json` an event log, projection, cache, checkpoint, API contract, or all
   five at once?
4. How can concurrent brain-server requests avoid an older snapshot overwriting a newer
   `kf_memory.json` after the lock is released?
5. What schema version migrates old captures when record shapes change?
6. What integrity check detects partial writes, truncation, stale semantic indexes, or
   mixed artifacts from another clip?
7. Which artifacts are authoritative when final JSON and checkpoint NDJSON disagree?
8. What backup, restore, replay, compaction, and retention procedures exist for a full
   day rather than a 160-second demo?

## E - Egress, Encryption, and Exposure

1. Why are `EgressGuard` and `TextEgress` tested but absent from the actual cloud and LAN
   egress paths?
2. Why is precise location/address-bearing memory stored and transmitted as plaintext?
3. What authenticates phone-to-Mac traffic when the client sends `dev-token` and the
   server ignores it?
4. Why does the brain bind to `0.0.0.0`, accept arbitrary capture/ask requests, and emit
   `Access-Control-Allow-Origin: *`?
5. What prevents a LAN peer from injecting false memories, reading timelines, burning
   local inference, or triggering frontier spend?
6. Why does the native UI opt into frontier egress on every ask rather than obtain
   explicit per-query consent?
7. How are frontier payloads audited, minimized, redacted, deleted, and linked to user
   consent?
8. What key lifecycle exists when the new encrypted codec is not wired to live storage?

## F - Fidelity and Information Loss

1. What does `lossless` mean when pixels become short, stochastic natural-language
   captions before the future question is known?
2. Which classes of facts are mathematically unrecoverable after compression into
   object labels and prose?
3. How is OCR fidelity measured across motion blur, glare, scripts, small text, and
   orientation rather than celebrated from a few readable signs?
4. How does the system distinguish observed activity from inferred intent, such as
   store presence from shopping activity?
5. What prevents repeated correlated VLM errors from looking like corroboration?
6. How much detail is lost at each boundary: sensor to helper, helper to record, record
   to server caption, caption to dossier, dossier to answer?
7. What oracle comparison demonstrates that the chosen text schema preserves the facts
   users later care about?

## G - Grounding, Citations, and Confidence

1. Does a citation prove the answer, or merely point to a retrieved scene that shares
   words with the question?
2. Why can the assembler return all retrieved scenes as citations even when only one,
   or none, supports the generated claim?
3. How is claim-level entailment tested independently from retrieval overlap?
4. Why can a frontier answer become accepted without structural grounding or verified
   citations?
5. Are confidence values calibrated probabilities, heuristic channel weights, prompt
   labels, or decorative numbers?
6. What held-out reliability curve maps confidence to actual correctness?
7. How are contradictions, negations, temporal changes, and mutually exclusive states
   represented without silently selecting the convenient observation?
8. What makes refusal consistent across paraphrases rather than a regex accident?

## H - Human Interface and Honest Proof

1. Why does the app display `0 raw media` as a constant rather than a measured invariant?
2. What should the UI show when raw media exists elsewhere in the same app container?
3. Why does the microphone permission say original audio will be recorded for later
   processing while product copy promises audio is never retained?
4. Can a user inspect, correct, delete, export, or dispute a false memory?
5. How does the user know the Mac brain is unreachable before 147 packets accumulate?
6. What does `watching` mean when a helper is unavailable, stalled, thermally throttled,
   or returning nonsense?
7. Are refusal, uncertainty, missing capture, model failure, and network failure visually
   distinct, or flattened into the same experience?
8. Why is a product called TRACE still bundled and permissioned as FastVLM?

## I - Identity, Binding, and Attribution

1. What stable identity exists for a person or object across frames without retaining a
   biometric or visual embedding?
2. How does the system avoid binding one stranger's clothing, name, object, or speech to
   another person or to the wearer?
3. Can entity-centric extraction recover identity after a mixed caption has already
   discarded spatial ownership?
4. What is the false-merge versus false-split rate on held-out multi-person scenes?
5. How are names verified rather than inferred from nearby OCR or speech?
6. What privacy and legal category do persistent person profiles create even without
   raw pixels?
7. How are corrections propagated through projections, indexes, dossiers, and answers?

## J - Jobs, Journeys, and End-to-End Reality

1. What single user journey works from fresh install through a real walk to a later ask
   without a developer, Terminal, cable, local model server, or manual artifact repair?
2. Which documented runbook describes the current app rather than a deleted capture mode
   or archived hub?
3. Can the founder reproduce the demo from a clean reboot when the cockpit agent is not
   loaded and both PID files are stale?
4. What happens when phone and Mac are on different networks or office client isolation
   blocks LAN traffic?
5. Is offline spool replay automatic, idempotent, observable, and provenance-preserving?
6. How many manual steps, hidden environment assumptions, and hard-coded local paths are
   required for one successful session?
7. What is the recovery journey after a helper crash, app kill, low battery, model load
   failure, full disk, or interrupted write?

## K - Kill Criteria and Strategic Honesty

1. At what OAG, hallucination, latency, battery, and setup thresholds is the central
   hypothesis declared dead rather than granted another helper?
2. How many held-out captures must fail before text-only recall is rejected?
3. Which result would force narrowing from `ask anything` to a constrained job?
4. What is the maximum acceptable rate of wrong-person or wrong-state answers?
5. When does a 1.8 GB app plus a large Mac model cease to be a wearable prototype and
   become a workstation demo?
6. What spend/time ceiling prevents indefinite accumulation of scripts and evaluators?
7. Which features are removed immediately if they do not improve a frozen held-out set?

## L - Live System and Latency

1. Is the current system live if the Mac brain was down, the phone targeted loopback,
   and all 147 inspected packets remained spooled?
2. What are p50/p95/p99 latencies from photons to durable observation and from question
   to cited answer?
3. What throughput is sustained over eight hours under realistic thermal and battery
   constraints?
4. What backpressure prevents camera, VLM, OCR, ASR, logging, posting, and UI work from
   starving one another?
5. How does the rolling server store survive process restart or Mac sleep?
6. How is live liveness measured end to end rather than by `/health` returning `ok` without
   checking the configured model?
7. What is the maximum tolerable packet backlog, and when does stale memory stop being
   useful memory?

## M - Models and Dependency Reality

1. Which exact model performs each production task on each platform, with what license,
   quantization, size, latency, and measured accuracy?
2. Why are most runtime dependencies undeclared and unlocked?
3. Can a clean machine reproduce the current environment from tracked files alone?
4. What happens when model names disappear, APIs change, or a Swift/Python dependency
   resolves differently?
5. Are local model outputs deterministic enough for gate-regression caching assumptions?
6. Why does packaging metadata disagree with the current declared dependency set?
7. Which models can legally be redistributed inside an app or investor build?
8. What smaller baseline proves each large model earns its size and compute cost?

## N - Native App Architecture

1. Why is a 2,582-line SwiftUI view the main capture, inference, persistence, networking,
   context, and ask controller?
2. Which deleted Swift components were genuinely dead, and which contracts vanished with
   them while docs still refer to their line numbers?
3. Why does a hidden persisted ground-truth toggle retain the ability to write `.mov`?
4. What is the device-only test plan for camera orientation, backgrounding, interruption,
   thermal pressure, permission denial, and low storage?
5. Why is the minimum OS 18.2, and what fraction of target users/devices does that exclude?
6. What does the 1.8 GB simulator bundle become after device thinning, and is install,
   update, launch, and memory pressure acceptable?
7. Why are broad arbitrary HTTP loads enabled for the whole app?
8. Where are native unit, integration, UI, performance, energy, and privacy tests?

## O - Operations and Observability

1. Which process supervisor is authoritative: launchd, shell keepalive, cockpit, Claude
   supervisor, or manual Terminal panes?
2. Why did operational state claim activity while the services and PIDs were stale?
3. What structured event links phone capture, spool, server ingest, retrieval, answer,
   grounding decision, and citation into one trace?
4. How are silent `except`, `try?`, and best-effort branches surfaced before they become
   false product behavior?
5. What alarms exist for packet loss, model unavailability, corrupt memory, growing disk,
   stalled capture, and privacy invariant breach?
6. Are logs themselves sensitive product data, and who can read or retain them?
7. What operational state is durable, what is disposable, and what is stale theater?

## P - Privacy, Security, and Legal Boundary

1. Is the privacy claim `production recall never reads raw media`, `the app never stores
   raw media`, or `the entire system is architecturally incapable of raw storage`?
2. How can the strongest version survive current source and device evidence of raw video
   and audio storage?
3. Does derived text containing names, speech, routines, precise coordinates, addresses,
   health context, and bystander descriptions reduce surveillance risk or merely change
   its format?
4. What threat model covers a hostile LAN, stolen phone, compromised Mac, malicious web
   page, prompt injection in visible text, poisoned capture packet, and leaked API key?
5. What lawful basis, notice, consent, bystander handling, deletion right, and retention
   policy apply in Germany/EU?
6. Does continuous person/speech/location processing trigger biometric, workplace,
   telecommunications, recording, or high-risk AI obligations?
7. What independent technical proof could substantiate `structurally unavailable` in
   marketing without misleading users or investors?
8. Why are security, privacy, and legal claims absent from enforced release gates?

## Q - Quality, Evaluation, and Statistical Validity

1. Why are both frozen OAG datasets tuning-exposed and incomplete?
2. Where is the truly blind held-out set that no prompt, regex, vocabulary, or gate edit
   has seen?
3. Why is the claimed live RAS not backed by a durable row-level result artifact?
4. Does binary `answer/refuse` scoring count a fluent but wrong answer to an answerable
   question as correct?
5. Who judges correctness, inter-rater agreement, citation support, partial truth, and
   harmful misattribution?
6. How are repeated edits against 25 questions prevented from becoming benchmark overfit?
7. What confidence intervals apply to results from 7, 8, 19, or 25 questions?
8. Why does OAG label every founder-reviewed item oracle-answerable by default, and how is
   oracle quality itself audited?
9. What metrics cover capture recall, entity binding, calibration, latency, energy,
   privacy, and end-to-end task success instead of collapsing everything into RAS?

## R - Recall and Reasoning Architecture

1. Is the actual recall engine a modular application service or a monolithic legacy
   script behind a type adapter?
2. How can a 700-line dossier builder be changed without unknowable cross-channel
   regressions?
3. Which question classifiers are principled routing and which are accumulated benchmark
   patches?
4. Why are many specialist failures swallowed and converted to fallback behavior?
5. Does the reasoner navigate a lossless store iteratively, or receive a truncated prompt
   assembled by hard caps and token overlap?
6. How are prompt injection and adversarial visible text prevented from controlling the
   answer model?
7. What is the contract between retrieval, entity resolution, confidence, grounding,
   refusal, and citation, and where is it tested end to end?
8. When two channels disagree, what deterministic policy preserves uncertainty instead
   of manufacturing a single narrative?

## S - Storage, Retention, and Schema Lifecycle

1. Why do ignored data directories contain hundreds of frames, raw media, audio, model
   outputs, semantic indexes, duplicate source videos, and plaintext memories without a
   documented retention policy?
2. Which raw artifacts are oracle-only, which are obsolete, which are device leftovers,
   and which are accidental privacy violations?
3. How does a user delete one person, place, time range, or sensitive fact from append-only
   memory and every derivative index?
4. What disk growth should be expected for one day, month, and year?
5. What encryption-at-rest and iOS file-protection classes apply to every stored artifact?
6. How are schema changes rolled forward and backward without invalidating old memory?
7. Why are semantic indexes accepted without a universal source hash/version contract?
8. What prevents iCloud, backups, Spotlight, crash reports, or logs from copying sensitive
   derived memory outside the claimed boundary?

## T - Tests and Governance

1. Why does `make check` enforce strict quality on the thin shell while excluding the
   code that runs the product?
2. Why does default `pytest` run only unit tests and omit most of `tests/`?
3. Why does the documented full suite currently fail after the hub archive?
4. What test proves the phone payload survives the server boundary with timestamp, pose,
   place, source, entity, and provenance intact?
5. What test proves unauthenticated LAN clients cannot ingest, ask, read, or trigger egress?
6. What test fails when raw media exists anywhere in the app container rather than one
   convenient Application Support directory?
7. Why are the brain server, live feed, phone web app, native app, and frontier path absent
   from CI?
8. What mutation, property, fuzz, concurrency, crash-recovery, and adversarial tests are
   needed before regex-heavy grounding can be trusted?
9. Which green check is product evidence, and which merely proves a placeholder compiles?

## U - Usability, Reliability, and Accessibility

1. Can a non-developer install, pair, configure, capture, ask, understand, and recover the
   product without reading terminal instructions?
2. What happens when permissions are denied or revoked after first launch?
3. How are camera, microphone, location, and cloud usage explained honestly and accessibly?
4. Can the wearer pause sensing instantly and verify that sensing really stopped?
5. How are battery drain, heat, bandwidth, storage, and model-loading delays communicated?
6. Does the product work for languages other than the hard-coded English ASR locale?
7. Are citations usable by blind, low-vision, cognitively impaired, or nontechnical users?
8. What reliability target applies to a memory product whose failures may alter user belief?

## V - Velocity, Version Control, and Decision Quality

1. Is current velocity measured by shipped validated capability, lines changed, result
   documents, cockpit percentages, or autonomous task volume?
2. Why is two days of major product work still uncommitted on `main` while another branch
   is six commits ahead?
3. Which branch and worktree is authoritative when nested worktrees contain divergent
   snapshots and stale task claims?
4. How much time is spent creating briefs, result files, supervisors, dashboards, and
   backups versus improving held-out end-to-end quality?
5. How often have roadmap pivots invalidated code before it was deleted or archived?
6. What decision log records hypothesis, expected metric movement, actual result, and
   reversal without rewriting history?
7. How does the team prevent iCloud corruption, duplicate conflict files, and another
   forensic Git rebuild?
8. What is the measured lead time from diagnosed miss to held-out verified improvement?

## W - Wearable Feasibility and Economics

1. What battery, thermal, memory, and storage budget is available for an all-day iPhone or
   glasses workload?
2. What fraction of current computation is truly on-device versus delegated to an 18 GB
   Mac model?
3. What hardware is required for the pitch, prototype, pilot, and plausible product, and
   what does each configuration cost?
4. Can the quality target survive the smaller models and power envelope of wearable
   hardware?
5. What network assumptions remain after removing the developer Mac?
6. Is the salience scheduler a demonstrated economic advantage or an unwired hypothesis?
7. What install size, launch memory, sustained inference rate, and device temperature are
   acceptable to users?

## X - External Reality: Market, Competition, and Compliance

1. Is the claimed empty quadrant still empty after current products, research systems,
   platform APIs, and privacy-preserving wearable approaches are examined?
2. Is `no raw storage` a defensible moat, a feature competitors can copy, or a constraint
   that permanently lowers answerability?
3. Which customer segment values the constraint enough to accept its recall loss?
4. What patents, licenses, upstream code obligations, model terms, and trademarks govern
   commercialization when no license/notice inventory is tracked?
5. Would Meta, Apple, or Google acquire this capability, reproduce it internally, or reject
   the legal/reputational risk?
6. What regulatory and platform-policy claims require qualified legal review before pitch
   language is used?
7. What competitor benchmark uses the same blind questions, device budget, privacy boundary,
   and failure penalties?

## Y - Yield, Scope, and Resurrection Preconditions

1. Which smallest vertical slice would prove real value without the current scripts,
   dashboards, spatial remnants, archived hub, and pitch machinery?
2. What must be deleted, quarantined, or explicitly labeled research-only before anyone can
   understand the product surface?
3. Which one event schema must every phone, server, store, evaluator, and answer path share?
4. Which three held-out captures and question sets would be sufficient to make the next
   decision credible?
5. What privacy invariant must become executable across the entire app container and egress
   boundary before any public demo?
6. What single reproducible command should build, start, capture, replay, ask, audit, and
   score the supported system?
7. What must be true before progress can be expressed as a percentage at all?

## Z - Zero-State Failure Premortem

1. If this fails in six months, was it killed by information loss, hallucination,
   misattribution, privacy contradiction, legal exposure, unusable setup, compute cost,
   benchmark overfit, or lack of demand?
2. Which of those killers is already present in current evidence rather than hypothetical?
3. What single hidden assumption has the largest blast radius if false?
4. What failure would remain invisible under the current green gate and cockpit reporting?
5. What happens after the founder stops manually supplying clips, questions, fixes, models,
   network setup, and interpretation?
6. If all roadmap prose disappeared today, could a new engineer infer the product, start the
   supported system, reproduce the headline metric, and verify the privacy claim from code?
7. What must be killed now so the one potentially valuable capability has room to become a
   coherent, testable product?
