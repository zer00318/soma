# Context Engine Phase 1 Parameter Matrix - 2026-06-23

> SUPERSEDED HEADER (2026-06-23 PM): the "reading-first / not permission to
> broaden" note below was written before the founder's full-architecture sanction
> (total sovereignty, build the whole `Context -> Prompt -> Answer` paradigm). The
> matrix is now an ACTIVE parameter map for the full multi-modal engine, not a
> deferred checklist. The architecture is completed in
> `ops/CONTEXT_ENGINE_PHASE2B_INJECTION_LAYER_2026-06-23.md` (the injection layer +
> standing-ground contract) and built per `ops/CONTEXT_SPRINT_2026-06-23.md`.
> The honesty gate still governs every row. Original note retained below for history:
>
> Status: REFERENCE CHECKLIST ONLY.
>
> This matrix describes the eventual context-engine problem space. It is not
> permission to broaden the current product. The active scope is reading-first:
> prove cross-frame OCR consensus on n≈50 founder-gold reading questions with
> lies near zero. See `ops/CHIEF_DECISION_READING_FIRST_2026-06-23.md`.

## Chief Position

The product is a continuous context engine. It does not begin at the user prompt.
It begins at the physical fact that the world is producing more signal than a
wearable can sense, process, store, or explain.

Therefore Phase 1 is not "what helpers do we build?" It is the universal
constraint map: what must be true for any current-technology system to
continuously convert lived reality into queryable private memory without
melting, hallucinating, spying, drowning in data, or lying.

This document intentionally does not choose a vendor stack. It defines the
parameters that any stack must satisfy.

## Bedrock Model

The engine has five irreversible boundaries:

1. Capture boundary: raw physical/digital signal enters.
2. Attention boundary: the system decides what deserves compute now.
3. Compression boundary: signal becomes typed, provenance-bearing observations.
4. Binding boundary: observations become entities, states, relations, episodes,
   routines, and contradictions.
5. Recall boundary: a user prompt becomes a plan over existing context, not a
   scramble for context.

The north-star invariant:

> Context must be useful before the prompt exists.

The non-negotiable technical invariant:

> Raw signal is not the memory. Typed evidence is the memory.

## Evaluation Framework

Every architecture must be scored on these axes.

| Axis | Meaning | Hard question |
| --- | --- | --- |
| Coverage | What classes of reality can the engine understand? | Which questions are impossible because no sensor/helper observed the required fact? |
| Grounding | Can each answer cite typed evidence? | What exact observation supports each claim? |
| Freshness | Does memory represent now vs earlier? | Is this fact current, stale, contradicted, or unknown? |
| Persistence | Does identity survive across time? | Is this the same object/person/place/order as before? |
| Power | Can it run continuously? | What is the hourly energy cost per always-on mode? |
| Thermal | Can it stay comfortable and performant? | What happens after 30 minutes in pocket/body heat? |
| Latency | Is context available before the ask? | Which facts are live, delayed, or sleep-pass only? |
| Privacy | Is raw life retained or exported? | What leaves device, and why is it safe? |
| Refusal | Does it know when it lacks evidence? | Can it explain the missing context class? |
| Repairability | Can errors be corrected? | How does a wrong binding get overturned later? |
| Extensibility | Can new helpers join cleanly? | Can a new source emit the same observation contract? |
| Pitchability | Can the illusion be shown today? | Which helper outputs can be simulated honestly? |

## A-to-Z Universal Parameter Matrix

### A. Acquisition Physics

| ID | Parameter | Why it matters | Failure mode | Required measurement/question |
| --- | --- | --- | --- | --- |
| A1 | Sensor placement | The world visible to a chest pin, glasses, phone, watch, and earbuds is different. | The engine confidently misses the relevant fact because it never had line-of-sight or audio access. | What percentage of target questions require eyes, ears, screen, location, transaction, or import data? |
| A2 | Field of view | Context-first dies if the relevant object sits outside view. | "What is left of me?" is unanswerable despite active camera. | What FOV and body orientation are needed for current-scene spatial memory? |
| A3 | Frame cadence | More frames improve recall but multiply power, heat, and privacy risk. | Either motion events are missed or the device overheats. | What is the minimum adaptive frame schedule per state: idle, walking, fixation, interaction? |
| A4 | Audio capture cadence | Speech, sound events, and intent cues need different windows. | Missed short utterances or continuous battery drain. | What is the minimum local audio buffer needed for ASR and sound-event detection without raw retention? |
| A5 | Screen/digital capture | Much user life happens on screens, not in camera view. | The engine knows the room but not the task. | Which OS-level APIs or user-authorized connectors can expose app state, notifications, and UI semantics? |
| A6 | Environmental metadata | GPS, Wi-Fi, Bluetooth, time, calendar, and motion disambiguate context. | A sign is read but not grounded to a place or episode. | Which passive metadata is high value per watt and per privacy cost? |

### B. Bandwidth And Backpressure

| ID | Parameter | Why it matters | Failure mode | Required measurement/question |
| --- | --- | --- | --- | --- |
| B1 | Raw ingress rate | Continuous video/audio creates far more data than can be stored or processed. | Queues explode; latency becomes infinite. | What are the peak and sustained bytes/sec per sensor mode? |
| B2 | Compute queue depth | Even local models become useless if tasks pile up. | Context arrives after the prompt, breaking the paradigm. | What max queue age is allowed for live facts? |
| B3 | Drop policy | A continuous engine must decide what to ignore. | It drops the only answer-bearing moment or stores everything. | What signals make data droppable, resumable, or urgent? |
| B4 | Priority inversion | Cheap tasks can starve expensive answer-critical tasks. | OCR backlog blocks speaker binding or order-state extraction. | What scheduler guarantees attention to high-information events? |
| B5 | Network availability | Cloud fallback cannot be assumed. | Device works only on perfect connectivity. | Which functions are fully offline, opportunistic cloud, or never cloud? |

### C. Continuous Attention

| ID | Parameter | Why it matters | Failure mode | Required measurement/question |
| --- | --- | --- | --- | --- |
| C1 | Salience detection | Continuous capture needs a reason to spend compute. | It processes every passerby and ignores the object the user cares about. | What signals imply attention: dwell, hand interaction, gaze, speech reference, app focus, repeated exposure? |
| C2 | Novelty detection | Familiar scenes can run cheap; new scenes deserve deeper passes. | The system wastes power re-describing the same desk. | How is scene/entity familiarity represented and aged? |
| C3 | Fixation vs incidental exposure | Seeing is not always caring. | A billboard dominates memory because it was visually large. | How do dwell, interaction, and recurrence change confidence and priority? |
| C4 | Interruption handling | Real life shifts quickly. | Long model pass blocks capture of a new important event. | What tasks are cancellable, resumable, or bounded by hard timeout? |
| C5 | Attention budget accounting | Every helper competes for battery and heat. | Helpers individually seem cheap but collectively melt the device. | What is the per-hour budget by context class? |

### D. Data Minimization

| ID | Parameter | Why it matters | Failure mode | Required measurement/question |
| --- | --- | --- | --- | --- |
| D1 | Raw retention policy | Raw life data is the largest privacy and trust risk. | Product becomes surveillance storage. | Which raw buffers exist, for how many seconds, and who can access them? |
| D2 | Evidence granularity | Too little evidence cannot ground answers; too much leaks life. | Answers are either unsupported or privacy-invasive. | What is the minimal citation unit: text snippet, entity relation, timestamp, encrypted excerpt? |
| D3 | Local-only transforms | Sensitive context should become typed facts before any egress. | Cloud sees raw images/audio/screens. | Which transforms must run on-device even if slower? |
| D4 | Forgetting | Continuous systems need deletion as much as memory. | Stale or sensitive facts persist forever. | What expires by default, what persists by value, and what requires user consent? |
| D5 | Redaction | Some facts are useful only after stripping names, faces, or secrets. | Useful memory becomes unsafe to search or show. | What redaction occurs before indexing, display, and cloud calls? |

### E. Entity Continuity

| ID | Parameter | Why it matters | Failure mode | Required measurement/question |
| --- | --- | --- | --- | --- |
| E1 | Persistent IDs | Questions target things across time. | The same mug becomes ten mugs; ten mugs become one mug. | What identity evidence merges or splits entities? |
| E2 | Cross-modal identity | People, places, restaurants, and objects appear through multiple channels. | "Alex" in speech is not bound to the visible person or contact. | How do ASR, face, messages, calendar, screen, and location converge? |
| E3 | Instance discrimination | Duplicate objects are common. | The engine cannot answer counts, leftovers, or placement. | What visual/spatial/temporal fingerprint separates same-class instances? |
| E4 | Identity uncertainty | Sometimes identity is plausible but not certain. | A guess becomes permanent memory. | How are candidate IDs, confidence, and ambiguity stored? |
| E5 | Identity repair | Wrong merges happen. | One bad binding poisons long-term memory. | How can later evidence split or correct entities? |

### F. Fact Shape

| ID | Parameter | Why it matters | Failure mode | Required measurement/question |
| --- | --- | --- | --- | --- |
| F1 | Observation contract | Helpers must speak a common language. | Every new helper needs custom glue. | What fields are mandatory for every emitted observation? |
| F2 | Predicate vocabulary | Open-vocabulary facts are flexible but hard to reason over. | Queries cannot reliably retrieve required evidence. | Which predicates are canonical vs freeform? |
| F3 | Attribute semantics | Attributes need units, confidence, and scope. | "Left", "favorite", "usual", and "connected" mean inconsistent things. | What attribute types require normalized value schemas? |
| F4 | Negative evidence | Not seeing a thing is different from seeing absence. | The engine says "not there" when it simply did not look. | How does a helper emit checked_absent vs unknown? |
| F5 | Contradiction cues | Living context changes. | Stale facts win over newer evidence. | What newer observations invalidate older facts? |

### G. Grounding And Truth

| ID | Parameter | Why it matters | Failure mode | Required measurement/question |
| --- | --- | --- | --- | --- |
| G1 | Provenance | Every answer needs a trail. | The model sounds right but cannot be audited. | What exact evidence object backs each answer clause? |
| G2 | Confidence calibration | Different helpers have different reliability. | Caption guesses outweigh OCR or transaction records. | What reliability prior exists per helper and per predicate? |
| G3 | Corroboration | Cross-helper agreement is stronger than one weak read. | A single hallucinated VLM caption becomes truth. | Which facts require corroboration before answer? |
| G4 | Refusal mechanics | Honest refusal is a feature. | The engine improvises when coverage is missing. | Can refusal cite missing helper classes and missing time windows? |
| G5 | Eval gold | Without question-level gold, progress is theater. | Demo improvement hides hallucination. | What fixed datasets measure answerability, grounding, and refusal? |

### H. Hardware Envelope

| ID | Parameter | Why it matters | Failure mode | Required measurement/question |
| --- | --- | --- | --- | --- |
| H1 | Battery budget | Always-on context competes with normal device use. | Prototype lasts 40 minutes. | What is the watt-hour budget per day and per active hour? |
| H2 | Thermal budget | Wearables touch the body. | Device throttles or becomes uncomfortable. | What sustained skin/device temperature is acceptable? |
| H3 | Memory pressure | Local models and queues consume RAM. | OS kills the process. | What is peak RAM by mode and model combination? |
| H4 | Storage budget | Typed memory can still grow unbounded. | Disk fills or search slows. | What is bytes/hour after minimization and projection? |
| H5 | Sensor package | Glasses, pendant, phone, watch, and earbuds support different modalities. | Architecture assumes sensors the product cannot ship. | What is the minimum viable hardware constellation? |
| H6 | Connectivity hardware | Local/off-device split depends on Wi-Fi, UWB, Bluetooth, cable, and phone link. | Helper latency spikes when link degrades. | What work runs on wearable, phone, laptop, home hub, or cloud? |

### I. Indexing And Retrieval

| ID | Parameter | Why it matters | Failure mode | Required measurement/question |
| --- | --- | --- | --- | --- |
| I1 | Append-only event log | Replayable truth prevents silent corruption. | Derived stores become inconsistent. | What is the immutable source of truth? |
| I2 | Graph projection | Entities and relations need structured retrieval. | "Where is X?" becomes text search. | What graph schema supports state, time, place, and evidence? |
| I3 | Temporal index | Living memory is time-shaped. | "last", "usual", "during", and "before" fail. | How are intervals, episodes, recency, and duration indexed? |
| I4 | Vector index | Semantic recall helps open-ended queries. | Exact schemas miss fuzzy intent. | Which text is embedded, how often, and with what privacy boundary? |
| I5 | Behavior index | "Usual" is not a single event. | Preference questions cannot be answered. | How are frequency, recency, routine, and deviation computed? |
| I6 | Current-state index | "Now" needs special handling. | The system answers from yesterday. | What facts are current, stale, expired, or superseded? |

### J. Joint Reasoning

| ID | Parameter | Why it matters | Failure mode | Required measurement/question |
| --- | --- | --- | --- | --- |
| J1 | Query decomposition | Prompt is not the context; it is a request over context. | A model scans everything and guesses. | How is a query mapped to required fact types? |
| J2 | Cross-source joins | Real questions span helpers. | "Usual order" cannot combine UI favorites, orders, visits, and recency. | What join keys exist: entity_id, place_id, time interval, app_id, merchant_id? |
| J3 | Causal restraint | The engine must distinguish observed facts from inferred reasons. | "Why" answers become fiction. | What inference levels are allowed: observed, correlated, inferred, speculative? |
| J4 | State composition | Answering requires current plus history plus contradiction. | The model sees facts but not their lifecycle. | How are state transitions represented? |
| J5 | Multi-step citation | Composite answers need multiple evidence nodes. | A behavior claim cites one arbitrary moment. | How does an answer cite aggregate evidence? |

### K. Knowledge Boundaries

| ID | Parameter | Why it matters | Failure mode | Required measurement/question |
| --- | --- | --- | --- | --- |
| K1 | Personal vs world knowledge | The engine should not confuse public facts with private memory. | It answers "usual order" from stereotypes. | Which answers require personal evidence only? |
| K2 | Ontology scope | Too rigid blocks new facts; too loose breaks reasoning. | Helpers emit incompatible labels. | What ontology is stable, and where is freeform allowed? |
| K3 | User correction | The user may teach or correct memory. | Wrong facts persist after correction. | How are corrections represented as high-authority observations? |
| K4 | External connectors | Email, banking, maps, delivery apps, calendars expand context. | Product over-relies on camera/audio. | Which connectors are essential vs optional? |

### L. Latency Classes

| ID | Parameter | Why it matters | Failure mode | Required measurement/question |
| --- | --- | --- | --- | --- |
| L1 | Reflex latency | Some facts must be ready in seconds. | "What is left of me?" is stale. | Which questions require sub-1s, sub-5s, sub-60s, or sleep-pass context? |
| L2 | Sleep-pass latency | Deep binding can happen later. | Expensive insights block live capture. | Which facts are okay to become available overnight? |
| L3 | Ask-time latency | The user expects immediate recall. | Context-first feels like normal chat. | What max time-to-first-answer is acceptable? |
| L4 | Correction latency | New evidence should overturn old state quickly. | The engine answers from stale state after an object moves. | How quickly do state projections update? |

### M. Model Strategy

| ID | Parameter | Why it matters | Failure mode | Required measurement/question |
| --- | --- | --- | --- | --- |
| M1 | Model placement | On-device, phone, hub, and cloud each have tradeoffs. | Privacy, power, or latency breaks. | Which model class runs where? |
| M2 | Model size ladder | Continuous systems need cheap and expensive passes. | Everything uses the biggest model. | What tiny classifiers gate bigger VLM/LLM calls? |
| M3 | Deterministic extractors | Not every fact should rely on generative output. | Counts, times, and state become unstable. | Which facts are extracted mechanically vs by model? |
| M4 | Model drift | Upgrading models changes memory behavior. | Old and new observations are not comparable. | Is helper version stored with every observation? |
| M5 | Prompt compilation | Prompt should be generated from evidence, not raw memory. | Ask-time prompt becomes too big and lossy. | What is the maximum evidence packet size per answer? |

### N. Normalization

| ID | Parameter | Why it matters | Failure mode | Required measurement/question |
| --- | --- | --- | --- | --- |
| N1 | Time normalization | All modalities must align. | Speech and image events cannot bind. | What clock source and drift correction are used? |
| N2 | Place normalization | Restaurants, rooms, GPS points, and addresses need one place identity. | "Here" and "Garden Wok" never join. | How are place aliases and confidence represented? |
| N3 | Item normalization | Orders and products have variants. | "Chicken bowl spicy" and "spicy chicken bowl" are separate habits. | How are menu items, modifiers, and brands canonicalized? |
| N4 | Person normalization | Contacts, faces, voices, and names are noisy. | One person becomes several or vice versa. | What is the identity merge policy for people? |
| N5 | Unit normalization | Distances, amounts, dates, durations, quantities need units. | Aggregation fails silently. | What units are required per predicate? |

### O. Operating Modes

| ID | Parameter | Why it matters | Failure mode | Required measurement/question |
| --- | --- | --- | --- | --- |
| O1 | Idle mode | Most life is not answer-worthy. | Battery dies watching nothing. | What sensors stay active when nothing salient is happening? |
| O2 | Active interaction mode | Hand/speech/screen interactions are high-value. | The engine misses the moments people ask about later. | What triggers high-capture mode? |
| O3 | Private mode | Users need immediate control. | Trust dies. | What does pause, mute, blackout, and forget do at every layer? |
| O4 | Low-power mode | The engine must degrade gracefully. | All context disappears under low battery. | Which helpers survive low power? |
| O5 | Offline mode | The product cannot require cloud. | Real-world use fails. | What answers remain supported offline? |

### P. Privacy, Policy, And Permission

| ID | Parameter | Why it matters | Failure mode | Required measurement/question |
| --- | --- | --- | --- | --- |
| P1 | Consent surface | Ambient capture affects bystanders. | Social and legal rejection. | What visible indicators, zones, and consent policies exist? |
| P2 | Sensitive categories | Some facts should be restricted or never inferred. | The product becomes creepy or unsafe. | Which categories are blocked, opt-in, or local-only? |
| P3 | App permissions | Screen, mic, location, messages, email, and banking are gated. | Architecture assumes unavailable access. | What is the minimum permission set for pitch vs product? |
| P4 | Auditability | Users must know what was remembered. | Memory feels uncontrollable. | How can the user inspect and delete evidence? |
| P5 | Egress control | Cloud calls must be bounded. | Private context leaks. | What exact payload types can leave device? |

### Q. Quality Measurement

| ID | Parameter | Why it matters | Failure mode | Required measurement/question |
| --- | --- | --- | --- | --- |
| Q1 | Answerability gap | Measures what the system should know but does not. | We celebrate easy questions. | How many oracle-answerable questions are missed? |
| Q2 | Hallucination rate | False answers are worse than refusals. | Trust collapses. | What percentage of unsupported questions get answered? |
| Q3 | Binding accuracy | Most hard failures are wrong referent, not missing token. | Correct text is attached to wrong person/object. | How often does who/what/where binding fail? |
| Q4 | Freshness accuracy | Current context is special. | "Now" answers from stale facts. | How often does latest-state retrieval choose correctly? |
| Q5 | Energy per useful fact | Context must justify power. | The system burns watts for junk memory. | What useful grounded observations are produced per watt-hour? |

### R. Real-Time State

| ID | Parameter | Why it matters | Failure mode | Required measurement/question |
| --- | --- | --- | --- | --- |
| R1 | State lifecycle | Facts change. | "Door open" remains true after closing. | What predicates are stateful vs timeless? |
| R2 | Current scene memory | Some answers depend on immediate surroundings. | The engine cannot answer situated questions. | What in-memory projection represents the last N seconds? |
| R3 | Long-term memory | Patterns require weeks/months. | "Usual" is impossible. | What aggregate stores survive raw deletion? |
| R4 | Conflict resolution | Helpers disagree. | The most recent or loudest helper wins incorrectly. | How are conflicts scored and exposed? |
| R5 | State invalidation | New evidence should close old states. | Object placement remains current after removal. | Which predicates have automatic invalidators? |

### S. Safety And Social Acceptability

| ID | Parameter | Why it matters | Failure mode | Required measurement/question |
| --- | --- | --- | --- | --- |
| S1 | Bystander safety | Ambient perception is socially sensitive. | Product is rejected before technical merit matters. | What is not captured, not stored, or not answerable about bystanders? |
| S2 | User dependence | Memory assistance can mislead decisions. | User acts on false context. | Which answer classes require high confidence or explicit uncertainty? |
| S3 | Abuse resistance | The system could be used to surveil others. | Product becomes harmful. | What policies and technical gates prevent misuse? |
| S4 | Failure transparency | Users need to understand limits. | Mistakes feel like betrayal. | How does the product explain missing or uncertain context plainly? |

### T. Temporal Semantics

| ID | Parameter | Why it matters | Failure mode | Required measurement/question |
| --- | --- | --- | --- | --- |
| T1 | Event segmentation | Life is not a stream of frames. | Queries cannot target "during lunch" or "after class". | What creates an episode boundary? |
| T2 | Duration estimation | Dwell and routines need time. | "How long" answers are fake. | What is observed duration vs inferred attention duration? |
| T3 | Recency weighting | Recent behavior often matters more. | "Usual" overweights ancient habits. | What decay curve applies per behavior type? |
| T4 | Seasonality | Habits vary by day/time/place. | Breakfast order and dinner order get mixed. | How are context-conditioned routines represented? |
| T5 | Temporal uncertainty | Timestamps can be approximate or imported. | Joins are overconfident. | How is time confidence stored? |

### U. User Model

| ID | Parameter | Why it matters | Failure mode | Required measurement/question |
| --- | --- | --- | --- | --- |
| U1 | Personal preferences | "Usual" and "favorite" are user-specific. | Product answers from generic assumptions. | What observed evidence creates a preference? |
| U2 | Intent signals | Users often ask why or what they were doing. | The engine only knows objects. | What speech, screen, calendar, and action signals imply intent? |
| U3 | Memory correction | The user knows when the system is wrong. | Errors cannot be repaired. | How does feedback update observations, entities, and aggregates? |
| U4 | Privacy preferences | Different users want different retention. | One policy fits nobody. | What knobs exist without making setup impossible? |

### V. Versioning And Replay

| ID | Parameter | Why it matters | Failure mode | Required measurement/question |
| --- | --- | --- | --- | --- |
| V1 | Helper versioning | Observation meaning depends on extractor version. | Replays and audits cannot explain differences. | Is helper_id and model/version mandatory? |
| V2 | Schema migration | Memory must survive product evolution. | Old facts become unreadable. | How are observations migrated or projected forward? |
| V3 | Deterministic replay | Bugs require reconstructing projections. | State corruption is unfixable. | Can the graph and indexes rebuild from the event log? |
| V4 | Experiment isolation | Prototype hacks should not poison core memory. | Pitch fixtures corrupt product data. | How are simulated observations labeled and isolated? |

### W. World Modeling

| ID | Parameter | Why it matters | Failure mode | Required measurement/question |
| --- | --- | --- | --- | --- |
| W1 | Spatial frames | Left/right/front/back depend on coordinate frame. | "Left of me" means camera-left, body-left, map-left, or screen-left inconsistently. | What coordinate frames are represented? |
| W2 | Containment | Bags, rooms, carts, and apps contain things. | "What's in my bag/cart?" fails. | How are inside/on/attached/held relations tracked? |
| W3 | Affordance and action | Objects matter because of use. | The engine knows "cup" but not "drinking coffee". | Which actions are observable and useful? |
| W4 | Place-memory binding | Objects and routines are place-conditioned. | Desk objects mix with restaurant objects. | How are facts scoped to place and episode? |
| W5 | Digital-world modeling | Apps and screens are worlds too. | UI state is treated as OCR text only. | What entities exist for app, screen, tab, thread, cart, button, favorite marker? |

### X. Cross-Device Architecture

| ID | Parameter | Why it matters | Failure mode | Required measurement/question |
| --- | --- | --- | --- | --- |
| X1 | Wearable role | Wearable may be sensor, not brain. | Device tries to run too much. | What is the minimal useful compute on wearable? |
| X2 | Phone role | Phone is a practical hub. | Latency and permissions are mishandled. | Which helpers run on phone continuously? |
| X3 | Home/laptop hub role | Larger models may run nearby. | Product depends on nonportable compute. | Which sleep-pass or heavy jobs can wait for hub availability? |
| X4 | Cloud role | Cloud can help but cannot be trusted with raw life. | Privacy and latency break. | What text-only, provenance-bearing payloads are cloud-eligible? |
| X5 | Sync protocol | Multiple devices see different parts of life. | Memory fragments across devices. | How are event logs merged, encrypted, and deduplicated? |

### Y. Yield Management

| ID | Parameter | Why it matters | Failure mode | Required measurement/question |
| --- | --- | --- | --- | --- |
| Y1 | Useful-fact yield | Most observations are junk. | Memory becomes noisy and expensive. | What fraction of emitted observations answer future questions? |
| Y2 | Helper ROI | Some helpers cost more than they unlock. | Product complexity grows without capability. | What question classes does each helper enable per watt and per engineering week? |
| Y3 | Pitch yield | Prototype must show paradigm, not breadth theater. | Demo looks like many weak features. | Which three cross-domain scenarios prove context-first? |
| Y4 | Learning loop | Usage should reveal missing helpers. | Roadmap is guesswork. | What unanswered questions become helper requirements? |

### Z. Zero-Trust Answering

| ID | Parameter | Why it matters | Failure mode | Required measurement/question |
| --- | --- | --- | --- | --- |
| Z1 | Evidence-first generation | The LLM should phrase, not invent. | Beautiful unsupported answers. | Does every generated sentence map to evidence? |
| Z2 | Missing-context proof | Refusal needs structure, not apology. | User cannot tell whether product failed or never observed. | Does every refusal name missing helper classes? |
| Z3 | Aggregate proof | Behavior answers require many facts. | "Usual order" cites one order. | What support threshold makes an aggregate answerable? |
| Z4 | Anti-hallucination gate | The answer model must be downstream of evidence checks. | Prompt pressure overrides truth. | Can the model answer only from a locked evidence packet? |
| Z5 | User trust loop | The system must admit uncertainty naturally. | Users stop relying on it. | What answer format communicates confidence without becoming legalese? |

## Core Paradoxes To Resolve In Phase 2

1. Always-on vs battery: the engine must feel continuous while most expensive
   helpers are asleep most of the time.
2. Rich memory vs privacy: the product must remember meaning, not raw life.
3. Flexibility vs schema: helpers need open-world perception but answer logic
   needs typed facts.
4. Local intelligence vs model quality: the most private place to process is not
   always the most capable place.
5. Freshness vs durability: current facts expire; behavioral facts accumulate.
6. Seeing vs caring: exposure is not attention, but attention is rarely directly
   measured.
7. Entity merge vs split: over-merging and under-merging both break real memory.
8. Helpful inference vs hallucination: the product must infer enough to be useful
   while labeling inference level.
9. Pitch magic vs engineering truth: we can simulate helper outputs, but the
   composition layer must be real.

## Phase 1 Output Verdict

The architecture cannot be designed as "camera plus LLM." It must be designed as
an operating system for continuous private context:

```text
sensor/import stream
  -> adaptive attention scheduler
  -> local typed observation emitters
  -> append-only encrypted event log
  -> deterministic and model-assisted binders
  -> graph/current-state/temporal/behavior projections
  -> query planner with coverage gate
  -> evidence-locked answer generator
```

Phase 2 must research current commercially available ways to instantiate each
row above, but no implementation choice is allowed to bypass the matrix.
