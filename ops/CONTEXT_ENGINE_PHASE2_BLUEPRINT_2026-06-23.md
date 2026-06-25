# Context Engine Phase 2 Blueprint - 2026-06-23

> SUPERSEDED HEADER (2026-06-23 PM): the "post-trust / not the active plan" note
> below predates the founder's full-architecture sanction. This blueprint (device
> topology, observation contract, projections, latency classes) is now ACTIVE
> reference for the multi-modal build. It covers HELPERS and MEMORY but stops at a
> retrieval-only planner; the missing INJECTION layer (knowledge expansion) and the
> standing-ground answer contract are specified in
> `ops/CONTEXT_ENGINE_PHASE2B_INJECTION_LAYER_2026-06-23.md`. Build per
> `ops/CONTEXT_SPRINT_2026-06-23.md`. Honesty gate still governs. Original note kept:
>
> Status: POST-TRUST REFERENCE, NOT THE ACTIVE BUILD PLAN.
>
> Active plan is `ops/CHIEF_DECISION_READING_FIRST_2026-06-23.md`: finish the
> n≈50 founder-gold reading eval, verify anchored live consensus recall, then
> integrate `consensus_recall` into the existing `src/trace_memory` event log.
> Do not use this document to justify synthetic helper-output demos or a new
> kernel rewrite before the reading metric is trusted.

## Executive Decision

Build Trace as a cross-device private context engine, not as a standalone
wearable brain.

The current-technology architecture that can work today is:

```text
wearable or phone sensors
  -> local ring buffers
  -> cheap continuous detectors
  -> adaptive attention scheduler
  -> typed observation helpers
  -> encrypted append-only event log
  -> projection workers
  -> entity graph + current-state graph + temporal index + behavior ledger + vector index
  -> query planner
  -> coverage/refusal gate
  -> evidence-locked answer generator
```

The wearable should be a sensor and attention device. The phone should be the
always-carried compute/storage coordinator. A laptop or home hub should run heavy
sleep-pass binding and larger local models. Cloud is optional and text-only.

This is the only architecture that satisfies the Phase 1 matrix without needing
future hardware.

## Research Anchors

Current commercially available building blocks exist:

- Apple Vision/Core ML/Speech/ScreenCaptureKit can support local OCR, model
  inference, speech, and screen capture on Apple platforms.
- Google ML Kit Text Recognition v2 can do real-time text recognition and
  returns bounding boxes, confidence, language, and text structure.
- MediaPipe Solutions provide cross-platform on-device tasks such as object
  detection, hand landmarks, pose, face, image embedding, audio classification,
  and LLM inference.
- whisper.cpp runs Whisper locally across macOS, iOS, Android, Windows, Linux,
  WebAssembly, Raspberry Pi, and accelerators including Metal/Core ML/OpenVINO.
- MLX is practical on Apple Silicon for local LLM/VLM/embedding research and
  deployment on Mac-class hub devices.
- SQLite WAL is appropriate for the local event log because readers and writers
  can proceed concurrently.
- SQLCipher gives full-database SQLite encryption across mobile and desktop.
- sqlite-vec gives local vector search inside SQLite, with the caveat that it is
  still pre-v1.
- W3C screen capture work and platform APIs show screen context is feasible but
  must be permission-forward because screen capture has major security risks.

Sources:

- Google ML Kit Text Recognition v2:
  https://developers.google.com/ml-kit/vision/text-recognition/v2
- MediaPipe Solutions:
  https://developers.google.com/edge/mediapipe/solutions/guide
- whisper.cpp:
  https://github.com/ggml-org/whisper.cpp
- MLX:
  https://github.com/ml-explore/mlx
- SQLite WAL:
  https://www.sqlite.org/wal.html
- SQLCipher:
  https://www.zetetic.net/sqlcipher/
- sqlite-vec:
  https://github.com/asg017/sqlite-vec
- Android NNAPI:
  https://developer.android.com/ndk/guides/neuralnetworks
- W3C Screen Capture:
  https://www.w3.org/TR/screen-capture/
- Apple Vision/Core ML/Speech/ScreenCaptureKit:
  https://developer.apple.com/documentation/vision
  https://developer.apple.com/documentation/coreml
  https://developer.apple.com/documentation/speech
  https://developer.apple.com/documentation/screencapturekit

## Device Topology

### Tier 0: Wearable Sensor Node

Role:

- Capture camera/audio/IMU/location hints.
- Run only always-on cheap classifiers when hardware permits.
- Maintain a seconds-long raw ring buffer.
- Send compressed candidate frames/audio features/typed observations to phone.

Do not make the wearable responsible for full VLM, long-context reasoning, or
large vector search. That is how competitors melt or become gimmicks.

Minimum viable hardware today:

- Phone-as-wearable for prototype.
- Glasses/camera module later if line-of-sight matters.
- Earbuds/watch as optional audio/gesture/biometric context sources.

### Tier 1: Phone Context Coordinator

Role:

- Own live capture permissions.
- Run local OCR, ASR, object/hand/pose/person detectors, screen/app connectors
  where allowed.
- Own the encrypted event log.
- Maintain the current-state graph for "now" questions.
- Run small embeddings and small local classifiers.
- Decide what is worth sending to hub.

This is the product's live brain.

### Tier 2: Local Hub

Role:

- Run heavy VLM/LLM passes, re-ID, entity cleanup, sleep binding, behavior
  aggregates, and batch embedding.
- Rebuild projections from event log.
- Evaluate answer quality and coverage gaps.

Commercially viable today:

- MacBook/Mac mini/Mac Studio with MLX, llama.cpp/Ollama, whisper.cpp, Core ML.
- Snapdragon/Intel/AMD NPU laptop can become viable if the runtime path is
  stable, but do not bet the prototype on one vendor's NPU stack.

### Tier 3: Cloud Text Reasoner

Role:

- Optional.
- Receives only text evidence packets with provenance IDs.
- Never receives raw frames, raw audio, or unbounded screen dumps.

Cloud is not the context engine. It is a language layer when local answer
quality is insufficient.

## Core Data Flow

### 1. Raw Signal Enters Ring Buffers

Each sensor writes to short-lived local buffers:

- Camera ring: 5-30 seconds, downsampled preview plus optional still capture on
  fixation.
- Audio ring: 10-30 seconds PCM or features, consumed by VAD/ASR/sound helper.
- Screen ring: permissioned frames or UI snapshots, never continuous by default.
- Metadata stream: time, motion, location, battery, thermal, app/session hints.

Raw buffers are not memory. They are working memory for helpers.

Default policy:

- Raw camera/audio/screen buffers expire automatically.
- Raw stills are consumed and deleted after typed observations are emitted.
- Debug capture requires explicit dev mode and visual indicator.

### 2. Cheap Continuous Detectors Gate Expensive Helpers

Always-on detectors:

- Motion/stability.
- VAD and wake/audio event detection.
- Low-res OCR candidate detection.
- Object/person/hand presence.
- Scene-change detection.
- App/screen-change detection.
- Location/place-change detection.

These detectors emit attention signals, not final memory.

Expensive helpers run only when attention clears threshold:

- High-res OCR.
- VLM attribute/state pass.
- ASR segment finalization.
- Speaker/person binding.
- Order/UI semantic extraction.
- Entity re-ID.
- Behavior update.

### 3. Helpers Emit Typed Observations

Every helper must emit the same contract:

```json
{
  "observation_id": "uuid",
  "helper_id": "ocr.highres.v1",
  "helper_version": "1.0.0",
  "source_channel": "camera|audio|screen|location|connector|user",
  "captured_at_ms": 0,
  "valid_from_ms": 0,
  "valid_to_ms": null,
  "subject": {
    "kind": "object|person|place|screen|speech_segment|order|app|merchant",
    "candidate_id": "track-or-entity-candidate",
    "label": "visible text surface"
  },
  "predicate": "contains_text",
  "object": {
    "kind": "text|entity|number|state|event",
    "value": "Needs Input"
  },
  "attributes": {
    "bbox": [0.1, 0.2, 0.4, 0.3],
    "language": "en",
    "spatial_anchor": "upper right frame",
    "place_hint": "home desk"
  },
  "confidence": 0.91,
  "evidence": {
    "snippet": "Needs Input",
    "raw_retained": false,
    "raw_ref": null
  },
  "refutation_cues": [
    "newer screen state lacks this badge",
    "higher-confidence OCR contradicts text"
  ]
}
```

No helper gets an exception. If it cannot emit this, it is not part of the
context engine.

### 4. Append-Only Event Log Is The Source Of Truth

Use encrypted SQLite as the local event store:

- `observations`: immutable helper outputs.
- `raw_debug_refs`: dev-only, never product default.
- `projection_offsets`: replay positions for each projection.
- `corrections`: user and system corrections as first-class observations.
- `sync_envelopes`: encrypted cross-device event transfer.

Use WAL mode for concurrent write/read projections. Use SQLCipher or platform
equivalent for encrypted storage.

Rule:

- The log is truth.
- Graphs, vector indexes, behavior ledgers, and current-state stores are
  rebuildable projections.

### 5. Projection Workers Build Queryable Memory

Projection workers subscribe to the event log.

Required projections:

1. Entity registry:
   - persistent people, objects, places, merchants, apps, menu items, screens,
     documents, devices.
   - stores candidate merges/splits, not just final IDs.

2. Relation graph:
   - `held_by`, `worn_by`, `left_of_self`, `inside`, `on`, `contains_text`,
     `said_by`, `ordered_from`, `favorite_in_app`, `located_at`,
     `state_changed_to`.

3. Current-state graph:
   - latest valid state facts with expiry.
   - optimized for "now", "left of me", "what's open", "where is X".

4. Temporal episode index:
   - visits, conversations, screen sessions, meals, shopping, commutes,
     object-placement episodes.

5. Behavior ledger:
   - frequency, recency, seasonality, preference, routine, deviation.
   - required for "usual", "favorite", "normally", "again", "last time".

6. Vector index:
   - embeds safe text summaries, not raw media.
   - useful for fuzzy recall, never authoritative alone.

7. Coverage ledger:
   - records which helpers were active or missing in each time/place/app window.
   - powers honest refusals.

## Helper Runtime Map

| Helper | Today path | Runs where | Persistence |
| --- | --- | --- | --- |
| Low-res object/person detector | MediaPipe, Core ML, ML Kit/Object Detection, YOLO-style mobile model | phone/wearable | observations and track IDs |
| Hand/pose | MediaPipe hand/pose landmarks, Vision body pose where available | phone | relation candidates |
| OCR | Apple Vision, Google ML Kit Text Recognition v2, Tesseract fallback, high-res still pass | phone/hub | text observations, bbox, confidence |
| ASR | Apple Speech on-device, WhisperKit, whisper.cpp | phone/hub | transcript segments, no raw audio |
| Sound events | Apple SoundAnalysis where available, MediaPipe/audio classifier, custom DSP features | phone | sound event observations |
| Screen/UI | ScreenCaptureKit on macOS, platform accessibility APIs, browser extension, user-permission capture | phone/desktop/hub | UI state observations |
| Location/place | CoreLocation/Android location, Wi-Fi/BLE hints, geocoder, calendar/place connector | phone | place episodes |
| Commerce/order | email/receipt import, delivery-app screen parser, bank/card connector where authorized | phone/hub | order events and merchant entities |
| Message/calendar | authorized local import/connectors | phone/hub | relationship, commitment, event observations |
| VLM attribute/state | mobile VLM for small tasks, larger local VLM on hub | phone/hub | state/attribute observations |
| Entity re-ID | deterministic first, embedding/VLM-assisted second | phone/hub | merge/split candidates |
| Behavior aggregation | deterministic ledger | phone/hub | aggregate facts with support counts |

## Parameter Resolution By Matrix Section

### A-B: Acquisition And Backpressure

Resolution:

- Never process continuous raw streams uniformly.
- Use adaptive capture states: idle, movement, fixation, interaction, screen,
  speech, sleep-pass.
- Raw stream is sampled cheap first, high-res second.
- Every queue has a max age and drop policy.

Hard budgets for prototype:

- Live current-state facts must be emitted within 1-5 seconds.
- Expensive VLM tasks have hard timeouts.
- Anything older than 60 seconds without projection is sleep-pass, not live.

### C-D: Attention And Minimization

Resolution:

- Attention scheduler is the central product primitive.
- Salience = dwell + novelty + interaction + speech reference + app focus +
  place change - motion/thermal/battery penalty.
- Raw data is consumed into typed observations and discarded.

The scheduler owns:

- which helper runs,
- at what resolution,
- on which device,
- with what timeout,
- under what privacy mode.

### E-F: Entity Continuity And Fact Shape

Resolution:

- All observations may reference candidate IDs.
- Projections decide durable entity IDs.
- Entity merge is reversible.
- State facts carry validity windows.
- Negative evidence is explicit.

Data model:

- `entity_candidates`
- `entity_identities`
- `entity_merge_edges`
- `relations`
- `state_facts`
- `state_invalidations`

### G-Q-Z: Grounding, Quality, Zero-Trust Answering

Resolution:

- The answer model never sees raw unbounded memory.
- Query planner creates required fact checklist.
- Coverage gate verifies helper availability.
- Evidence resolver fetches only supporting observations/projections.
- Generator phrases evidence packet.
- Every answer sentence gets citation IDs.
- Unsupported answers become structured refusals.

Answer packet:

```json
{
  "question": "What is my usual order?",
  "required_fact_types": ["merchant", "order_events", "item_frequency"],
  "coverage": {
    "transaction_order": "present",
    "screen_ui_semantics": "present",
    "behavior_ledger": "present"
  },
  "evidence": [
    {"type": "order_event", "merchant": "Garden Wok", "item": "spicy chicken bowl", "t": "..."},
    {"type": "order_event", "merchant": "Garden Wok", "item": "spicy chicken bowl", "t": "..."},
    {"type": "ui_state", "predicate": "favorite_in_app", "merchant": "Garden Wok"}
  ],
  "allowed_inference": "aggregate_preference"
}
```

If `transaction_order` is absent, the answer is refusal, not a guess.

### H-L-M-X: Hardware, Latency, Model Placement, Cross-Device

Resolution:

- Wearable does sensing and maybe tiny classifiers.
- Phone does live helpers and current-state projection.
- Hub does deep re-ID, VLM enrichments, long-context cleanup, and behavior
  rebuilds.
- Cloud receives only typed text evidence when explicitly enabled.

Latency classes:

| Class | Target | Examples | Device |
| --- | --- | --- | --- |
| Reflex | under 1s | motion, VAD, scene change, app change | wearable/phone |
| Live | 1-5s | current OCR, current objects, ASR segment, left/right relation | phone |
| Near-live | 5-60s | person binding, high-res OCR, UI state, object state | phone/hub |
| Sleep-pass | minutes-hours | behavior ledger, entity cleanup, long video/scene binding | hub |
| Ask-time | under 2s after evidence fetch | answer phrasing | phone/hub/cloud text |

### I-J-N-R-T-W-Y: Indexing, Joins, State, Time, World, Yield

Resolution:

- Do not rely on one index.
- The event log feeds multiple projections, each built for a query class.

Required joins:

- time overlap,
- entity ID,
- candidate entity ID,
- place ID,
- app/session ID,
- merchant/order ID,
- episode ID,
- source helper coverage.

Yield management:

- Track "future answer usefulness" per helper.
- Helpers that emit low-use facts get throttled.
- User unanswered questions become coverage gaps and roadmap inputs.

### K-O-P-S-U-V: Knowledge, Modes, Policy, User Model, Replay

Resolution:

- Personal memory answers require personal evidence.
- Public/world knowledge can explain terms but cannot invent personal facts.
- Private mode pauses capture and seals projections.
- Corrections are high-authority observations.
- Every helper output stores helper/model/schema version.
- Every projection must replay from the log.

## The Three Databases

Use one physical encrypted SQLite database initially, but three logical stores.

### 1. Event Log

Append-only, immutable, encrypted.

Tables:

- `observations`
- `observation_attributes`
- `evidence_snippets`
- `helper_heartbeats`
- `coverage_windows`
- `corrections`

### 2. Structured Projections

Rebuildable.

Tables:

- `entities`
- `entity_aliases`
- `entity_candidates`
- `relations`
- `state_facts`
- `episodes`
- `places`
- `orders`
- `messages`
- `behavior_aggregates`

### 3. Retrieval Projections

Rebuildable.

Tables:

- `text_chunks`
- `embedding_vectors`
- `fact_index`
- `question_coverage_index`
- `answer_audit_log`

## Behavior Ledger

This is the missing substrate for "usual".

Behavior facts are aggregates with support, not vibes:

```json
{
  "aggregate_id": "uuid",
  "subject_entity_id": "user",
  "predicate": "usual_order_at",
  "object_entity_id": "merchant:garden_wok",
  "value": {
    "item": "spicy chicken bowl",
    "modifiers": ["no onions"],
    "support_count": 5,
    "window_days": 60,
    "last_seen_at": "...",
    "competing_items": [
      {"item": "tofu bowl", "support_count": 2}
    ]
  },
  "confidence": 0.84,
  "evidence_ids": ["obs1", "obs2", "obs3", "obs4", "obs5"]
}
```

Behavior ledger rules:

- Require minimum support count.
- Weight recency.
- Keep competing hypotheses.
- Never answer if the relevant source coverage is absent.
- Cite aggregate plus underlying events.

## Current-State Graph

This is the substrate for "now".

State facts:

- have `valid_from_ms`, `valid_to_ms`, `last_confirmed_ms`, `expiry_policy`.
- are invalidated by newer contradictory facts or coverage gaps.
- are scoped by place/episode when appropriate.

Examples:

- `object:keys located_at surface:desk`
- `object:mug left_of self`
- `screen:ubereats restaurant:garden_wok favorite_in_app true`
- `bag:blue closure_state zipped`

Current-state answers must prefer:

1. direct current evidence,
2. latest valid state,
3. stale memory with warning,
4. refusal.

## Query Planner

The planner maps user prompt to evidence requirements.

Examples:

| Query | Required facts | Missing-context refusal |
| --- | --- | --- |
| What's left of me? | current self anchor, current objects, egocentric relation | "I had no current spatial scene graph active." |
| What is my usual order? | merchant, order events, item frequency, optional favorite UI | "I do not have order history for that merchant." |
| Who said they would send notes? | speech segment, commitment, speaker/person identity | "I heard the sentence but did not bind a speaker." |
| Where did I put keys? | object entity, placement event, surface/place, latest state | "I saw keys earlier but did not observe a placement event." |

The planner is not a general LLM prompt. It is a classifier + rule planner with
LLM fallback only for ambiguous phrasing.

## Prototype Path Today

### Week 1: Engine Spine

Build:

- observation contract,
- encrypted SQLite event log,
- projection runner,
- coverage ledger,
- query planner skeleton,
- evidence-locked answer packet.

Do not build new perception first. Build the spine.

### Week 2: Three Simulated Domains

Inject typed observations for:

1. Current physical scene:
   - mugs, keys, bag, spatial relations, duplicate entities.
2. Conversation:
   - ASR segment, known person, said_by relation, commitment.
3. Restaurant/order:
   - order events, favorite UI state, behavior aggregate.

The simulation should fake helper outputs, not answer outputs.

### Week 3: Live Helper Integration

Wire live helpers into the same observation contract:

- OCR,
- ASR,
- object/person detector,
- location,
- screen/UI on desktop,
- one transaction/order importer fixture.

### Week 4: Pitch Prototype

Demo flow:

1. Ask "what's left of me?" - answer from current-state graph.
2. Ask "are those duplicates?" - answer from entity registry.
3. Ask "who said they would send the notes?" - answer from ASR plus speaker binding.
4. Ask "what is my usual order there?" - answer from order behavior ledger plus UI favorite evidence.
5. Ask unsupported question - refusal names missing helper coverage.

## Hard Product Rules

1. No raw media as memory.
2. No helper without observation contract.
3. No answer without coverage gate.
4. No "usual" without behavior support count.
5. No "now" without current-state freshness.
6. No person claim without identity confidence.
7. No UI claim from OCR alone if the UI semantic helper is required.
8. No cloud raw context.
9. No demo that fakes final answers.
10. No architecture that requires unreleased hardware.

## Final Blueprint

The practical current-technology product is a private, event-sourced,
cross-device context operating system:

- Phone/wearable senses continuously but cheaply.
- Attention scheduler allocates compute.
- Helpers emit typed observations.
- SQLite/SQLCipher event log stores private evidence.
- Rebuildable projections create world, time, behavior, and current-state memory.
- Query planner compiles the user's prompt into required evidence.
- Coverage gate blocks hallucination.
- Local or cloud text model phrases only the evidence packet.

That is the build. Anything else is a reactive assistant with a camera.
