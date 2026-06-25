# Trace Context Compiler Audit - 2026-06-23

> Status: POST-TRUST BACKLOG REFERENCE.
>
> This audit is useful for the eventual broader context engine. It is not the
> active sprint. The active product is "a memory for everything you READ" and the
> active gate is the n≈50 founder-gold reading evaluation using cross-frame OCR
> consensus. See `ops/CHIEF_DECISION_READING_FIRST_2026-06-23.md`.

## Chief Call

Trace is not an OCR/ASR wearable and it is not a chat UI with a camera. Trace is a
context compiler.

The product lives or dies on this loop:

1. Many narrow helpers observe the world, devices, people, places, apps, audio,
   transactions, and repeated behavior.
2. Helpers emit typed observations with provenance, confidence, time, entity
   anchors, spatial anchors, and refutation cues.
3. A binder converts observations into durable entities, relations, episodes,
   states, and behavioral patterns.
4. A query planner answers from that structured memory and refuses when the
   required helper coverage is absent.

The "Context -> Prompt -> Answer" shift means the prompt is mostly compiled
before the user asks. The user's question should not trigger a frantic search
through raw screenshots and captions. It should trigger a plan over already-built
facts: entities, attributes, locations, orders, preferences, transcripts, app
state, repeated routines, and contradictions.

If Trace keeps treating context as prose snippets, it collapses into worse RAG.
If Trace turns context into a durable evidence graph plus behavior ledger, the
paradigm is real.

## Repo Reality

The current repo is not empty. It already contains several organs of the right
product.

| Capability | Existing evidence | Product meaning | Current problem |
| --- | --- | --- | --- |
| Native live visual capture | `trace-native-fastvlm/FastVLM App/ContentView.swift` | Phone/glasses can observe stable scenes, OCR, objects, people, and push memory records. | Emits mixed prose records and side effects; not all helper outputs enter one durable contract. |
| Live speech path | `trace-native-fastvlm/FastVLM App/TraceLiveContextEngines.swift`, `scripts/build_asr.py` | Speech can become local transcript context. | Whisper live binary is optional/missing; Apple Speech fallback exists. Until patched, native transcript rows were not loaded by `ask_home` as ASR evidence. |
| Audio event helper | `scripts/build_audio_events.py` | Non-speech sound can be remembered without retaining raw audio. | Offline artifact, not generalized into live helper contract. |
| Screen/UI OCR | `scripts/screen_reader.py`, `scripts/capture_screen_live.py` | Screens can become context. | Mostly text OCR; no app-state model, UI hierarchy, active control, favorite markers, cart state, or interaction semantics. |
| Object/person detector | `trace_perception/worker.py`, `trace_perception/memory.py` | Cheap always-on object stream. | Emits `OBJECT | ...` prose; detector tracks are session-local, not durable identities. |
| Fixation/salience scheduler | `trace_perception/scheduler.py`, native enrichment comments in `ContentView.swift` | Attention depth should govern compute spend. | Currently visual-object only. It must become the global context budgeter across vision, audio, screen, place, commerce, and habits. |
| VLM enrichment ladder | `trace_perception/enricher.py` | Stable subjects can receive overview -> attributes -> minutiae passes. | Enrichment writes graph attributes, but the answer brain often bypasses the graph. |
| Entity-centric capture | `scripts/build_entity_capture.py` | Attributes are bound at capture while pixels still show who/what they belong to. | Good move, but offline and not the universal helper schema. |
| Cross-frame re-ID | `scripts/reid_entities.py` | Same real-world person/object can survive across frames. | Limited to visual appearance continuity. Needs cross-helper identity binding. |
| Entity graph | `scripts/entity_graph.py`, `trace_hub/graph.py` | Entities, attributes, relations, observations, encounters, messages. | There are two brains: `trace_hub` graph and `scripts/ask_home.py` sidecar recall. |
| World/inventory memory | `scripts/build_world_memory.py`, `scripts/walk_fuse_world.py` | Distinct physical objects can be counted once instead of per frame. | Offline; not robust live instance memory. |
| Attribute extraction | `scripts/build_attributes.py`, graph parser attributes in `trace_hub/graph.py` | Helper-specific attribute passes exist. | Hard-coded and uneven: backpack/laptop/cables are treated; arbitrary objects/states are not. |
| Temporal/count specialists | `scripts/temporal_specialist.py`, `scripts/counting_specialist.py` | Some mechanically recoverable answers avoid hallucination. | Benchmark-specific specialists; not a general query planner. |
| Evidence confidence | `scripts/evidence_confidence.py` | Channel reliability is already recognized. | Needs to be enforced as the universal answer gate. |
| Sleep binding | `scripts/build_sleep_bind.py` | Multi-helper nightly binding exists as a concept. | LLM JSON sleep pass is useful but cannot be the only binder. |
| Relationship imports | `trace_hub/importer.py`, `trace_hub/recall.py` | Messages/calendar can seed social context. | No commerce/order/favorites/restaurant/order-history helper exists. |
| Clean future architecture | `src/trace_memory/domain/observation.py`, `binding.py`, `adapters/sqlite_eventlog.py` | Append-only observation log and typed provenance are started. | Not yet the source of truth for live helpers or recall. |

The repo already knows the right direction. The mistake is treating those pieces
as separate patches instead of one context compiler.

## The Break

The current system has helper fragments, not a helper society.

The live app, graph, sidecar JSON files, sleep binders, and benchmark
specialists do not share one mandatory claim shape. Some outputs are JSON,
some are `OBJECT | ...` lines, some are cached sidecars, some are graph rows,
some are directly injected into `ask_home`. That means every new question class
requires custom glue.

That is why narrow fixes feel wrong: they are wrong. Better OCR or better ASR
alone cannot answer:

- "What's left to me?"
- "Which of these are duplicates?"
- "Where exactly did I put my keys?"
- "What is my usual order?"
- "Who said they would send the thing?"
- "Was that restaurant marked favorite in the app?"
- "Which bag was zipped?"
- "Which person was wearing the green shirt?"

Those require different helper classes and a binder that can compose them.

## Helper Classes We Actually Need

### 1. Perception Helpers

These turn local sensory or digital input into low-level observations.

Required helpers:

- OCR helper: visible text, text surface, bbox, reading confidence.
- ASR helper: transcript segment, language, speaker candidate, time span.
- Sound helper: non-speech sound class, onset/end, confidence.
- Object detector: object class, bbox, color, size/dominance, track id.
- VLM scene/action helper: activity, affordances, object states.
- Attribute helper: color, material, closure state, damage, brand, quantity,
  item-specific attributes.
- Face/person helper: visual person identity candidate, clothing, pose,
  accessories, active speaker cues.
- Hand/pose/ownership helper: held_by, worn_by, touched_by, put_down, picked_up.
- Spatial helper: egocentric left/right/front/back, rough distance, surface,
  containment, room/place anchor.
- Location/place helper: GPS, Wi-Fi/place hint, venue, room, visit episode.
- Screen/UI helper: app name, screen title, visible UI elements, active element,
  selected state, favorite markers, cart/order state.
- Transaction/order helper: receipts, bank/email/order history, restaurant,
  items, modifiers, price, time, source.
- Calendar/message/helper imports: commitments, social graph, planned events,
  repeated contacts.

### 2. Binding Helpers

These turn observations into durable facts.

Required helpers:

- Entity registry: persistent IDs for people, objects, places, apps, merchants,
  restaurants, menu items, documents, devices.
- Re-ID resolver: same physical object/person across frames, days, and helpers.
- Relation extractor: worn_by, held_by, inside, on, near, left_of, located_at,
  purchased_from, ordered_at, favorite_in_app, said_by.
- State tracker: open/closed, zipped/unzipped, connected/disconnected, selected,
  in-cart, delivered, consumed, left/right/current/absent.
- Episode segmenter: visits, conversations, screen sessions, meals, commutes,
  shopping sessions, object placement events.
- Behavior ledger: frequency, recency, usual choices, preferences, routines,
  deviations.
- Contradiction/refutation helper: last observation beats stale observation;
  conflicting helpers lower answerability.

### 3. Answer Helpers

These decide what evidence a question requires.

Required helpers:

- Query planner: maps user question to required fact types.
- Evidence resolver: fetches entities, relations, episodes, behavior patterns.
- Coverage gate: refuses if a required helper class never observed the needed
  context.
- Citation builder: cites typed evidence, not raw media.
- Confidence combiner: weights channel reliability and corroboration.

## Example Requirements

### "What's left to me?"

Required facts:

- Self/wearer pose or current viewpoint.
- Current nearby object instances.
- Egocentric relation: left/right/front/back/near/far.
- Latest timestamp and stale-state handling.
- Object identity and duplicate-safe instance count.

Existing pieces:

- Detector frame position in `trace_perception/worker.py`.
- Spatial word map hooks in `trace_hub/graph.py`.
- Object graph relations and attributes.
- Some world memory/inventory scripts.

Missing:

- Current-scene spatial graph with egocentric anchors.
- Durable instance IDs for duplicate objects.
- "Current" state semantics: present now vs last seen earlier.

### "Are these duplicate items?"

Required facts:

- Same-class instance segmentation.
- Appearance signature per item.
- Spatial separation and co-presence in the same episode.
- Cross-frame merge/split rules.

Existing pieces:

- `scripts/build_world_memory.py` tries to avoid recounting.
- `scripts/reid_entities.py` handles person/object identity continuity.
- `scripts/counting_specialist.py` clusters repeated signs/posters.

Missing:

- Live duplicate-aware instance registry.
- Co-present count vs repeated sighting count as first-class fields.
- General item fingerprinting, not only persons/signs/posters.

### "What is my usual order?"

Required facts:

- Merchant/restaurant entity.
- Order event schema: item, modifiers, quantity, price, timestamp, source.
- Visit/order history over days or weeks.
- UI state: favorite restaurant, saved item, reordered item, cart state.
- Behavior aggregation: frequency, recency, confidence, tie-breaking.

Existing pieces:

- Message/calendar import architecture exists in `trace_hub/importer.py`.
- Screen OCR exists.
- Graph can store people/messages/events/attributes.

Missing:

- Commerce/order importer.
- Receipt/email/transaction helper.
- Food delivery/restaurant UI parser.
- Menu item normalization.
- Preference/frequency ledger.

Verdict: today Trace cannot honestly answer this except by faking the needed
helper outputs. For a pitch, fake those outputs. For product, build the helper.

### "Who said X?"

Required facts:

- ASR segment text.
- Speaker diarization or active speaker visual cue.
- Person/entity identity.
- Time-aligned face/person observation.

Existing pieces:

- Native speech transcript and offline ASR.
- Person/face visual enrichment.
- Entity graph and relationship imports.

Missing:

- Speaker identity binding.
- Active speaker relation: `speech_segment said_by person_id`.
- Conversation episode model.

### "Which bag was zipped?"

Required facts:

- Bag instances, not just bag class.
- Closure state attribute per instance.
- Same-frame relation between visual attribute and object.
- Confidence/refusal if zipper state not visible.

Existing pieces:

- `scripts/build_attributes.py` has bag zipper/attribute prompt.
- `scripts/build_entity_capture.py` preserves object-bound text and person-bound attributes.

Missing:

- General object-state helper.
- Instance-bound state ledger.
- Current/stale state conflict handling.

## Architectural Decision

We stop making one-off specialists the center of the product.

The new center is:

```text
helper output -> append-only observation log -> binder -> evidence graph + behavior ledger -> query planner -> grounded answer/refusal
```

The observation contract must be mandatory:

```json
{
  "observation_id": "uuid",
  "helper_id": "screen.ui.v1",
  "source_channel": "screen",
  "captured_at_ms": 123456,
  "valid_for_ms": 5000,
  "subject": {
    "candidate_id": "entity-or-track-id",
    "kind": "restaurant|object|person|screen|speech_segment|order|place",
    "label": "Garden Wok"
  },
  "predicate": "favorite_in_app|ordered_item|left_of_self|held_by|contains_text|state",
  "object": {
    "kind": "text|entity|value",
    "value": "Chicken bowl, spicy, no onions"
  },
  "attributes": {
    "bbox": null,
    "spatial_anchor": "left of wearer",
    "app": "Uber Eats",
    "merchant": "Garden Wok",
    "confidence_reason": "visible UI favorite marker"
  },
  "confidence": 0.86,
  "evidence": {
    "snippet": "Favorite; reorder Chicken bowl",
    "raw_retained": false
  },
  "refutation_cues": [
    "same merchant later un-favorited",
    "newer order contradicts usual item"
  ]
}
```

This is not optional plumbing. It is the product.

## The Product Surface

The pitch-ready prototype must show Trace answering across context classes:

1. Physical present: "What is left of me?" and "how many duplicate mugs are on
   the desk?"
2. Physical memory: "Where did I last put the keys?"
3. Speech/social: "Who said they would send the notes?"
4. Screen/UI: "Which chat was open?" and "was the restaurant favorite?"
5. Behavior: "What is my usual order from this restaurant?"

If the prototype only answers visual/OCR questions, it is not the product.

## Diagnostic Gauntlet

These are the questions we must answer for every helper before calling it real:

1. What exact raw signal does the helper observe?
2. Does it run live, in sleep pass, or via import?
3. What is the maximum acceptable latency?
4. Does raw media ever persist? If yes, where and for how long?
5. What exact typed observations does it emit?
6. Which entity IDs can it attach to?
7. What is its confidence calibration?
8. What refutation cues can invalidate its claim later?
9. Which query classes does it unlock?
10. Which query classes does it not unlock, even if it looks relevant?
11. What other helper must corroborate it before an answer is allowed?
12. How does it handle duplicates of the same class?
13. How does it handle stale observations?
14. How does it expose "I saw absence" vs "I did not look"?
15. What test fixture proves it refuses when coverage is missing?

Hard questions for the current project:

1. Is `src/trace_memory/adapters/sqlite_eventlog.py` going to become the source
   of truth, or is `trace_hub/graph.py`? We cannot keep both as primary brains.
2. Which existing sidecar artifacts remain projections, not source of truth:
   `kf_memory.json`, `screen_memory.json`, `asr.json`, `world_memory.json`,
   `entity_centric.json`, `attributes.json`, `sleep_bind.json`?
3. What are the first 30 canonical user questions, and which helper classes
   are required for each?
4. What helper do we build first that proves the product is bigger than VLM:
   commerce/order, UI-state, speaker identity, or current spatial graph?
5. What do we fake in the pitch, and what do we explicitly label as simulated
   helper output internally?

## Marching Orders

### Today

1. Freeze the product definition: Trace is a context compiler.
2. Create a coverage matrix with at least 30 questions and required helper
   classes. A query is not "supported" unless every required helper exists or
   the pitch fixture simulates it.
3. Create the helper observation contract and force every new helper to emit it.
4. Pick three pitch scenarios:
   - physical desk/current scene,
   - speech/person conversation,
   - restaurant/order preference.
5. Build the pitch fixture by injecting typed helper observations. Do not fake
   raw sensors first. Fake the helper outputs, because that is the system we
   need to prove.

### This Week

1. Promote `src/trace_memory` append-only observations or `trace_hub` graph as
   the single source of truth. My call: use the append-only log as truth and
   make `trace_hub` graph a projection until proven otherwise.
2. Write the binder that turns observations into:
   - entities,
   - relations,
   - episodes,
   - current states,
   - behavior aggregates.
3. Replace answer-specialist routing with query-planner routing:
   question -> required fact types -> evidence fetch -> coverage gate -> answer.
4. Add a commerce/order helper simulator. This is non-negotiable because it
   proves the paradigm is not just VLM.
5. Add an app/UI semantic helper simulator over screen text/state.
6. Add a current-scene spatial graph simulator over physical observations.

### Pitch Illusion

The pitch illusion should be honest internally and magical externally.

We should fake:

- order history ingestion,
- restaurant favorite UI state,
- active speaker binding,
- duplicate physical object instance IDs,
- egocentric spatial current-scene relations.

We should not fake:

- the answer being grounded in typed evidence,
- refusal when evidence is missing,
- cross-reference between helpers.

Pitch line:

> Trace does not wait for you to ask and then scramble for context. It quietly
> compiles your world into private, typed memory: what was seen, heard, touched,
> ordered, favorited, repeated, and contradicted. When you ask, the answer is
> already mostly built.

## Viability Verdict

Viable, but only if we stop optimizing the wrong layer.

Competitors fail because they are prompt-first assistants: the user asks, the
device hunts context, then a model improvises. That breaks on latency, privacy,
hallucination, and shallow memory.

Trace can win because context-first turns life into evidence before the ask.
But it only wins if context means structured, cross-helper, durable facts. If
context means "more captions in a prompt," nuke it.

My stand: proceed, but the next milestone is not a better demo answer. The next
milestone is the helper contract plus coverage matrix plus three cross-domain
pitch fixtures.
