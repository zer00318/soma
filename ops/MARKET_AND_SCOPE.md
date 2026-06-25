# Trace - Market and Scope

Corrected: 2026-06-22

This is a decision document, not market proof. It separates the target product from the
current executable and separates direct competitors from products that merely share a
sensor, form factor, model, or marketing word.

## Product Under Evaluation

The defensible Trace hypothesis is:

> A wearable can observe vision and audio continuously or attention-selectively, convert
> raw signals into useful structured events before raw media leaves volatile memory, keep
> the derived memory under the user's local control, and later answer open retrospective
> questions with claim-level evidence or refusal.

The conjunction matters. Remove vision and the product becomes an audio notetaker. Retain
video and it becomes a lifelogging camera. Remove durable memory and it becomes an in-the-
moment assistant. Remove interaction and it becomes a passive diary. Send the memory to a
vendor cloud and it becomes a different trust product.

The current executable does not yet satisfy this definition. It contains a raw MOV writer,
stores plaintext derived data, drops provenance at Mac ingest, exposes an unauthenticated
LAN API, and enables frontier fallback from the iOS Ask path.

## Competitive Taxonomy

### Direct thesis competitor

**Brilliant Labs Halo** is in the same conceptual realm. Brilliant says Halo can see and
hear what the wearer does, provides long-term memory and dialogue, and does not retain raw
audio or video beyond immediate processing. Brilliant also describes Noa as a cloud-based
AI agent and says encoded memories can live on encrypted servers. Halo therefore attacks
the same user job with a different persistence boundary.

Halo invalidates the broad claims "nobody is doing visual autobiographical memory" and
"nobody combines visual memory with raw-media non-retention." It does not invalidate the
narrower hypothesis that no proven product combines those properties with local durable
memory, grounded open recall, and a verifiable no-egress boundary.

### Modality competitor, not visual substitute

**Amazon Bee** captures conversations, creates transcripts and summaries, and derives
longitudinal insights while Amazon says no audio is stored. It is relevant evidence that
ambient memory and non-retention are real product positions. It is not a visual-memory
competitor: it cannot preserve objects, scenes, visible text, gestures, clothing, spatial
relations, or the visual identity of a speaker.

Trace's conceptual advantage over audio-only memory is legitimate. Synchronized vision
can bind speech to visible people and physical context. The current code does not implement
that advantage: it stores generic nearby-speech transcripts separately from visual records
and has no active-speaker detection, AV clock alignment, or speaker-binding evaluation.

### Hardware and attention competitors

**Ray-Ban Meta Gen 2** combines glasses, camera, microphone, media capture, and AI. Meta
explicitly sells high-resolution photo/video capture and momentary assistance. On-device
OCR and captions prove that useful local visual inference is feasible. They do not amount
to automatic text-only autobiographical memory with immediate raw deletion.

Meta competes for face-worn hardware acceptance, battery, industrial design, distribution,
and user attention. It is not currently the same data product.

### Prototype adjacency

**Google Android XR glasses** have been demonstrated with camera, microphones, Gemini,
context, and language saying the glasses can remember what matters. Google has not publicly
specified a continuous derived-memory event log, raw scene-media deletion contract, local
persistence boundary, open retrospective recall benchmark, or shipping glasses product.

Google proves strategic direction, not occupancy of Trace's exact execution cell.

### Other adjacency

Audio pendants and notetakers compete for the same tolerance for ambient capture but do not
solve visual recall. Lifelogging cameras preserve raw media and solve a different privacy
problem. Memory APIs operate on digital inputs, not first-person physical perception.
Smart-glasses platforms can become suppliers, substitutes, or acquisition channels, but a
camera plus an assistant is not automatically a memory product.

## Exact Cell Verdict

| Claim | Verdict |
|---|---|
| No adjacent competitors exist | False. |
| No visual autobiographical-memory product is claimed | False; Halo claims it. |
| No competitor claims raw-media non-retention | False; Halo and Bee do for their modalities. |
| No proven product has continuous visual input, immediate raw deletion, durable local derived memory, and grounded open retrospective QA | Plausible, but not established by a teardown or benchmark. |
| The exact cell has demonstrated demand | Unknown. No interviews, paid pilots, retention, or willingness-to-pay evidence exists here. |

The supportable statement is:

> Trace is testing an apparently unproven local-first trust architecture for multimodal
> autobiographical memory.

Do not translate "unproven" into "empty market." Empty can mean opportunity; it can also
mean the combination is blocked by battery, information loss, law, social rejection, or a
weak user need.

## What Could Be Defensible

Not defensible by itself:

- no raw-media storage;
- on-device inference;
- a text memory graph;
- retrieval-augmented generation;
- smart-glasses hardware;
- refusal prompts;
- a privacy policy.

Potentially defensible as a verified system:

- useful capture despite irreversible raw deletion;
- a cryptographically auditable raw-data lifecycle across the whole device;
- local encrypted event storage with user-held keys;
- synchronized audio-visual entity and active-speaker binding;
- claim-level provenance and calibrated refusal;
- quality per joule on wearable hardware;
- a consent, correction, export, and deletion model users trust;
- longitudinal evaluation data collected with explicit rights and reproducible scoring.

The moat, if one exists, is the measured performance and trust system under the constraint,
not the constraint's slogan.

## Required Competitive Test

Trace and Halo should be tested on the same consented sessions and blind question set. The
comparison must report:

1. Oracle fact-capture recall before question answering.
2. Open-answer accuracy and unsupported-claim rate.
3. Wrong-person, wrong-object, and wrong-time binding rates.
4. Tiny-text, moving-scene, speech, and active-speaker performance.
5. Raw media written on each device, companion, cache, crash path, and server.
6. Derived-data egress destinations and retention.
7. Battery, heat, latency, offline behavior, and recovery after interruption.
8. Setup burden, pause/consent clarity, export, correction, and deletion completeness.

Until that exists, feature tables compare promises rather than products.

## Market Evidence Missing

The repository contains no credible evidence for market size, serviceable market, price,
retention, acquisition value, or a beachhead user. Prior dollar ranges were constructed
from broad smart-glasses and personal-AI categories and should not drive decisions.

Before more architecture expansion, interview at least 20 users in one narrow segment,
observe their current workaround, test a working bounded prototype, and ask for a concrete
commitment: paid pilot, deposit, or repeated weekly use. Curiosity is not demand.

## Legal and Social Boundary

No-raw storage reduces risk; it does not make the system legally incapable of surveillance.
Derived transcripts, locations, routines, person descriptions, relationships, and inferred
events remain personal data when linked to people. Collection, transformation, storage,
retrieval, and transmission are still processing.

German speech law, image/personality rights, GDPR lawful basis and household scope,
bystander rights, workplace use, biometric classification, DPIA obligations, AI Act scope,
international transfers, and App Store disclosures require qualified review against the
actual executable. The repository is not a legal opinion.

Minimum product rules before any external pilot:

- no raw-media persistence API in the production target;
- a visible, truthful capture indicator and immediate pause;
- consent-scoped sessions before ambient public use;
- no face or voice identity templates;
- no verbatim third-party speech retention by default;
- local encryption, authentication, export, correction, deletion, and retention controls;
- no cloud path without explicit per-use consent and a disclosed data contract;
- device-wide privacy audits, not directory-local badges.

## Scope Decision

The first credible product is not all-day life memory. It is a consented, visual-first,
10-minute session with local event storage, no raw persistence, later open questions,
claim-level citations, and zero unsupported answers.

Speech enters only after active-speaker binding is measured. Identity enters only after
correction and consent exist. Public-space wear enters only after legal and social review.
Frontier reasoning enters only as an explicit text-egress mode, never as a hidden fallback.

Continue the broad thesis only if three untouched held-out sessions achieve OAG at or below
25%, zero unsupported claims, zero wrong-entity/state answers, and a clean whole-container
raw-media audit. Otherwise narrow to deliberate visual bookmarking or reject the text-only
deletion architecture.

## Primary Sources

- [Brilliant Labs Halo](https://brilliant.xyz/products/halo)
- [Brilliant Labs privacy policy](https://brilliant.xyz/pages/privacy-policy)
- [Brilliant Labs: Road to Halo, Part 4](https://brilliant.xyz/blogs/announcements/road-to-halo-part-4)
- [Amazon: Building Bee](https://www.aboutamazon.com/news/devices/bee-amazon-wearable-ai-device-new-features/)
- [Meta: Ray-Ban Meta Gen 2](https://about.fb.com/news/2025/09/ray-ban-meta-gen-2-better-battery-life-video-capture/)
- [Meta: on-device AI in Reality Labs](https://ai.meta.com/blog/executorch-reality-labs-on-device-ai/)
- [Google: Android XR glasses demo](https://blog.google/products/android/android-xr-glasses-demo-io-2025/)
- [European Commission: personal data](https://commission.europa.eu/law/law-topic/data-protection/reform/what-personal-data_en)
- [German Criminal Code section 201](https://www.gesetze-im-internet.de/stgb/BJNR001270871.html)
- [Apple App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/)
