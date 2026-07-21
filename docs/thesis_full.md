# SOMA — An Input-Only Wearable Memory

*Architecture, Rationale, and the Case for a Memory That Keeps Words Instead of Footage.*

*Editable source (reconstruction v3, 2026-07-20) of `docs/SOMA_Architecture_Thesis.pdf`. Editorial fixes vs the PDF: chapters 18/19 restored to logical order (Objections before Conclusion — the PDF renders them swapped), wrapped chapter titles joined. Revision 1.1 adds chapters 20–21, Appendix W, refs [41]–[50]. Edit THIS file; PDF/LaTeX are renders.*

---

## Abstract

SOMA is a wearable memory system built on one uncompromising invariant: raw media never persists and never leaves the device; only typed text may cross the boundary. On-device perception converts the live world into open-vocabulary, provenance-bearing text observations at the moment of capture; the raw pixels and audio that produced them are discarded within milliseconds. A nightly consolidation process — deliberately modeled on biological sleep — binds the day's scattered observations into a typed evidence graph by spatial and temporal co-occurrence, attaching a calibrated confidence to every link and refusing weak ones outright. A recall engine answers unconstrained natural-language questions from this bound text alone, citing the exact observations that support each claim and refusing honestly when the answer was never perceived. This document is the complete argument for that architecture. It derives the design from first principles (Chapters 1–2), situates it against forty years of lifelogging, egocentric-vision, and retrieval-augmented-generation research (Chapter 3), states the seven locked invariants that govern all implementation (Chapter 4), and walks the full pipeline from photons to answers (Chapter 5) — including a complete worked example, the crow, followed end to end from a single wingbeat on a balcony railing to a derived habit node no sensor ever observed (Chapter 6). It then descends into the machine: the formal domain model (Chapter 7), the hexagonal event-sourced software architecture (Chapter 8), the salience-governed perception subsystem (Chapter 9), the binder (Chapter 10), and grounded recall with calibrated refusal (Chapter 11). The remaining chapters treat the privacy architecture and its threat model (Chapter 12), the evaluation methodology that makes every failure diagnosable (Chapter 13), engineering governance (Chapter 14), market position and moat (Chapter 15), honest risks (Chapter 16), and the road from prototype to glasses (Chapter 17). The central hypothesis — that perception can be decomposed into channels which reconstruct lossless-enough textual context for a tractable reasoner to answer arbitrary retroactive questions at near-zero hallucination — is stated throughout as what it is: unvalidated, falsifiable, and instrumented. Every architectural decision in this document exists to test it faster.
## Executive Summary

For the reader with ten minutes. Every claim below is developed, evidenced, and stress-tested in the body; section pointers are given throughout. The product. SOMA is a wearable memory you can question. It senses the day through always-on, cheap perception; turns everything into words the instant it happens — never keeping one frame of video or one second of audio; binds those words into understanding at night; and answers any question about the past with citations to what it actually perceived, or an honest "I don't know."

The insight. The valuable artifact of a lived day was never the footage — it was the bound, queryable meaning. Storage-first wearables keep the toxic artifact (raw media: subpoenable, breachable, socially unacceptable) while deferring the valuable one (extracted, connected facts). SOMA extracts at the moment of capture and keeps only the value (Chapters 1–2). The moat. Surveillance is not forbidden by policy; it is impossible by architecture. The only object that can leave the device is typed text carrying the IDs of the observations it came from; everything else dies at an eleven-line guard that raises an error. The store is AES-256-GCM encrypted under the user's key. A competitor cannot copy this posture without abandoning the stored-media foundation its product is built on (Chapters 12, 15). The machine, in one breath. Cheap senses run continuously (detection, OCR, speech, sound events, motion and pose); an attention scheduler spends a hard hourly budget of deep vision-model "looks" only where dwell, novelty, and stability earn them; every emission is a typed, timestamped, provenance-bearing observation in an append-only log; a nightly binder fuses observations by co-occurrence into living nodes — refusing every weak link — and derives new facts no sensor observed; at question time, a supplier hands a local reasoner just enough cited evidence to answer or refuse (Chapters 5, 9–11). The crow example — Chapter 6 — walks one memory through every stage in four pages. The discipline. Seven locked invariants govern all code (Chapter 4): no raw persistence; text-only egress; append-only truth; provenance on everything; calibrated confidence with refusal over fabrication; unconstrained questions; and nothing built until a missed question demands it. Most are enforced by construction — an invalid memory object cannot exist. SOMA — AN INPUT-ONLY WEARABLE MEMORY EXECUTIVE SUMMARY The measurement. Two metrics keep the system honest (Chapter 13). RAS scores answers with fabrication subtracted — a made-up answer costs what a correct one earns. OAG measures what verbalization lost: of the questions a raw-footage oracle can answer, the share the retained text cannot. Every miss is mechanically diagnosed as (A) never captured or (B) captured but unused, and the miss list is the backlog. Current honest baseline on the 92-second proving clip: RAS 40.0, hallucination 27.3%, with 8 of 9 misses diagnosed (B) — the work is in the binder and reasoner, not in more sensors, and the first disciplined binder (36 entities, 58 bindings, 144 weak links refused) plus grounded recall already exists on a follow-on branch.

The hypothesis, stated as one. That textual channels can carry lossless-enough context for near-zero-hallucination recall is unvalidated — and instrumented rather than assumed. The method: prove sufficiency offline with unlimited compute first; discover the necessary channel set by ablation second; optimize for the live budget last (Chapters 13, 16, Appendix P).

The ask of the reader. Chapter 6 to feel it; Chapter 13 to audit it; Chapter 16 to see what could kill it; Chapter 18 for every hard objection, answered at full strength. The interactive companion (docs/interactive/soma-architecture.html) renders the node graph, the crow, and the privacy membrane live.

SOMA — AN INPUT-ONLY WEARABLE MEMORY EXECUTIVE SUMMARY


## 1 — Introduction and Problem Statement


### 1.1 The problem: lives are forgotten by the people who live them

People forget most of their lives. Where the keys were left. What the doctor actually said, as opposed to what anxiety later reconstructed. Whether the door was locked. The name attached to a face met once at a dinner. Which pharmacy the prescription went to. What the contractor promised, verbally, in the hallway. The moments that matter are sparse, unpredictable in advance, and irretrievable by the time they are needed. Human episodic memory was never designed for retrieval on demand; it is a reconstructive process, optimized for gist over fidelity, and it degrades precisely along the dimensions — exact words, exact places, exact times — that everyday questions require [1][2]. The obvious remedy is to record everything. It fails twice, and both failures are fundamental rather than incidental.

The first failure is social and legal. A person wearing an always-on camera that stores video is a walking surveillance device. Every bystander is recorded without consent; every stored hour is subject to subpoena, theft, breach, and misuse; every intimate space the wearer enters becomes an archive. The history of wearable cameras is a history of this failure: from the earliest sousveillance experiments to the public rejection of camera glasses, storage-first capture has been socially unacceptable everywhere it has been tried at scale [10][34]. No privacy policy fixes this, because policies are promises, and promises about stored media are exactly what nobody believes.

The second failure is functional. Raw footage is the wrong artifact. Nobody rewatches their life; a day of video is a day long. What people actually want from a memory is not playback but answers: they want to query the past the way they query a database, in natural language, and get back a short, true, cited response. The valuable artifact was never the footage — it was the bound, queryable meaning that a mind would have extracted from it. Storage-first systems defer that extraction forever and so never deliver it.


### 1.2 The problem statement

SOMA — AN INPUT-ONLY WEARABLE MEMORY INTRODUCTION AND PROBLEM STATEMENT SOMA's problem statement follows directly: Build a system that perceives a person's day through always-on, cheap senses; converts everything to words the instant it happens — never keeping one frame of video or one second of audio; consolidates those words, nightly, into bound understanding; and later answers arbitrary questions from that understanding with citations, or refuses honestly.

Three phrases in that statement carry the whole design, and each is defended at length in this document. "The instant it happens" is the privacy architecture (Chapter 12): ephemerality at the source, not deletion after the fact. "Bound understanding" is the binder (Chapter 10): isolated observations are raw material, not memory; memory is what emerges when the black shape and the caw and the balcony are fused into a crow. "Or refuses honestly" is the epistemology (Chapters 11 and 13): a memory that fabricates is worse than no memory at all, so refusal is a first-class outcome and fabrication is priced into the headline metric at the cost of a correct answer.


### 1.3 The central hypothesis

Everything rests on one hypothesis, stated in the project's canonical roadmap and repeated here because intellectual honesty about it is the whole game: Perception can be decomposed into channels that reconstruct lossless-enough context — a complete, continuous spatial, temporal, and audio scaffold of the day — such that a tractable reasoner answers arbitrary retroactive questions, including hard spatial ones, at near-zero hallucination.

This hypothesis is unvalidated. It might be false: it might be that no set of textual channels captures enough of the visual world to answer the questions people actually ask; that verbalization at capture time inevitably discards the one detail tomorrow's question needs. SOMA does not assume the hypothesis — it instruments it. The oracle-answerability gap (Chapter 13) measures precisely the distance between what a mind with the raw footage could answer and what the retained text can, and the entire development method — sufficiency first, necessity second, efficiency last — is organized to drive that measurement toward an answer as fast as possible.


### 1.4 What SOMA is not

Boundary-setting is cheap insurance against scope drift, and the project's own governance documents are explicit about it. SOMA is not a recorder: there is no playback, because there is nothing to play back. It is not a general assistant: it does not act, schedule, remind, or intervene; it remembers and answers. It is not a 3D reconstruction of the world: a SOMA — AN INPUT-ONLY WEARABLE MEMORY INTRODUCTION AND PROBLEM STATEMENT photorealistic spatial render was prototyped, answered no question the text could not, and was killed under the project's anti-diversion law (Chapter 14). And it is not "answer anything at 50%": a memory that is half right and confidently wrong the other half is a liability, which is why the invariant is hallucination approaching zero with refusal as the honorable exit.


### 1.5 Contributions of this document

This exposition makes five contributions. First, a derivation of the input-only architecture from first principles — the standard model of perception, the reconstructive nature of memory, and the economics of attention — rather than from product intuition (Chapter 2). Second, a complete formalization of the system's domain model, down to the constructor invariants of each value type (Chapter 7). Third, a fully worked example — the crow — that traces one memory from photons to a derived insight to a cited answer, exercising every subsystem on the way (Chapter 6). Fourth, an evaluation methodology in which every failure is mechanically attributable to capture or to reasoning, so that the system's development is driven by diagnosed misses rather than intuition (Chapter 13). Fifth, an honest register of risks, including the ways the central hypothesis could fail (Chapter 16).


### 1.6 How to read this document

Chapters 1–6 are readable by anyone and constitute the argument; a reader deciding whether to join or fund this project should read exactly these. Chapters 7–11 descend into the machine and assume software literacy. Chapters 12–17 treat privacy, measurement, governance, market, risk, and roadmap, and are the chapters an auditor or a skeptic should read first. The appendices transcribe the founding napkin sketch and map every phrase on it to the production system, provide a full glossary, and list the formal domain model. Citations in brackets refer to the consolidated bibliography; references to code paths name files in the SOMA repository, which is the ground truth wherever this document and the code could disagree.

SOMA — AN INPUT-ONLY WEARABLE MEMORY INTRODUCTION AND PROBLEM STATEMENT WORLD EYES / EARS (manufacturable senses) BRAIN Standard model (human) WORLD CAMERA / MIC TYPED WORDS BRAIN raw pixels/audio die in milliseconds - only the words survive SOMA (machine) Figure 1 — The standard model, copied then amended: SOMA keeps the words, never the stream. SOMA — AN INPUT-ONLY WEARABLE MEMORY INTRODUCTION AND PROBLEM STATEMENT


## 2 — Conceptual Foundations


### 2.1 The standard model: a brain never touches the world

The founding sketch of SOMA — drawn on a napkin, reproduced and transcribed in


## Appendix A — begins not with a product but with an epistemological observation labeled

"Standard Model": the world reaches a brain only through senses. There is no direct acquaintance with reality; there is only the sensory stream and what a mind makes of it. For a manufactured system, the sketch notes, the practically buildable senses are eyes and ears — cameras and microphones — "because we can't manufacture other senses, or most of the information is obtained through this."

This observation does real work. It says that a machine memory need not apologize for perceiving only sight and sound: that is approximately the human condition too, and humans construct rich, queryable lives from it. It also says that whatever the system stores is already an interpretation — there is no neutral, complete record to preserve, only choices about which interpretation to keep. Storage-first systems pretend otherwise; they keep the stream and defer interpretation, inheriting the costs of both. SOMA commits to the interpretation at capture time and keeps only that.

The amendment SOMA makes to the standard model is therefore not a compromise but a completion: World → senses → words → brain. The words are the interpretation; the brain — consolidation at night, reasoning at question time — operates on words alone.


### 2.2 Episodic memory is reconstruction, not playback

The choice has a deep precedent: it is how biological memory actually works. Human beings do not store sensory streams. Tulving's foundational distinction [1] separates episodic memory — events located in subjective time and place, the "mental time travel" system — from semantic memory, the consolidated knowledge that no longer carries its acquisition context. Bartlett demonstrated nearly a century ago that recall is reconstructive: people retrieve gist and rebuild detail, importing schema-consistent inventions in the process [2]. The visual system itself retains almost nothing of the retinal stream beyond the current fixation; what persists is categorical, linguistic, relational. SOMA — AN INPUT-ONLY WEARABLE MEMORY CONCEPTUAL FOUNDATIONS SOMA's two stores mirror the biological pair precisely. The append-only observation log — every typed emission of every perceiver, stamped with time and place — is the episodic store: sparse, literal, chronological. The evidence graph that the nightly binder builds over it — entities, bindings, derived facts — is the semantic store: consolidated, cross-referenced, queryable. And the system's honesty about reconstruction exceeds the biological original: where human recall silently invents schema-consistent detail, SOMA's recall is forbidden to assert anything that does not trace to a logged observation, and says "I don't know" where a human would confabulate.


### 2.3 Sleep consolidation: why the binder runs at night

The decision to concentrate binding in a nightly pass is likewise borrowed from biology. Systems-consolidation research shows that the mammalian brain replays the day's hippocampal traces during slow-wave sleep, gradually binding them into neocortical structure — an architecture forced by the same constraint SOMA faces: deep integration is expensive, and the organism cannot afford it while also perceiving [3]. Night is when the device is charging, thermally unconstrained, and free to run the big model over the whole day at leisure. The napkin's phrase is exact: node creation is "always running in the background, but better nightly." Incremental binding accelerates; the night shift perfects. The Hebbian slogan — cells that fire together, wire together [35] — is the binder's actual operating principle, transposed to text: observations that co-occur in time and place, repeatedly, get bound into shared structure. Chapter 6's crow is the worked demonstration.


### 2.4 Event segmentation: why capture is gated, not uniform

Human perception does not sample the world uniformly; it carves experience into events at boundaries of change, and encodes richly at those boundaries [4]. SOMA's capture follows the same economics (Chapter 9): the cheap channels run continuously precisely because they are cheap, while the expensive channel — deep visual description by a VLM — fires only on attention, dwell, or change. Uniform deep capture would be both unaffordable and pointless: most moments do not matter, and the value of a memory is concentrated in the few that do. The scheduler that makes this call is not an optimization detail; it is the system's model of what deserves to be remembered well, which is why the project treats it as the moat.


### 2.5 Text as the retention format: the four arguments

The load-bearing decision — keep words, not media — rests on four arguments. SOMA — AN INPUT-ONLY WEARABLE MEMORY CONCEPTUAL FOUNDATIONS Privacy is structural, not promised. A store that physically contains no pixels cannot leak pixels. This is privacy-by-design in Cavoukian's original sense — protection embedded in the architecture rather than appended as policy [5] — and data minimization in the sense of GDPR Article 5(1)(c): collect the meaning, not the medium [6]. The strongest privacy claim a storage-first system can make is "we promise not to look." SOMA's claim is categorically different: "there is nothing to look at." Chapter 12 develops the full threat model. Text is the interlingua of reasoning. Modern reasoners — local or frontier — consume and produce text natively [7]. A text store makes every present and future language model a drop-in brain, decouples the memory from any particular model's lifespan, and makes the escape hatch to a stronger model (Chapter 11) safe by construction: text was already the only thing allowed out.

Text is economically lossless-enough to keep forever. A day of typed observations is on the order of megabytes; a day of video is tens of gigabytes. At text rates, never deleting becomes affordable — which is what makes invariant I3 (the append-only log is forever) practical, and what makes the discarder's rule (drop derived structure, never raw material) free.

Text is auditable by its owner. A user can open their memory and read, in their own language, every fact the system holds about them. No one can audit what a neural embedding of their kitchen contains. Auditability also disciplines the system itself: every answer's citations point at human-readable lines, so a wrong answer can be traced to the observation that misled it.

The cost of the decision is stated with equal weight: whatever the perceivers fail to verbalize at capture time is gone forever. There is no going back to the frames. This is the sharpest edge of the architecture — the point where the central hypothesis could break — and it is why the oracle-answerability gap exists as a first-class metric rather than an afterthought (Chapter 13).


### 2.6 The resolution of the central tension

Maximum context and detail-follows-attention pull in opposite directions, and the project's north-star document resolves the tension in one sentence that governs the whole capture design: capture everything cheaply, perceive deeply only what attention marks. Maximum cheap context — the continuous scaffold of OCR, speech, sound events, motion, place — plus selective deep context where salience justifies the spend. Chapter 9 gives the scheduler that implements the resolution; Chapter 13 gives the method that verifies, by ablation, that nothing load-bearing was lost to the economy. SOMA — AN INPUT-ONLY WEARABLE MEMORY CONCEPTUAL FOUNDATIONS CAPTURE live · cheap · parallel · OCR / ASR / sounds · sensors + pose · VLM gist (gated) · raw discarded instantly SLEEP nightly · the big model · congregate + dedupe · bind by when+where · confidence per link · weak links refused ASK on demand · navigate bound words · cite what was seen · refuse the unperceived · never re-open raw Figure 3 — Three tempos: live capture, nightly consolidation, on-demand recall. SOMA — AN INPUT-ONLY WEARABLE MEMORY CONCEPTUAL FOUNDATIONS


## 3 — Prior Art and Position


### 3.1 The memex lineage: total capture as an old dream

The dream of an external memory is as old as computing's founding essays. Vannevar Bush's 1945 memex imagined a device in which an individual "stores all his books, records, and communications," consulted "with exceeding speed and flexibility" [36]. Every generation since has re-attempted the dream with its era's storage medium, and every attempt has clarified the same two lessons: capture is easy, retrieval of meaning is the hard part; and total storage of raw experience creates more problems than it solves.


### 3.2 MyLifeBits and SenseCam: storage-first, and what it taught

The most serious modern attempts came from Microsoft Research. Gordon Bell's MyLifeBits project [9] digitized and stored a life — documents, photos, calls, screen captures — and found that the bottleneck was never disk space but annotation and query: a stored life without structure is a landfill. The SenseCam [10] — a wearable camera taking passive photographs on sensor triggers — demonstrated genuine clinical value as a memory prosthesis for amnesic patients, with recall improvements that persisted for months; it also demonstrated, in every deployment study, the social cost of a visible always-on camera and the burden of reviewing captured images [34]. The lifelogging literature's own retrospectives converge on the diagnosis SOMA starts from: the artifact that helps is not the image archive but the cues and facts extractable from it [37]. SOMA's relationship to this lineage is inversion, not iteration: capture is total, but retention is linguistic. The extraction that MyLifeBits deferred and SenseCam left to the user happens at the moment of capture, and the raw stream — the socially and legally toxic artifact — never exists at rest.


### 3.3 Ego4D and egocentric vision: the demand curve, measured

The computer-vision community has meanwhile quantified exactly the capability SOMA targets. Ego4D [11] collected 3,670 hours of egocentric video and defined benchmark tasks that read like SOMA's question battery: episodic memory ("where did I last see X?"), SOMA — AN INPUT-ONLY WEARABLE MEMORY PRIOR ART AND POSITION audio-visual diarization ("who said what when?"), forecasting, and hand-object interaction. Successor benchmarks extended to natural-language queries over one's visual past. Two facts from this literature matter here. First, the tasks are hard even with the raw video available at query time — long-horizon retrieval over egocentric streams is an open problem. Second, every published approach keeps the video, inheriting the storage-first costs. SOMA's wager is that a day of well-chosen words plus a competent reasoner can approach the raw-video ceiling on the questions people actually ask — and OAG (Chapter 13) is the instrument that measures how close.


### 3.4 Retrieval-augmented generation: the ASK stage's ancestry

SOMA's answering stage is structurally retrieval-augmented generation [12]: retrieve evidence, condition generation on it, attribute the output. The differences are ones of discipline rather than shape. The corpus is machine-perceived rather than authored, so every datum carries a capture-time confidence. Attribution is mandatory at the claim level, in line with the attributed-QA research program [31]. And abstention is a tuned, first-class outcome — selective prediction [13] — rather than a failure mode, because the headline metric subtracts fabrication instead of merely not rewarding it. The hallucination literature [32] catalogues precisely the behavior SOMA's grounding gate exists to make structurally difficult.


### 3.5 The commercial field: an empty quadrant

Plotting the wearable-memory field on two axes — what is stored (raw media versus derived text) and where reasoning happens (cloud versus device) — makes the market structure visible. Screen-recording memory products store everything and search it; audio pendants store or transcribe conversations, retaining raw or verbatim records; camera glasses stream to cloud services. All occupy the raw-retention half-plane, and all inherit its consequences: subpoena exposure, breach liability, bystander hostility, and app-store/regulatory friction. The quadrant SOMA occupies — nothing but derived text at rest, perception on device, raw media architecturally impossible to retain — is, at the time of writing, empty. The project's market memorandum names the acquirers for whom that quadrant is strategic; this document confines itself to the architectural point: the moat is not a feature but an incapability, and incapabilities cannot be copied by adding a feature flag. Product class What persists Where perception runs Inherited liability Screen-recording memory tools full raw screen video local, retained archive of everything ever displayed, incl.

secrets SOMA — AN INPUT-ONLY WEARABLE MEMORY PRIOR ART AND POSITION Audio pendant recorders audio and/or verbatim transcripts cloud, retained every conversation discoverable; consent law exposure Camera glasses / clip cams photos, video cloud, retained bystander images at rest; the SenseCam lesson at scale Phone assistants w/ memory chat + service data cloud scoped to app usage, blind to the lived world SOMA typed text observations only on device no media artifact class exists to leak The table's last column is the argument in miniature: every competitor's liability is a stored artifact class, and SOMA's defining move is that its equivalent class is never instantiated. This is also why the moat deepens rather than erodes with regulatory attention — every recording-law tightening raises rivals' costs and leaves an input-only architecture untouched.


### 3.6 Knowledge graphs and open vocabulary

The evidence graph is a property graph — entities, typed edges, confidence, provenance — squarely in the knowledge-graph tradition [14]. The deliberate deviation is open vocabulary: observation kinds and binding predicates are unconstrained strings, because a fixed schema is a fixed ceiling on what can be remembered, and the project explicitly rejected constraining the question surface. Schema discipline is replaced by evidential discipline: any predicate is admissible, but no predicate is assertable without provenance and confidence.

SOMA — AN INPUT-ONLY WEARABLE MEMORY PRIOR ART AND POSITION


## 4 — The Seven Invariants

Architecture is what remains constant while everything else iterates. SOMA locks seven invariants; each is stated with its rationale, its enforcement mechanism, and the failure mode it forecloses. Code that violates an invariant does not merge — several are enforced by construction, so violating them does not even compile against the domain model.


### 4.1 I1 — No raw persistence

Statement. Raw pixels and audio are discarded the instant words are extracted from them. There is no record path, no cache, no "temporary" buffer that survives the perceptual moment.

Rationale. Every stored frame is a liability with no compensating asset: it cannot be queried directly, and it is the artifact whose existence makes the system a surveillance device. Ephemerality at the source is the only privacy claim that survives an adversarial audit — deletion policies, retention windows, and encryption of stored media all reduce to promises. Enforcement. Capture code converts and drops in one motion; the repository's ignore rules block media files as defense-in-depth; and the live invariant is a named, falsifiable gate in the roadmap — demonstrated on stage as the "no-raw-media proof panel," with the store shown text-only while frames visibly die. Honesty note: legacy .MOV files from the pre-pivot era exist as evaluation oracles; the README states plainly that the live invariant is a target with a gate, not yet a proven fact. This document does not pretend otherwise.


### 4.2 I2 — Text-only egress

Statement. The only payload type permitted to cross the device boundary is TextEgress: typed text carrying the identifiers of the source events it derives from. Rationale. Local models may hit a quality wall (Chapter 16); the architecture must allow routing reasoning to a stronger model without ever routing media anywhere. Typing the boundary makes the safe path the only path.

SOMA — AN INPUT-ONLY WEARABLE MEMORY THE SEVEN INVARIANTS Enforcement. EgressGuard.text() (in src/soma/application/egress_guard.py) raises PrivacyViolationError for any payload that is not a TextEgress; the type's own constructor rejects empty text and empty provenance. The guard is eleven lines long — short enough to audit in one breath, which is the point.


### 4.3 I3 — Append-only truth

Statement. The observation log is immutable and append-only; it is the single source of truth. Everything derived from it — the evidence graph, every index — is a disposable, replayable projection.

Rationale. Consolidation is experimental and will be wrong often; retrieval structures will be redesigned repeatedly. If derived structure were the truth, every such change would risk memory loss. With an immutable log, any projection can be thrown away and rebuilt — the napkin's discarder rule: marinated content that proves useless is dropped, never the raw material.

Enforcement. The SQLite event-log adapter exposes no update and no delete; its docstring states the contract, and the schema has no mutation path. Replays are deterministic, which Chapter 13's evaluation depends on.


### 4.4 I4 — Provenance everywhere

Statement. Every observation, binding, citation, and egress payload carries the event identifiers it derives from. An unsourced claim is a construction error. Rationale. Citations are the product (answers must show their evidence), diagnosis is the method (a wrong answer must be traceable to the observation that misled it), and audit is the promise (the user can see where every remembered fact came from). Enforcement. Constructors: Binding rejects an empty evidence tuple; Observation rejects a timestamp that disagrees with its provenance; TextEgress rejects empty source lists. Provenance is not a logging convention — it is a type obligation.


### 4.5 I5 — Calibrated confidence; refusal over fabrication

Statement. Every binding carries a confidence in [0,1] intended to be calibrated; links below the floor are refused, not hardened; at answer time, insufficient evidence yields "I don't know."

Rationale. A memory's worth is its trustworthiness. One confident fabrication — "you locked the door" when you did not — costs more trust than a hundred honest refusals. The SOMA — AN INPUT-ONLY WEARABLE MEMORY THE SEVEN INVARIANTS metric agrees: RAS subtracts fabrications from corrects, so the optimizer and the ethics point the same way.

Enforcement. Confidence rejects values outside [0,1] at construction; Binding.is_usable(floor) is the refusal gate in domain form; the binder's contract (Chapter 10) makes refusal the default disposition of weak evidence; calibration itself is a measured property (Chapter 13), per [20].


### 4.6 I6 — Unconstrained questions

Statement. There is no fixed question taxonomy, no menu of supported query types. Users ask anything, natively.

Rationale. A constrained question surface is a product decision masquerading as a safety decision: it hides hallucination by refusing to hear the questions that would expose it. The honest path is open vocabulary end to end — open observation kinds, open predicates, open questions — with calibrated refusal as the safety mechanism instead of a menu. Enforcement. The domain's Query type is a bare text string by design; the north-star document explicitly supersedes an earlier suggestion to constrain question types, and the founder's locked decision is recorded in the README.


### 4.7 I7 — Nothing is built until a missed question demands it

Statement. Every helper, sensor, channel, and feature must be authorized by a diagnosed failure on a real question from a real capture.

Rationale. Perception systems invite infinite plausible work; intuition about which channel matters is reliably wrong. The project's own history supplies the cautionary tale: a 3D world renderer was built on intuition, answered nothing, and was killed. The discovery loop — ask, miss, diagnose, build exactly the missing channel — replaces guessing with evidence, and the overnight self-play harness automates the asking.

Enforcement. Governance (Chapter 14): the plan-gate requires naming the roadmap item and the missed question before any build starts. The (A)/(B) diagnosis log (Chapter 13) supplies the missed questions mechanically.


### 4.8 The invariants as a system

The seven interlock. I1 and I2 make the privacy claim structural; I3 and I4 make memory auditable and experimentation safe; I5 and I6 together make "ask anything" compatible with "near-zero hallucination" — the refusal gate absorbs what open vocabulary exposes; I7 SOMA — AN INPUT-ONLY WEARABLE MEMORY THE SEVEN INVARIANTS keeps the whole system growing along the gradient of measured need. Remove any one and a neighboring invariant loses its footing: without I4, I5's confidences have nothing to bind to; without I3, I7's replays are impossible; without I5, I6 becomes reckless. They are stated separately for enforcement but justified jointly.

SOMA — AN INPUT-ONLY WEARABLE MEMORY THE SEVEN INVARIANTS


## 5 — The Pipeline: From Photons to Answers

The founding napkin decomposes execution into a chain of black boxes. Each has since become a named subsystem with a file path. This chapter walks the chain in order; Chapters 7–11 open each box. Appendix A maps every napkin phrase to its production counterpart. SENSES video·audio·pose EXTRACTION frames→signal MACRO VLM scene gist HELPERS OCR·ASR·sounds TEXT +coords +time BINDER co-occurrence NODES living cells SUPPLIER just-enough ctx LLM sits after the last box - a commodity reasoner; the value is everything upstream Figure 2 — The execution pipeline: eight black boxes from the napkin, industrialized.


### 5.1 Stage 1 — Senses

Video is the eyes; audio is the ears; and riding alongside are the senses the napkin's "Standard Model" note said we cannot manufacture — except the phone can: inertial motion, 6-DOF pose, GPS place, orientation. These sensor channels are tiny, so they are kept losslessly and continuously from the first instant. Egomotion in particular is a first-class input, not an afterthought: it is what answers "which floor was I on?" and "which side of the street?" — the validated form of the spatial insight that the abandoned 3D renderer got wrong. The device substrate uses ARKit's world tracking for pose and relocalization [15].


### 5.2 Stage 2 — Extraction

The extraction stage turns streams into usable moments: blurry frames are discarded (motion blur is measured, not guessed), and what survives is stamped with coordinates, timestamps, and context — the spatio-temporal scaffold that every later stage hangs facts SOMA — AN INPUT-ONLY WEARABLE MEMORY THE PIPELINE: FROM PHOTONS TO ANSWERS on. The napkin's phrase for the output — "signal-noise deciphered" — is the stage's whole job description. Nothing semantic happens here; extraction's product is well-located raw material for the perceivers.


### 5.3 Stage 3 — The macro picture

A small vision-language model provides scene gist — "a macro picture of what's happening" — but only when the salience scheduler decides the moment has earned the cost (Chapter 9). Gist is deliberately coarse: its job is orientation ("kitchen, morning, person cooking"), giving the binder a stage on which to place the specialists' details. On the device substrate this role was prototyped with FastVLM-class models [38]; the current design routes gist through the same budgeted enrichment path as all deep looks.


### 5.4 Stage 4 — The helpers

The napkin: "a specialized eye or helper for various tasks; called as needed." Helpers are narrow perceivers, each emitting typed text: OCR reads visible text (receipts, signs, screens); ASR transcribes speech [30]; a sound-event tagger names the non-speech world — cry, alarm, hum, door latch [39]; a detector-tracker maintains object identities across frames (Chapter 9). Two properties define the helper stratum. First, cheapness: helpers run continuously because they cost almost nothing next to a VLM call. Second, empirical membership: the helper set is discovered, not designed — a helper is added when a missed question demands it (I7), and the ablation method (Chapter 13) prunes any that prove non-load-bearing.


### 5.5 Stage 5 — Text

Everything converges to the wire format of memory: open-vocabulary observations — text from various helpers, marked by coordinates — each carrying kind, subject, attributes, time, optional spatial anchor, confidence, and provenance (formally, Chapter 7). This is "the best understanding possible of the world" at capture time, and it is all that survives the moment. The raw media that produced it is already gone.


### 5.6 Stage 6 — The binder

Isolated observations are not yet memory. The binder fuses them across channels by co-occurrence — "binding the coordinates, physicality and temporality together": the dark shape and the harsh call at the same second and place were one crow; the hum that always shares a desk with the laptop is the laptop's fan. Binding output is the napkin's "first thought, or raw material that can be marinated on — not a complete node" — tentative structure, SOMA — AN INPUT-ONLY WEARABLE MEMORY THE PIPELINE: FROM PHOTONS TO ANSWERS each link carrying a confidence, weak links refused outright. Chapter 10 gives the contract.


### 5.7 Stage 7 — Node creation

Consolidation marinates raw bindings into living nodes: entities and derived facts that — the napkin's most vivid phrase — behave like "a physical living breathing cell that can combine with fellow nodes to derive new things: 1+1=4, not 2." A node is alive in three senses: it accretes evidence across days without duplicating; it participates in derivations that produce genuinely new nodes no sensor observed; and it can be demoted or dissolved when the discarder finds it useless — while the raw material beneath it is never touched (I3). The store is encrypted such that only the user's app deciphers it (Chapter 12). Node creation runs continuously in the background, but better nightly.


### 5.8 Stage 8 — The information supplier

At question time, the supplier navigates the graph and assembles just enough context for the reasoner — an evidence dossier, not a data dump. No context window holds a life, and no local model needs it to: the supplier's craft is selection, compression, and citation-carrying. Then, in the napkin's closing shrug, the LLM does what LLMs do. The reasoner is a commodity at the end of the pipe; every ounce of the system's value is upstream of it, in what was perceived, how it was bound, and which evidence is on the table. Chapter 11 details the loop, the grounding gate, and refusal.


### 5.9 What flows between stages

Interface Payload Persisted?

Chapter Senses → Extraction frames, samples, sensor ticks never Extraction → Perceivers gated crops + coordinates + t never Perceivers → Log typed Observation forever (append-only) Log → Binder observation replay derived only Binder → Graph Entity, Binding (+confidence, evidence) disposable projection Graph → Supplier evidence dossier transient Supplier → Reasoner just-enough context (text) transient Anything → off-device TextEgress only, via EgressGuard n/a SOMA — AN INPUT-ONLY WEARABLE MEMORY THE PIPELINE: FROM PHOTONS TO ANSWERS


## 6 — The Crow: One Memory, End to End

A worked example is worth a chapter of assertion. What follows traces a single, small, real-shaped memory through every subsystem — capture, gating, binding, refusal, derivation, and recall — at the level of the actual data structures. The interactive companion renders this same scenario as a live, steppable node graph; here it is frozen on paper with the numbers visible.


### 6.1 Tuesday, 07:42:03 — the eyes fire

You step onto the balcony carrying a trash bag. A crow lands on the railing. The always-on detector — cheap, running on every gated frame — registers a dark object entering the scene and holds a track on it. It emits: observation: kind=object, subject=black bird, attributes=[position: balcony_railing, size: small], t=07:42:03.210, spatial_anchor=balcony/railing, confidence=0.71, provenance=(ev-4183, channel=detector) The frame that produced this observation is already gone. No pixel of the crow exists anywhere.


### 6.2 Tuesday, 07:42:04 — the ears fire, independently

The sound tagger, a separate always-on helper that knows nothing of the detector, hears a harsh call: observation: kind=sound_event, subject=corvid call (caw), t=07:42:04.030, spatial_anchor=balcony, confidence=0.66, provenance=(ev-4184, channel=audio) Two lines of text now exist that happen to share a second and a place. Nothing yet says they are the same event. That ignorance is deliberate: capture channels never coordinate; coordination is the night's job. Cheap parallel senses first, expensive fusion later — the same decomposition biological perception uses.


### 6.3 Tuesday, 07:42:06 — attention pays for one deep look

SOMA — AN INPUT-ONLY WEARABLE MEMORY THE CROW: ONE MEMORY, END TO END The bird stays. In the scheduler (Chapter 9), the track's dwell accumulates while its novelty is high — a bird on this railing is not familiar — so salience crosses the enrichment threshold and the token bucket has budget. One token is spent; the expensive eye looks once, at just this crop, at level 1 of the enrichment ladder: observation: kind=vlm_gist, subject=large corvid, attributes=[color: glossy black, activity: perched, watching], t=07:42:06.400, confidence=0.78, provenance=(ev-4188, channel=vlm) Meanwhile the sensors never stopped: pose says balcony, facing east (ev-4189); the detector's other track says a trash bag is in hand (ev-4190). Five observations, three channels, one shared scaffold of when-and-where. Total persistent footprint of the entire event: under a kilobyte of text.


### 6.4 Tuesday, 23:40 — the night shift binds

You sleep; the device charges; the big model reads the day. The binder clusters by co-occurrence: ev-4183 (dark shape, railing, 07:42:03), ev-4184 (caw, balcony, 07:42:04), ev-4188 (corvid gist, 07:42:06) — same place, same seconds, compatible kinds. It proposes an entity and scores the join: entity: crow_1, kind=animal, label=crow — binding: subject=crow_1, predicate=observed_at, object=balcony/railing @ 07:42, confidence=0.87, evidence=(ev-4183, ev-4184, ev-4188) The crow node is born: a living cell citing every observation it grew from. Note what the confidence is doing — 0.87 is not decoration, it is the survival threshold made explicit. Which matters immediately, because:


### 6.5 Tuesday, 23:40:02 — and refuses what it cannot prove

A neighbor's wind chime rang at 07:42:10 (ev-4191). Temporally correlated with the crow? Yes. Causally or physically related? The binder scores the join at 0.31 — below the 0.55 floor — and refuses it. The link is not stored weakly; it is not stored at all. Weak links are refused, not hardened (I5). This single behavior is why the graph does not silt up with coincidence, and why answers do not hallucinate connections. The evidence for the refusal's wisdom arrives in Chapter 13: hallucination in the baseline system is dominated by exactly the joins a disciplined binder would have refused.


### 6.6 Wednesday and Friday — the node thickens

SOMA — AN INPUT-ONLY WEARABLE MEMORY THE CROW: ONE MEMORY, END TO END Wednesday 07:44: trash bag, crow, caw. Friday 07:39: trash bag, crow. Each morning writes fresh observations; each night the binder finds the same shape in them. Identity resolution matters here: the new sightings do not spawn crow_2 and crow_3 — same place, same behavioral signature, same kind resolve to crow_1, whose confidence rises to 0.93 and whose evidence tuple now spans three days. Nodes that fire together, wire together; nodes that recur, thicken.


### 6.7 Friday, 23:42 — 1 + 1 = 4

Now the cell combines with its fellow nodes and derives something no sensor ever observed. The pattern engine notices: every observation cluster containing crow_1 also contains the trash-bag-in-hand observation, three mornings out of three, within the same two-minute window: derived binding: subject=crow_1, predicate=co_occurs_with, object=trash-run (morning routine), confidence=0.81, evidence=(tue cluster, wed cluster, fri cluster) One crow plus one chore equals four: the crow, the chore, the pattern, and the anticipation the pattern licenses. This is the napkin's arithmetic made literal, and it is the entire justification for building a graph instead of a diary: isolated observations answer "what happened?"; combined nodes answer "why?" and "what will?".


### 6.8 Saturday, 10:15 — you ask

"Why is that crow always on my balcony?" The supplier walks the graph — crow_1, its sightings, its derived habit — and hands the reasoner a dossier of perhaps twenty lines. The answer returns with its evidence attached: "A crow has been landing on your balcony railing on the mornings you take the trash out — seen Tuesday, Wednesday, and Friday around 07:40. It appears to be showing up for the trash." — citations: ev-4183, ev-4188, wed cluster, fri cluster "What color were its eyes?" The supplier finds no observation about eyes — the level-1 enrichment never got that deep, because dwell never earned level 3. The grounding gate finds the draft unsupported, and the memory answers: "I didn't perceive that." No fabrication. The refusal is not a failure of the system; it is the system, working. A storage-first product would have offered to re-watch the video. SOMA has no video — it has the honesty of its words.

SOMA — AN INPUT-ONLY WEARABLE MEMORY THE CROW: ONE MEMORY, END TO END black bird · railing sound: caw corvid, glossy black trash bag in hand place: balcony CROW  conf .87 comes for the trash  conf .81 wind chime refused (.31) Figure 6 — The crow example as it rests in the graph after Friday's night shift.


### 6.9 What the example proves

Every invariant did visible work. I1: no pixel of the crow survived the capture second. I3: three nights of binder runs never touched Tuesday's raw observations. I4: the final answer cites capture-time event IDs. I5: the wind chime died at the floor; the eye-color question died at the gate. I7, prospectively: had the user asked "which direction did it fly off?" and the memory missed, the diagnosis log would name the missing channel (heading, from pose), and that miss — not intuition — would authorize building it. The crow is small. The architecture is exactly the crow, at the scale of a life.

SOMA — AN INPUT-ONLY WEARABLE MEMORY THE CROW: ONE MEMORY, END TO END


## 7 — The Domain Model

The domain layer (src/soma/domain/) is deliberately tiny: seven frozen value types, each a dataclass whose constructor is the boundary where invariants are enforced [19]. Nothing in the layer performs I/O, imports an adapter, or names a model. The layer is small enough to read in half an hour, and that smallness is a design position: the vocabulary of memory should fit in a head.


### 7.1 Observation — the atom

An Observation is one typed emission from one perceiver: an open-vocabulary kind and subject; a tuple of Attribute name–value pairs; capture time t_ms; an optional spatial_anchor; a Confidence; a Provenance; and an optional refutation_cue — a hint about what evidence would disprove the observation, falsifiability designed into the datum itself. Constructors reject empty kinds and subjects, negative times, and — critically — any disagreement between the observation's time and its provenance's capture time: an observation cannot claim to be from a moment its evidence trail denies.


### 7.2 Provenance — the birth certificate

Provenance is three fields: event_id, source_channel, captured_at_ms, each validated non-empty/non-negative. It answers, for any datum in the system, the auditor's three questions: which event, which sense, which millisecond. Nothing exists without one (I4).


### 7.3 Confidence — a number with a contract

Confidence wraps a float and rejects anything outside [0,1] at construction. The type exists so that "confidence" can never drift into being a score, a rank, or a vibe: it is a probability, and the system's intent (measured in Chapter 13) is that it be calibrated — a 0.8 right about 80% of the time [20]. Refusal thresholds (I5) are only meaningful over calibrated numbers; an uncalibrated confidence is a decoration, and decorations kill.


### 7.4 Entity and Binding — the graph

SOMA — AN INPUT-ONLY WEARABLE MEMORY THE DOMAIN MODEL Entity is a stable identity: id, kind, label. Binding is the edge: subject–predicate–object where the object is exactly one of an entity reference or free text (the constructor rejects both-or-neither); a Confidence; and a non-empty tuple of Provenance evidence. Binding.is_usable(minimum_confidence) is the refusal gate expressed in domain form — one comparison, but placed where every consumer must pass through it.


### 7.5 Query, Citation, RecallAnswer — the ASK contract

Query is a bare non-empty string (I6: no taxonomy). RecallAnswer is text plus a tuple of Citations — node id and optional timestamp. The contract encodes the product promise at the type level: an answer has citations; an answer without them is a different type of thing and does not exist in the domain.


### 7.6 TextEgress — the only exportable thing

TextEgress is non-empty text plus a non-empty tuple of source_event_ids. It is the single type the device boundary accepts (I2), and its constructor makes anonymous egress impossible (I4): text cannot leave without naming the observations it came from.


### 7.7 Why constructors, not validators

All seven types validate in __post_init__ and are frozen thereafter. The alternative — permissive construction plus downstream validation — distributes the invariant over every consumer and guarantees eventual drift. Here, an invalid domain object cannot exist, so every function accepting an Observation inherits its guarantees silently. The strict-typing gate (Chapter 14) runs mypy --strict over this layer with 100% of the public surface typed; the test suite covers the constructor rejections explicitly. SOMA — AN INPUT-ONLY WEARABLE MEMORY THE DOMAIN MODEL


## 8 — Software Architecture

Three patterns govern the production monolith, each chosen for a failure mode it forecloses: hexagonal structure against substrate lock-in, event sourcing against experimental memory loss, and the strangler fig against the big-bang rewrite.

ADAPTERS - sqlite eventlog · encrypted text · vision OCR · MLX VLM · ollama · cloud text (guarded) PORTS - Perceiver · Ocr · Asr · VlmRunner · TextReasoner · MemoryStore · RecallBackend APPLICATION - Recall · EgressGuard · Binder · CaptureScheduler · GroundingGate DOMAIN Observation · Entity · Binding · Confidence · Provenance · TextEgress dependencies point inward only - the domain imports nothing concrete Figure 4 — The hexagonal monolith: dependencies point inward; substrates swap at the rim.


### 8.1 Hexagonal: ports and adapters

The layout follows Cockburn's ports-and-adapters [21] with Clean Architecture's dependency rule [22]: dependencies point inward only. domain/ imports nothing concrete. application/ orchestrates use cases against ports/ — seven typing.Protocol interfaces: Perceiver, Ocr, Asr, VlmRunner, TextReasoner, MemoryStore, RecallBackend. adapters/ implement the ports against reality: Apple Vision OCR, MLX-hosted VLMs, Ollama-served local reasoners, the SQLite event log, the AES-GCM text codec, and a guarded cloud text reasoner.

The pattern earns its keep in this codebase specifically because the same core must run on three substrates: the Mac processing pipeline (V0), the iPhone rig (V1), and eventually glasses — plus pure in-memory doubles for tests. Ports make each substrate a set of adapters rather than a fork. The perception scheduler is written to the same discipline — pure logic, injected clock, no I/O — precisely so it ports 1:1 to Swift when capture moves fully on-device.

SOMA — AN INPUT-ONLY WEARABLE MEMORY SOFTWARE ARCHITECTURE


### 8.2 Event sourcing and disposable projections

The capture core is event-sourced [23]: every perceiver emission is appended to an immutable log (adapters/sqlite_eventlog.py — the public API has no update and no delete; the docstring states the contract). Derived read models — the evidence graph, vector indexes, temporal indexes — are projections in the CQRS sense [24]: rebuildable by replay, free to change shape as the binder improves, safe to discard entirely. What this buys, concretely: deterministic replay, the backbone of offline evaluation — a recorded day can be re-perceived and re-bound under a new binder and scored against the same gold answers; audit, since the log is the history; crash-safety, since append-only writes have no torn-update states; and the discarder semantics of the napkin — a bad marination is dropped without touching the raw material. The pattern's usual cost, unbounded log growth, is neutralized by the text decision: a life of observations fits on a phone.


### 8.3 The strangler fig

A functioning legacy answer engine predates this architecture: scripts/ask_home.py, roughly 2,900 lines, 47 broad exception handlers, and — importantly — real, hard-won answer-quality heuristics that must not be lost in a rewrite. It is not rewritten; it is contained. The Recall use case fronts a RecallBackend port; the LegacyAskHome adapter wraps the old module and translates its output into typed RecallAnswers with citations. Capability by capability — retrieval, dossier assembly, grounding — the new implementations take over behind the same boundary: Fowler's strangler fig [25]. The application layer is honest about the migration's frontier: binder.py, capture_scheduler.py, and grounding_gate.py exist today as named single-line boundary modules for Phases 2, 1, and 3 respectively — the target architecture is visible in the code before it is filled in.


### 8.4 The repository at a glance

Path Role Status src/soma/domain/ seven value types; the vocabulary production, strict-typed, 87% covered src/soma/application/ use cases: Recall, EgressGuard; Phase 1–3 boundaries production + named stubs src/soma/ports/ seven Protocol interfaces production src/soma/adapters/ eventlog, crypto, OCR/VLM/LLM bridges, legacy wrapper mixed: production + boundaries SOMA — AN INPUT-ONLY WEARABLE MEMORY SOFTWARE ARCHITECTURE src/soma/eval/ engine-independent OAG calculation production soma_perception/ live loop: detector, salience scheduler, enricher prototype, Swift-portable core scripts/ legacy engine + migration inputs (build_*.py) strangler source evaluation/ frozen gold sets, RAS/OAG scoring artifacts instrument ops/ north star, roadmap, briefs, runbooks governance soma-native-fastvlm/, apps/ios/ device capture app lineage migration input archive/ retired experiments (relational hub, corrupt-git forensics) archaeology only


### 8.5 What was rejected, and why

Three roads not taken, recorded because the reasons generalize. A microservice decomposition was rejected: the system is one person's memory on one person's device; network boundaries inside it would add failure modes and remove type safety, for zero scaling benefit. A neural/vector-native store as the source of truth was rejected: embeddings are projections here — rebuildable accelerators — because the truth must remain human-auditable text (I4) and replayable (I3). The relational hub — an earlier architecture with a server-backed relational graph at the center — was built, measured, and archived; its lesson (in-process graph writes, no server, phone-library shape) is encoded in the current perception loop's design.

SOMA — AN INPUT-ONLY WEARABLE MEMORY SOFTWARE ARCHITECTURE


## 9 — The Perception Subsystem

Perception is where the economics live. A phone cannot run a deep vision model continuously for sixteen hours; a memory cannot afford to look deeply at nothing. This chapter describes the machinery that spends a fixed attention budget where it buys the most future answer — the component the project regards as its moat.


### 9.1 The cheap stratum: always-on helpers

The base of the stack never sleeps, because it costs almost nothing: – Detection and tracking. A lightweight detector maintains persistent tracks — object identities with dwell, motion, and position statistics — on every gated frame. On the Mac substrate this is a YOLO-family tracker [26]; on device, region proposals feed MobileCLIP-S0 zero-shot naming [27], chosen after an explicit audit: it runs fast on the Apple Neural Engine, emits words not prose, and its vocabulary grows without retraining. The audit's verdict is preserved in ops: the weak link was region proposals, not naming — fix proposals, don't swap the namer.

– OCR reads every legible surface: receipts, screens, signs, labels. Dense text is the single highest-value cheap channel — a receipt is a structured record of a transaction the user will one day ask about.

– ASR transcribes speech continuously [30]; the transcript is the social scaffold of the day. – Sound events name the non-speech world — alarm, cry, hum, latch, espresso machine

[39]; sound is the sense that works around corners and in pockets.

– Sensors — pose, motion, place — are kept losslessly; they are bytes per second and they anchor everything else in space (ARKit world tracking on device [15]).


### 9.2 Salience: deciding what deserves the expensive eye

The scheduler (soma_perception/scheduler.py) is pure logic — no I/O, injected clock, portable 1:1 to Swift. Its inputs are track statistics from the cheap stratum; its outputs are sparse, budgeted enrichment decisions. The scoring function: SOMA — AN INPUT-ONLY WEARABLE MEMORY THE PERCEPTION SUBSYSTEM salience = dwell_progress × (0.6 · novelty + 0.4 · stability) Dwell is attention's signature — what the wearer lingers near matters; novelty front-loads the unfamiliar — the hundredth sighting of the kitchen kettle is worth less than the first crow; stability suppresses motion blur — a deep look at a smear is a wasted token. The weights are starting points, tuned against captured data, not doctrine.


### 9.3 The budget: a token bucket with no overdraft

Enrichment requests spend from a token bucket [28] refilled at a hard hourly rate set by thermal and battery measurement. The bucket is the difference between an architecture and a demo: it is what makes the loop honest about all-day wear. When the bucket is empty, salient moments are simply not enriched — and that loss is visible in evaluation (an (A)-diagnosed miss, Chapter 13), which is exactly how the budget's size gets justified or raised: by evidence.


### 9.4 The progressive enrichment ladder

Depth of attention buys depth of knowledge, in three levels — overview → attributes → minutiae — where each level costs one token and demands roughly 3× the accumulated dwell of the previous: dwell time → knowledge depth → L1 overview  (costs 1 token, ~3× dwell) L2 attributes  (costs 1 token, ~3× dwell) L3 minutiae  (costs 1 token, ~3× dwell) Figure 8 — The progressive enrichment ladder: attention depth buys knowledge depth. Level 1 records what a glance records: category, color, activity. Level 2 is a delta pass — the prompt includes what the graph already knows and asks only for new detail: material, condition, readable text, accessories. Level 3 hunts identifying minutiae: scratches, stickers, wear marks, unique blemishes — the details that make this backpack findable among the world's backpacks. Delta prompting matters twice over: it saves tokens, and it structurally prevents the model from re-asserting (and re-hallucinating) what is already known. A worked scheduler trace SOMA — AN INPUT-ONLY WEARABLE MEMORY THE PERCEPTION SUBSYSTEM The crow's enrichment decision, with the arithmetic visible. At 07:42:06 the track has been alive ~3 seconds; nothing like it has been seen at this anchor before; the bird is still. Input Value Note dwell_progress (toward L1 threshold) 0.75 3s of a 4s L1 requirement novelty 0.9 first corvid at this anchor stability (1 − motion) 0.8 perched; low blur risk salience


### 0.75 × (0.6·0.9 + 0.4·0.8) = 0.65

above the 0.5 decision floor bucket tokens


### 2.3 available

refill 6/hr, last spend 22 min ago decision enrich, level 1, focus "overview" one token spent Contrast the kitchen kettle at 09:15: dwell_progress 1.0 (stared at while waiting), but novelty ≈ 0.05 after a hundred sightings — salience 0.35, below the floor, no token spent. The kettle stays a cheap word; the crow earned a deep look. That asymmetry, repeated thousands of times a day, is the whole attention economy. The prompts encode field-learned humility — "material and brand are often NOT determinable from an image… a confident wrong material is worse than none" — a lesson bought with a real error (a glass phone recorded as plastic) and now enforced in the prompt contract, including the permission to answer exactly: nothing new.


### 9.5 The enricher: expensive eye, delta facts

The enricher consumes the scheduler's decisions: crop + level → local multimodal model (currently Gemma 3 12B, quantized, via Ollama [17][29]) → delta facts written to the graph, in-process, no server. Every emission is a normal Observation with provenance; the expensive eye enjoys no epistemic privilege over the cheap ones — its words meet the same binder and the same confidence discipline as everyone else's.


### 9.6 Honesty about the current frontier

The perception loop runs today on the Mac substrate against recorded and live streams; the device app lineage (soma-native-fastvlm/) is a migration input, not the target. The scheduler's Swift port, the on-device budget measurements, and the live no-raw-persistence gate are Phase 1 work with named gates (Chapter 17). Numbers claimed for the loop — enrichments per hour, battery per hour — appear in the demo script only once measured on device (Chapter 14's governance forbids otherwise).

SOMA — AN INPUT-ONLY WEARABLE MEMORY THE PERCEPTION SUBSYSTEM


## 10 — The Binder: Consolidation as SLEEP


### 10.1 The job

The binder is the night shift: congregate the day's observations, dedupe them, resolve them to entities, and bind them by co-occurrence in time and space — which hum was the laptop fan, which blue thing was the bag, which name belongs to which face. Its input is the immutable log; its output is the evidence graph — a disposable projection (I3). It is the system's answer to the classical binding problem of multi-sensor fusion [16], restated over text with timestamps as the join key.


### 10.2 The contract

Five clauses, each load-bearing: – Co-occurrence is the only join license. Channels are bound by shared when-and-where, never by semantic plausibility alone. Plausibility proposes; co-occurrence disposes. – Every binding carries calibrated confidence (I5), and the evidence tuple that justifies it (I4).

– Weak links are refused, not hardened. Below the floor, a candidate binding is dropped entirely — not stored at low weight, not kept "for later." A graph of hedged maybes is noise wearing structure's clothes; noise in the graph becomes hallucination in the answer.

– Identity resolution accretes; it does not duplicate. Recurring things thicken their node (the crow, Chapter 6); the alternative — a new entity per sighting — dissolves the graph's power to see patterns.

– Derivation is generative. Bindings compose into derived nodes — patterns, habits, locations-of-things — each itself carrying confidence and evidence. This is the 1+1=4 clause, and it is what distinguishes a memory from a log.


### 10.3 Accelerator, not gatekeeper

SOMA — AN INPUT-ONLY WEARABLE MEMORY THE BINDER: CONSOLIDATION AS SLEEP A structural safety property: the graph speeds recall but never bounds it. The reasoner can always fall back to navigating the raw observation scaffold — timeline, egomotion track, per-moment notes — so a bad night's binding can slow answers but cannot destroy information. Consolidation failures are recoverable by replay (I3); this is what makes aggressive experimentation on the binder safe.


### 10.4 The devil's advocate, kept in the room

The project's north star preserves its own counter-arguments, and the binder chapter is where they bite. More signals are not better answers: every added channel is another source of spurious co-occurrence, and an undisciplined binder converts signal wealth into confident nonsense. The refusal floor is therefore not a tuning parameter but the immune system. Most moments don't matter: binding effort follows the same salience gradient as capture. And the diagnosis data (Chapter 13) is blunt about where the work is: the baseline's failures are dominated by binding and reasoning misuse of context already captured — (B) failures — not by missing sensors. The binder is the wall the project is currently climbing, by design and by evidence.


### 10.5 Status

Phase 0's honest report: two binder prototypes produced zero entities and zero bindings — the consensus projection shipped in a follow-on branch is the first to bind for real (36 entities, 58 bindings, 144 weak links refused on the hero walk). The numbers in this document describe the contract and the measured frontier, not a finished component; Chapter 17 places binder completion in Phase 2 with its gate. SOMA — AN INPUT-ONLY WEARABLE MEMORY THE BINDER: CONSOLIDATION AS SLEEP


## 11 — Recall: Grounded Answering with Calibrated Refusal


### 11.1 The loop

A day does not fit a context window, and does not need to. Recall is agentic navigation, not single-shot prompting: the reasoner iterates — consult the timeline, follow the egomotion track, pull deep notes for a candidate moment, cross-check the transcript — until it can answer with citations or must refuse. Structurally this is retrieval-augmented generation [12] hardened into a verification pipeline; operationally it resembles a detective with a case file, not a student with a textbook.


### 11.2 Just enough context

The information supplier's craft is the dossier: the minimal evidence set that lets a small local model answer well. Selection beats volume — a 7–12B model reasons competently over twenty relevant lines and drowns in two thousand irrelevant ones. Every dossier line carries its provenance, so citation is not a post-hoc garnish but a pass-through of what the reasoner actually saw.

A dossier for "why is that crow always on my balcony?", in full: ENTITY crow_1 (animal, "crow") conf .93 — evidence spans tue/wed/fri. B-0917 crow_1 observed_at balcony/railing tue 07:42 conf .87 [ev-4183, ev-4184, ev-4188] B-0954 crow_1 observed_at balcony/railing wed 07:44 conf .89 [ev-5211, ev-5214] B-1033 crow_1 observed_at balcony/railing fri 07:39 conf .90 [ev-7042] B-1035 crow_1 co_occurs_with trash-run (morning routine) conf .81 [tue, wed, fri clusters] CONTEXT trash-run: object "trash bag, in hand" tue 07:42 [ev-4190], wed 07:43 [ev-5213], fri 07:38 [ev-7040] NEGATIVE no crow observations at other anchors; no observations of feeding.

Nine lines. The reasoner answers from these and only these; the citations in its answer are these lines' provenance, passed through. Note the last line: the dossier states relevant absences explicitly, because a model not told "no feeding was observed" will helpfully imagine breadcrumbs.

SOMA — AN INPUT-ONLY WEARABLE MEMORY RECALL: GROUNDED ANSWERING WITH CALIBRATED REFUSAL


### 11.3 The grounding gate

Between draft and user stands the gate (Phase 3; application/grounding_gate.py): claim-level verification that every assertion traces to cited evidence [31]. Drafts with unsupported claims are repaired — the claim is deleted or weakened to what the evidence bears — or the answer becomes a refusal. The gate's design target is the fabrication taxonomy of the hallucination literature [32]: unsupported binary states (the door was locked; the phone was charging), phantom objects imported by prior plausibility, and over-specific detail beyond what was perceived. The legacy engine already carries hand-built versions of these defenses (occupancy-claim gating, phantom-class checks, absence handling); the gate generalizes them into one auditable chokepoint.


### 11.4 Refusal as a calibrated instrument

Refusal is governed by selective-prediction discipline [13]: answer when evidence-supported confidence clears the bar, abstain otherwise, and measure the trade — because RAS subtracts fabrications, the optimal policy under the metric is the honest policy. Refusals are phrased as what they are ("I didn't perceive that") rather than as generic inability, preserving the distinction between the world didn't show me and I failed to find it — a distinction the (A)/(B) diagnosis (Chapter 13) turns into engineering signal.


### 11.5 The text-egress hatch

If local reasoning is the wall — and the north star names this risk explicitly — the architecture permits routing SLEEP binding and ASK reasoning to a stronger text-only model. The hatch is safe by construction: TextEgress is the only shape that fits through it (I2), carrying provenance (I4), so escalation changes who reasons, never what leaves. The decision to open the hatch is a measurement, not a mood: local quality is scored against the same batteries, and the hatch opens when the gap justifies it. Privacy posture is unchanged either way — raw media does not exist to send.

SOMA — AN INPUT-ONLY WEARABLE MEMORY RECALL: GROUNDED ANSWERING WITH CALIBRATED REFUSAL


## 12 — The Privacy Architecture

The moat is that surveillance is architecturally impossible, not promised away. This chapter states the layers, the threat model, and the residual obligations that architecture alone cannot discharge.

ON DEVICE, EPHEMERAL · raw frames (ms lifetime) · raw audio (ms lifetime) · no record path exists PERSISTED / EGRESSABLE · TextEgress: text + source_event_ids · append-only log, AES-256-GCM · auditable, human-readable PERCEPTION + EGRESS GUARD any non-text payload at the wall → PrivacyViolationError Figure 5 — The one-way membrane: meaning crosses, media dies at the wall.


### 12.1 Layer 1 — Ephemerality at the source

Raw media exists in memory for the milliseconds between capture and text extraction. There is no record path: no API in the production capture code writes a frame or an audio buffer to durable storage. Deletion is not a policy here; deletion is not even the right word — nothing is created that would need deleting. (The honesty note of §4.1 applies: legacy clips predating the architecture exist as evaluation oracles, and the live gate that proves the invariant on device is named, scheduled work.)


### 12.2 Layer 2 — The typed boundary

Everything outbound passes EgressGuard.text(), which accepts exactly one type — TextEgress — and raises PrivacyViolationError for anything else. The payload type's own constructor requires non-empty text and non-empty source event IDs, so even legitimate egress is provenance-bearing and auditable. The guard is deliberately tiny: a boundary you can read in one breath is a boundary you can trust an audit of.


### 12.3 Layer 3 — Encryption at rest

SOMA — AN INPUT-ONLY WEARABLE MEMORY THE PRIVACY ARCHITECTURE The text memory itself is encrypted with AES-256-GCM [33] (adapters/encrypted_text.py): SHA-256-derived key, random 96-bit nonce per payload, format version bound as associated data — so ciphertexts authenticate their own container version — with a legacy-format read path for migration. The napkin's phrase — "encryption, i.e. people using our app can decipher" — is this codec: the memory is unreadable to the platform, the cloud, and the thief; readable only to the user's own application holding the user's key.


### 12.4 Layer 4 — Repository and process hygiene

Defense-in-depth extends to the development process: the repository's ignore rules block raw video, audio, and still formats globally; the commit gate verifies zero media binaries staged; the CI gate runs on every push. These are small controls with a large meaning: the team's own workflow is subject to the invariant it ships.


### 12.5 The threat model, tabulated

Threat Storage-first system SOMA Device theft media archive exposed AES-GCM ciphertext; text-only plaintext under user key Cloud breach media archive exposed nothing off-device but guarded text with provenance Subpoena / legal compulsion stored footage discoverable no footage exists; text store is the complete universe Insider access (vendor) policy-limited architecturally empty: no media to access Bystander recording permanent images of non-consenting parties no image persists; bystanders appear only as typed gist Function creep (future feature "re-opens" media) one flag away impossible: the media was never kept


### 12.6 Regulatory alignment

Text-only, minimal, purpose-bound retention is data minimization under GDPR Article 5(1)(c) [6]; capture-time conversion is privacy-by-design in the original, architectural sense

[5]; user-key-only decryption aligns with data-protection-by-default. None of this is claimed

as legal clearance — wearables face jurisdiction-specific recording law — but the architecture starts from the strongest position a perception device can occupy: the sensitive artifact class is never instantiated.

SOMA — AN INPUT-ONLY WEARABLE MEMORY THE PRIVACY ARCHITECTURE


### 12.7 What architecture cannot discharge

Honesty requires the residue stated. Perceiving people into text still touches privacy: "Anna said she's pregnant" is sensitive with no pixel involved. The bystander literature on wearable cameras [34] transfers in part to any wearable perception. Product-level obligations therefore remain: disclosure norms for wearers, redaction policies for bystander speech, retention and export controls in the user's hands, and the wearer's own social contract. The architecture makes the worst artifact impossible; it does not make the remaining ones weightless. This paragraph exists so that no investor, customer, or regulator can say the project hid the residue behind the moat.

SOMA — AN INPUT-ONLY WEARABLE MEMORY THE PRIVACY ARCHITECTURE


## 13 — Evaluation: Every Miss Names the Next Build

Measurement is the most opinionated subsystem in SOMA. It is designed so that failure is never ambient — every miss is attributed, mechanically, to a cause that names the work that fixes it.

REAL CAPTURE walk clip / vlog / day BLIND ADVERSARIAL QUESTION BATTERY ANSWER + CITATIONS + what-brain-looked-at log SCORE RAS / OAG (A) NEVER CAPTURED → build the missing channel (B) BRAIN FAILED TO USE IT → fix bind / retrieval / refusal both branches feed the next capture - nothing is built until a missed question demands it Figure 7 — The measurement loop: every miss is diagnosed (A) or (B) and names the next build.


### 13.1 RAS: fabrication priced like a loss, because it is one

The headline metric over a blind adversarial battery on a real capture: RAS = (correct − made-up) / total A fabricated answer subtracts what a correct one adds; an honest refusal costs nothing. The metric encodes the product ethics (I5) so directly that optimizing the number and behaving honestly are the same act. The qualitative bar attached to it in the north star: a stranger asks about your day and is amazed, with near-zero made-up answers.


### 13.2 OAG: the price of throwing the pixels away

SOMA — AN INPUT-ONLY WEARABLE MEMORY EVALUATION: EVERY MISS NAMES THE NEXT BUILD The oracle-answerability gap (src/soma/eval/oag.py): among questions an offline oracle with the raw frames can answer, the percentage the on-device text memory cannot. OAG is the direct measurement of the retention decision's cost (§2.5) and the falsifier of the central hypothesis (§1.3). Raw media's only legitimate role in the system is here — oracle-side, offline, never entering production recall. The evaluator is engine-independent and tracks tuning exposure per dataset, because an oracle gap measured on a tuned clip is not a measurement.


### 13.3 The (A)/(B) instrument

Every miss is classified: (A) the fact was never captured — the context was not lossless enough — or (B) the fact was in the store and the brain failed to reach, hold, or reason over it. The classification is mechanical, not judged: every answer logs what the brain looked at, so a miss either had the evidence in view or did not. (A) misses authorize new channels (I7); (B) misses direct work to binding, retrieval, or refusal calibration. If a miss cannot be classified, the instrument itself is declared broken — "if we can't tell them apart on a miss, we're blind."


### 13.4 The method: sufficiency, then necessity, then efficiency

Three questions, answered strictly in order, never conflated: – Sufficiency (brute force, offline). On a recorded clip, thermal and token limits do not apply. Throw the kitchen sink — deep VLM on every frame, full pose/GPS track, OCR everywhere, full audio — and ask only: can the brain answer the hard set at approximately zero hallucination at all? This isolates "does the idea work" from "can we afford it."

– Necessity (ablation). Remove one channel at a time; re-score. A removal that breaks no answer is not load-bearing for this battery. The helper set is thereby discovered — open-ended, never capped by a guess — and pruning is measured, never intuited. – Efficiency (last). Only with the necessary set known does the salience scheduler return, to approximate that set within the live budget. Optimizing before sufficiency is proven is how projects die with beautiful, useless engineering.


### 13.5 The current honest baseline

The proving ground is a 92-second outdoor walk with a 25-question adversarial set. Scored honestly from frozen answers: RAS 40.0, hallucination 27.3% — 16 correct, 6 wrong, 3 refused. The diagnosis headline: 8 of 9 misses are (B) — wrong-object binding, SOMA — AN INPUT-ONLY WEARABLE MEMORY EVALUATION: EVERY MISS NAMES THE NEXT BUILD confident-wrong binary states, bad counting, retrieval misses — and only 1 is (A), the head-pose channel that spatial questions demand. Phase 0's report adds the gate output (27 unit tests green, 87% domain/application coverage) and flags its own validation clip as tuning-contaminated rather than quietly promoting it. Two workstreams follow from the numbers, in order of leverage: drive hallucination from 27.3% toward zero by fixing the brain; add egomotion so spatial questions become answerable rather than (correctly) refused.


### 13.6 Anti-overfit machinery

Gold answer keys are hash-pinned (evaluation/gold.lock.json); a silent edit to the answer key breaks the build. Datasets carry tuning-exposure flags. And the pitch-readiness bar includes a cold second capture — never tuned on — passing a private regression check before any external claim, so the live "ask it anything" moment cannot faceplant on distribution shift. The founder battery stays blind: questions are written by someone who has not seen what the system captured.


### 13.7 The self-play flywheel

Question generation itself is automated: an overnight job drives question batteries against the day's memory, mines the misses, and files them into the (A)/(B) queue. The system that answers questions by night also discovers, by night, which questions it cannot answer — turning I7's discipline ("build only what a missed question demands") into a continuously running discovery loop rather than a quarterly ritual.

SOMA — AN INPUT-ONLY WEARABLE MEMORY EVALUATION: EVERY MISS NAMES THE NEXT BUILD


## 14 — Engineering Governance

A two-person company with an ambitious architecture survives on discipline that is cheaper to follow than to break. SOMA's governance is code where possible, ritual where necessary.


### 14.1 The merge gate

One command — make check — enforced identically three ways: locally, as the pre-push hook, and in CI on every push. The gate: formatting and linting (ruff); mypy --strict over domain and application; cyclomatic-complexity and function-length ceilings; dead-code detection (vulture) with zero tolerance in production code; frozen-gold hash verification; the focused evaluator tests; and at least 80% domain/application coverage (87% at Phase 0). The gate is the definition of done — "works on my machine" is not a state the process recognizes.


### 14.2 One source of truth, read first, updated last

The canonical roadmap file governs execution; the north star governs product. Every working session starts by reading them and ends by updating them. The rule exists because the project's early history includes divergence between documentation and reality — including an "acceptance failure" traced to a founder desk-testing a stale build — and the fixes are procedural: a build stamp (git SHA in the app status line and in every posted packet), artifact-level verification by the lead, and the standing instruction to never trust "installed."


### 14.3 The plan-gate and the anti-diversion law

Before any build: name the roadmap item and the missed question that authorizes it (I7). No authorization, no build. The law's origin is a real casualty — the 3D world renderer, built on intuition, needed by no question, killed on diagnosis — and its function is to make that class of detour structurally difficult. Corollaries: pruning is measured (ablation), never aesthetic; and re-evaluation of locked component choices (the namer, the pose stack) requires new diagnostic evidence, not new enthusiasm.

SOMA — AN INPUT-ONLY WEARABLE MEMORY ENGINEERING GOVERNANCE


### 14.4 Honesty as an artifact

Phase reports record what was verified against the live code, including corrections of prior claims; evaluation reports carry their contamination flags; the README states which invariants are proven and which are targets. The document you are reading inherits the same rule — see §4.1, §9.6, §10.5. A pitch built on these artifacts survives due diligence because it is due diligence.

SOMA — AN INPUT-ONLY WEARABLE MEMORY ENGINEERING GOVERNANCE


## 15 — Market Position and the Moat


### 15.1 The quadrant

Two axes organize the field: what persists (raw media ↔ derived text) and where reasoning happens (cloud ↔ device). Screen-recording memory tools, audio pendants, and camera glasses all sit in the raw-persistence half-plane — differing only in which medium they hoard. The text-only, device-perception quadrant is empty, and not by accident: occupying it requires giving up the raw stream, which storage-first architectures cannot do retroactively — their features, their indexes, and their user expectations are built on the archive. An incumbent cannot follow without abandoning its own foundation. That is what makes the position a moat rather than a feature.


### 15.2 The demo that proves the moat

The pitch deliverable is designed to make the architecture felt: a hero capture answered live with citations; the no-raw-media proof panel — frames visibly converting to text and dying, the store shown text-only, surveillance made structurally impossible on stage; the live "ask it anything" kicker where an honest refusal lands as a feature; and one market beat. The audience for the prototype is explicitly one person — the angel — and its job is to prove the moat (architecturally incapable of surveillance) and the market (the empty quadrant, with named acquirers).


### 15.3 Why incumbents want it and cannot build it

For platform acquirers, an input-only memory is the wearable strategy without the surveillance liability that has repeatedly burned camera products. The acquisition logic is strengthened, not weakened, by the moat's nature: the asset is an architecture and its measured evidence — the invariants, the evaluation trail, the scheduler — none of which can be bolted onto a storage-first product without a rewrite indistinguishable from starting over.

SOMA — AN INPUT-ONLY WEARABLE MEMORY MARKET POSITION AND THE MOAT


## 16 — Risks and Open Problems

Stated plainly, ordered by severity, with the mitigation that exists and the trigger that would escalate each.


### 16.1 The central hypothesis may be false

Text may not carry enough of the visual world. Mitigation: OAG exists to measure exactly this; the sufficiency phase brute-forces the best case before efficiency is allowed to constrain it. Escalation trigger: a sufficiency run on a clean capture in which the brute-force text scaffold still misses a material share of oracle-answerable questions — that result would demand rethinking the retention format itself, and no amount of scheduling cleverness would matter.


### 16.2 Hallucination is at 27.3% against an invariant of ~0

The gap between baseline and bar is the project's daily work. Mitigation: the diagnosis says the misses are (B) — binder discipline, retrieval, refusal calibration — all addressable in software against replayable data; the follow-on binder branch already demonstrates mass weak-link refusal. Escalation trigger: hallucination plateauing under a disciplined binder would point at the reasoner, opening the text-egress hatch (measured, I2-safe).


### 16.3 Local models may be the wall

Gemma-12B / Qwen-VL-7B may cap binding or answering quality. Mitigation: the hatch, designed and typed already; the measurement that opens it. Residual: dependence on a frontier vendor for the deep pass — bounded by the fact that only guarded text ever leaves.


### 16.4 The live loop is unproven on device

Battery, thermals, and the no-raw-persistence gate are prospective until the phone rig runs all day. Mitigation: the budget architecture is designed for it (token bucket, measured refill); Phase 1 gates name the numbers to hit. Escalation trigger: measured enrichments-per-hour too low to hold OAG — which would force cheaper deep models or a SOMA — AN INPUT-ONLY WEARABLE MEMORY RISKS AND OPEN PROBLEMS bigger cheap stratum.


### 16.5 Overfit to the hero capture

One clip has dominated tuning. Mitigation: hash-pinned golds, contamination flags, the cold-capture guard. Residual: the guard has not yet been passed; until it is, every quality number in this document is an in-sample number, and says so.


### 16.6 Bystander and social risk

Architecture removes stored media; it does not remove the social fact of being perceived. Mitigation: §12.7's product obligations; disclosure norms; text-level redaction options. Residual: recording-law heterogeneity across jurisdictions — a compliance program, not an architecture patch.


### 16.7 The binder as single point of intellectual failure

If disciplined binding at scale proves intractable — entity resolution degrading over weeks, derived nodes accumulating subtle wrongness — the graph's value proposition erodes. Mitigation: accelerator-not-gatekeeper (the scaffold always answers); replayability (every binder version can be re-run over history); refusal (the graph prefers silence to error). Honesty: this is the research risk. The crow binds cleanly; a life is noisier than a crow. SOMA — AN INPUT-ONLY WEARABLE MEMORY RISKS AND OPEN PROBLEMS


## 17 — Roadmap


### 17.1 Prototype tiers

Tier Definition Horizon V0 Mac-processed, generalizing, trustworthy: record → one command → ask → cited answers days–weeks V1 live, on-device, attention-gated, all-day (phone rig) — the moat made wearable weeks–months Glasses the same architecture in the target form factor months+


### 17.2 Phases and gates

Phase Work Gate 0 — Baseline & instrument pin the hero clip + battery; wire (A)/(B) logging; one source of truth honest baseline + diagnosis log ✔ (done) 1 — Sufficiency brute-force maximal offline capture; agentic brain; score and tag every miss a clean answer to "does lossless context + brain work at all?"

2 — Close (A)s, kill hallucination build only the channels missed questions demand (egomotion first); tighten refusal until made-up ≈ 0 hallucination ~0; spatial answered or honestly refused 3 — Close (B)s navigation/indexing where context was present but unused; measured hatch if needed no unexplained (B) failures on the set 4 — Necessity & harden ablate to load-bearing channels; moat-proof panel; cold-capture guard anti-overfit green; minimal channel set known 5 — Package demo script + moat proof + market beat, rehearsed end to end founder runs the pitch alone SOMA — AN INPUT-ONLY WEARABLE MEMORY ROADMAP


### 17.3 The founder's rituals

The division of labor is explicit: human hands record clips (with real sensor streams), write and extend adversarial questions, run one command, and occasionally capture what a diagnosed miss demands. Everything else — pipeline, helpers, ablation, scoring, night-bind, bookkeeping — is the machine's, around the clock. The system is built to need its founders for judgment, not for labor.

SOMA — AN INPUT-ONLY WEARABLE MEMORY ROADMAP


## 18 — Objections and Responses

Every serious reader of this architecture raises a version of the same dozen objections. They deserve direct answers, in one place, at full strength. Where an objection is partially right, the response says so.


### 18.1 "If you throw away the pixels, you'll throw away the

answer."

The strongest objection, and the one the whole evaluation apparatus exists to face. Response: it is a measurable claim, not a debate. OAG quantifies exactly the questions the raw-frame oracle answers that the text cannot; the sufficiency phase maximizes the text side before any efficiency constraint is allowed to bite; and the enrichment ladder exists precisely to spend deep perception where tomorrow's question is likeliest to land. The honest current state: the measured gap is real (Chapter 13), and the diagnosis says most of it is the brain's misuse of captured text, not missing capture. If the gap ever proves irreducible at the sufficiency limit, the hypothesis is falsified and the project's premise fails — a possibility this document states in its own risk register (§16.1) rather than hiding. What the objection cannot claim is that the alternative escapes the problem: storage-first systems defer extraction, they do not solve it, and they pay the surveillance price forever while deferring.


### 18.2 "A verbal description of a scene is a pale shadow of the

scene."

True — and the wrong comparison. The competitor is not the scene; it is human memory of the scene, which is itself a sparse verbal-categorical trace reconstructed on demand [1][2]. SOMA does not need to beat the videotape; it needs to beat the wearer's own recollection, with citations, at near-zero fabrication. That bar is high in trustworthiness and low in visual fidelity — exactly the trade the architecture makes.


### 18.3 "People will not wear a camera, period."

SOMA — AN INPUT-ONLY WEARABLE MEMORY OBJECTIONS AND RESPONSES The social objection. Response: people already carry always-on microphones and cameras in their pockets and on their wrists; what they reject — and what jurisdictions legislate against — is retention and replay. SOMA's answer is not "trust us" but "there is nothing to distrust": no stored image of any bystander exists one second after the moment. That claim is demonstrable on stage (the no-raw-media proof panel) and auditable in code (eleven lines of egress guard). It may still fail socially — §12.7 and §16.6 keep that residue on the books — but it fails from a categorically stronger position than any recording device.


### 18.4 "Local models are too weak to bind a day correctly."

Possibly. The architecture's response is the measured hatch: binding and answering can escalate to a frontier text-only model with the privacy posture unchanged, because text was the only thing allowed out from the first commit (I2). The decision is a benchmark delta, not a philosophy: local is preferred, cloud-text is permitted, raw egress is impossible. The objection's teeth are economic (cloud inference costs money), and the mitigation is the same as everywhere in this design: spend depth only where salience earns it.


### 18.5 "The graph will silt up with garbage over months."

The scaling objection to consolidation, and the project's honest research risk (§16.7). Three structural answers: weak-link refusal keeps coincidence out of the graph at write time; projections are disposable, so a better binder can re-marinate history at any time (I3); and the graph is an accelerator, never a gatekeeper — recall can always fall back to the raw scaffold. What these do not answer is whether any binder discipline holds at life-scale; that is what the phased evaluation is for.


### 18.6 "Why not just embeddings? Vector search over frames is

simpler."

Embeddings are in the system — as projections, rebuildable accelerators for retrieval. They are disqualified from being the truth for three reasons: they are not auditable by the owner (no one can read what a vector of their kitchen contains); they are not citable at the claim level (I4); and they freeze a model's worldview into the store (a new encoder means re-embedding, which is fine for an index and catastrophic for a memory). Text is the only format that is simultaneously queryable, auditable, citable, and model-independent.


### 18.7 "OCR/ASR errors will poison the memory."

They will enter it — every channel is noisy. The defenses are layered: per-observation confidence at capture; cross-channel corroboration at binding (an OCR misread that nothing SOMA — AN INPUT-ONLY WEARABLE MEMORY OBJECTIONS AND RESPONSES else co-occurs with binds to nothing); the refusal floor at answer time; and the refutation-cue field on observations, which invites later evidence to overturn earlier error. The design position: noise in an auditable text store is a manageable disease; noise in an unauditable one is undiagnosable.


### 18.8 "This is just RAG with extra steps."

The ASK stage is RAG-shaped, and the document says so [12]. The extra steps are the product: a corpus that is machine-perceived under a privacy invariant rather than scraped; provenance as a type obligation rather than a convention; refusal as a scored, calibrated outcome rather than a failure; and a nightly consolidation layer that RAG systems do not have because their corpora do not accrete a life. Dismissing a system by naming its weakest structural analogy is a category of critique this chapter welcomes — it is how the 3D renderer died — but here the analogy covers one of eight stages.


### 18.9 "The salience scheduler will miss the moment that

matters."

Sometimes it will — a budget is a bet. Two answers. First, the cheap stratum never blinks: OCR, ASR, sounds, and sensors record continuously, so a missed deep look is a degraded memory, not an absent one. Second, every such miss is visible: it surfaces as an (A)-diagnosed failure in evaluation, and the budget, weights, or ladder thresholds move in response (I7). The scheduler is not claimed optimal; it is claimed instrumented — its errors are the training signal for its own next version.


### 18.10 "Encryption with the vendor holding no key means no

recovery."

Correct, and chosen. A memory this intimate with a vendor-side recovery path is a memory with a second reader. The design accepts the consumer-grade consequence (lose the key hierarchy, lose the memory) in exchange for the categorical claim (§12.3); key-escrow-by-user-choice can exist as product surface without weakening the default.


### 18.11 "Two people cannot build this."

The scope objection. The architecture is its own answer: a domain layer small enough to read in a sitting; one substrate at a time behind ports; a legacy engine strangled rather than rewritten; a machine that generates its own backlog from missed questions and runs its own night shifts (self-play, auto-grading, ablation). The governance chapter is not process theater — it is how a two-person team rents the discipline of a larger one. The risk that remains is SOMA — AN INPUT-ONLY WEARABLE MEMORY OBJECTIONS AND RESPONSES focus, and the anti-diversion law exists because the team has already paid once for losing it.


### 18.12 "Why would anyone pay for honest refusals?"

Because the alternative is confident fabrication about their own life, and one such fabrication ends the relationship with the product. Refusal is not the product; trust is, and refusal is trust's price. The demo bets on this directly: the "ask it anything" kicker treats an honest "I didn't perceive that" as a feature moment. If users in fact prefer comfortable invention to honest silence, then this product should not exist — and its founders would rather learn that than build the alternative.

SOMA — AN INPUT-ONLY WEARABLE MEMORY OBJECTIONS AND RESPONSES


## 20 — The desk pillar's gaze economy: attention as an auction *(revision 1.1)*

Chapter 9 stated the attention economy as a design: a cheap always-on stratum
deciding what deserves the expensive eye. Between version 1.0 and this
revision, the desk pillar (the Mac sibling of the wearable, sharing every
invariant of Chapter 4) BUILT that economy and put it under test. This chapter
records the mechanism as it exists, because several of its laws were not
designable in advance — they were found by building, and a thesis that omits
them would flatter the design.

### 18.1 The organs

The eye is not a camera pipeline; it is a gaze. A **retina** holds the raw
stream in a short ring — I1 (no raw persistence) enforced mechanically: pixels
die in seconds, and a deep look in progress must PIN its scene or lose it.
**Peripheral vision** watches the complete stream cheaply and continuously,
emitting only two facts: *something changed here* and *this scene has been
still for N seconds* — and it measures its own true coverage rate rather than
assuming it, so the system's blind spots are numbers, not hopes. A **fovea**
allocates the expensive looks. Nothing above the retina is permitted to think
in frames; consumers ask for "the scene now," never "frame N." The lineage is
classical — attention as selective allocation over a saliency landscape [15,
41] — but the allocation mechanism is economic rather than heuristic.

### 18.2 The auction

Every consumer of perception declares a two-sided **diet contract**: what it
wants to eat and what it will pay attention for. Change events and standing
hungers become bids; each beat runs a sealed, winner-take-all auction; the
winning gaze is executed once and its meal broadcast to every subscribed
consumer. Losing bids age upward so persistent hungers eventually beat fresh
noise — starvation is priced away rather than special-cased. One law emerged
the hard way and is now enforced by a test: **no specialist is architecture**.
Every stall in the marketplace must be droppable without the system noticing
(the "bias law," born from over-fitting perception to a chess demo). The test
drops each stall and asserts the organism's behavior is unchanged minus that
stall's own claims.

### 18.3 The dwell ladder and the Nutella law

A scene that persists earns *deepening*, never repetition. L0 glances (what is
this); L1 reads (the words, with coordinates); L2 studies (the jar is 1 kg,
three-quarters empty, lid ajar); L3 infers (a German label suggests where its
owner lives). Each level receives everything already extracted and must return
only the delta against a **novelty ledger** — a still screen over minutes
yields monotonically growing nuance and zero repeated facts, and the oracle
asserts exactly that. This is progressive refinement under a prediction-error
economy: look longer only where the model of the scene is still being
surprised [42, 49].

### 18.4 The ceiling

Extraction quality is measured against a frontier model's maximum extraction
from the same scene — the **ceiling**. A miss shared by product and ceiling
counts against neither; the ceiling is the limit, not a competitor. As of this
revision the desk pillar's L1 verbatim gap to ceiling, measured across the
banked frame corpus, is **0.026**. The frontier also serves, during
development only and by explicit founder ruling, as a stand-in organ for L2/L3
— with a product-cut drill (delete the gateway; everything must still run
local) enforcing that the stand-in dies before shipment (I2 preserved at
product time).

### 18.5 The live-only theorem

Because raw dies at the membrane (I1) and the night shift eats text only, any
relation visible *only* in raw material — motion correlation, sound direction,
lip-sync — must be bound in daylight or it is lost forever. This is a theorem
of I1 plus the closed pantry, not a preference; it dictates which bindings the
live beat must compute before the pixels die, and it is written into the
binder's contract as such.

## 21 — Laws the cell taught us: identity, birth, and night *(revision 1.1)*

The graph of Chapter 7 is typed evidence; the desk pillar's node layer put a
*living* cell on top of it — born, warmed, combined, pruned. Building it
surfaced laws that belong in this document precisely because none of them were
in the design.

### 19.1 Identity never merges under uncertainty

Person nodes are **instances, not names**: two Sams remain two nodes forever.
Anonymous people are **per-context ghosts**, never one global bucket. And the
resolver's failure posture is asymmetric by law: a wrong split is a cheap,
reversible repair (a SAME-AS edge is meta), while a wrong merge poisons every
future sighting and cannot be undone in place — so below the confidence bar
the resolver attaches *nothing* and a question carries the fork to the owner,
naming both candidates. Answered questions land as verbatim truth and heal the
graph mechanically.

### 19.2 Ubiquity cannot vouch

Naive spreading activation [43] merged two strangers through a shared web
browser. The fix is an inverse-ubiquity weighting on context overlap: a node
that co-occurs with everything identifies nobody. Your home Wi-Fi cannot vouch
for anyone; the pottery kiln can. The same principle recurs at combination
level: a *place* may not be the via-node of a co-occurrence chain, because
everything co-occurs at home — "A and B are both often at home" is trivia
wearing the costume of a derivation.

### 19.3 Newborns are born warm

Derived nodes initially entered the graph at zero activation — and the same
night that created them pruned them as cold. The law: a fresh derivation is
the most recently *thought* thing in the graph and is born warm. Its rent
(Chapter 10's judge: cite your sources and survive checks, or don't exist)
still falls due; warmth buys it a fair trial, not immortality.

### 19.4 Contradiction fires only on functional keys

An entity legitimately accumulates many topics, many sightings, many
co-occurrences; firing the contradiction machinery on multi-valued
observational keys stole the causal engine's turn every night. Contradiction
is now scoped to *functional* keys — attributes for which two values are
impossible (a phone number, a color, a title). The general lesson: the cell's
organs compete for the night's budget, and mis-typing one attribute class can
silently starve another organ.

### 19.5 The night, mapped to its biology

The night shift runs an economy in fixed order: succession (temporal edges),
schema refit (routines crystallize; deviation becomes surprise), **mining** —
each hungry node re-reads its own raw with today's understanding — then
combination, then pruning with re-derivation rights. The order is the
complementary-learning-systems story told mechanically [44]: fast episodic
capture by day, slow structured consolidation by night [45, 46]. Where
biology reconsolidates destructively and confabulates [17, 48], this
architecture re-derives from immutable raw — failed thinking is discarded,
never the material it thought about. And spacetime as the primary key of every
record — meaning attaches later and can always find its way home — is the
cognitive-map thesis [47] applied as a storage schema.

## Appendix W — Witnessed status of the desk pillar (2026-07-20)

Numbers below are witnessed outputs, not projections; each has a command and a
log behind it in the desk repository's board.

- Suite: **274 passed, 1 xfailed** — the single xfail is the VLM specialist
  eye, gated by the one-GPU law, not by missing work.
- **The core loop has run end-to-end on lived data**: live screen → auction
  chose the gaze → Vision read it → claims went durable in the encrypted log →
  a natural-language question about that lived moment returned cited, graded,
  timestamped evidence — carrying an honest 0.30 confidence on a shaky read
  rather than a confident fabrication (I5 exercised in anger).
- Perception bank: **181 golden frames** auto-captured during the founder's
  normal work; **111 frontier ceiling extractions** over **4,674 claims**;
  L1-verbatim gap to ceiling **0.026**.
- The ear is real (CPU-only, word timestamps, honest confidence) — and its
  first measured word-error ("kiln" heard as "kill" at 0.66 confidence on
  clean audio) is preserved as the standing justification for owner-voice
  measurement before any engine is trusted.
- The build map: **489 tracked parts, 43 open design questions**, every part
  carrying its own work order, proof criterion, and prerequisites.
- Unproven, stated plainly: the never-lies contract against a real local
  model (0% tested — the hardest open loop); identity resolution on real
  weeks; and the two load-bearing bets of §1.3, which only banked weeks of
  real life can settle.

## References

[1] E. Tulving, "Episodic and Semantic Memory," in Organization of Memory, Academic Press, 1972;

and Elements of Episodic Memory, Oxford University Press, 1983.

[2] F. C. Bartlett, Remembering: A Study in Experimental and Social Psychology, Cambridge University

Press, 1932.

[3] J. G. Klinzing, N. Niethard, J. Born, "Mechanisms of systems memory consolidation during sleep,"

Nature Neuroscience 22, 1598–1610, 2019. doi:10.1038/s41593-019-0467-3

[4] J. M. Zacks, N. K. Speer, K. M. Swallow, T. S. Braver, J. R. Reynolds, "Event perception: a

mind-brain perspective," Psychological Bulletin 133(2), 273–293, 2007.

[5] A. Cavoukian, Privacy by Design: The 7 Foundational Principles, Information & Privacy

Commissioner of Ontario, 2009.

[6] Regulation (EU) 2016/679 (General Data Protection Regulation), Article 5(1)(c) — data minimisation.

gdpr-info.eu/art-5-gdpr

[7] T. Brown et al., "Language Models are Few-Shot Learners," NeurIPS, 2020. arXiv:2005.14165

[8] L. Itti, C. Koch, "Computational modelling of visual attention," Nature Reviews Neuroscience 2,

194–203, 2001.

[9] J. Gemmell, G. Bell, R. Lueder, "MyLifeBits: a personal database for everything," Communications of

the ACM 49(1), 88–95, 2006. doi:10.1145/1107458.1107460

[10] S. Hodges et al., "SenseCam: A Retrospective Memory Aid," Proc. UbiComp, 177–193, 2006.

doi:10.1007/11853565_11

[11] K. Grauman et al., "Ego4D: Around the World in 3,000 Hours of Egocentric Video," Proc. CVPR,

2022. arXiv:2110.07058

[12] P. Lewis et al., "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks," NeurIPS,

2020. arXiv:2005.11401

[13] A. Kamath, R. Jia, P. Liang, "Selective Question Answering under Domain Shift," Proc. ACL, 2020.

arXiv:2006.09462

[14] A. Hogan et al., "Knowledge Graphs," ACM Computing Surveys 54(4), 1–37, 2021.

arXiv:2003.02320

[15] Apple Inc., ARKit documentation: ARWorldMap, world tracking and relocalization.

developer.apple.com/documentation/arkit

[16] D. L. Hall, J. Llinas, "An introduction to multisensor data fusion," Proceedings of the IEEE 85(1),

6–23, 1997.

[17] Gemma Team, Google DeepMind, "Gemma 3 Technical Report," 2025. arXiv:2503.19786

SOMA — AN INPUT-ONLY WEARABLE MEMORY REFERENCES

[18] Qwen Team, Alibaba Group, "Qwen2.5-VL Technical Report," 2025. arXiv:2502.13923

[19] E. Evans, Domain-Driven Design: Tackling Complexity in the Heart of Software, Addison-Wesley,

2003.

[20] C. Guo, G. Pleiss, Y. Sun, K. Q. Weinberger, "On Calibration of Modern Neural Networks," Proc.

ICML, 2017. arXiv:1706.04599

[21] A. Cockburn, "Hexagonal Architecture (Ports and Adapters)," 2005.

alistair.cockburn.us/hexagonal-architecture

[22] R. C. Martin, Clean Architecture: A Craftsman's Guide to Software Structure and Design, Prentice

Hall, 2017.

[23] M. Fowler, "Event Sourcing," martinfowler.com/eaaDev/EventSourcing.html, 2005.

[24] M. Fowler, "CQRS," martinfowler.com/bliki/CQRS.html, 2011.

[25] M. Fowler, "Strangler Fig Application," martinfowler.com/bliki/StranglerFigApplication.html, 2004

(updated 2024).

[26] J. Redmon, S. Divvala, R. Girshick, A. Farhadi, "You Only Look Once: Unified, Real-Time Object

Detection," Proc. CVPR, 2016 (arXiv:1506.02640); Ultralytics YOLO documentation, docs.ultralytics.com.

[27] P. K. A. Vasu, H. Pouransari, F. Faghri, R. Vemulapalli, O. Tuzel, "MobileCLIP: Fast Image-Text

Models through Multi-Modal Reinforced Training," Proc. CVPR, 2024. arXiv:2311.17049

[28] A. S. Tanenbaum, D. J. Wetherall, Computer Networks, 5th ed., Pearson, 2011 — §5.4, token-bucket

traffic shaping.

[29] Ollama — local large-model runtime. ollama.com

[30] A. Radford, J. W. Kim, T. Xu, G. Brockman, C. McLeavey, I. Sutskever, "Robust Speech

Recognition via Large-Scale Weak Supervision (Whisper)," Proc. ICML, 2023. arXiv:2212.04356

[31] B. Bohnet et al., "Attributed Question Answering: Evaluation and Modeling for Attributed Large

Language Models," 2022. arXiv:2212.08037

[32] Z. Ji et al., "Survey of Hallucination in Natural Language Generation," ACM Computing Surveys

55(12), 1–38, 2023. arXiv:2202.03629

[33] M. Dworkin, NIST Special Publication 800-38D: Recommendation for Block Cipher Modes of

Operation — Galois/Counter Mode (GCM) and GMAC, NIST, 2007. doi:10.6028/NIST.SP.800-38D

[34] R. Hoyle, R. Templeman, S. Armes, D. Anthony, D. Crandall, A. Kapadia, "Privacy behaviors of

lifeloggers using wearable cameras," Proc. UbiComp, 571–582, 2014. doi:10.1145/2632048.2632079

[35] D. O. Hebb, The Organization of Behavior: A Neuropsychological Theory, Wiley, 1949.

[36] V. Bush, "As We May Think," The Atlantic Monthly, July 1945.

[37] C. Gurrin, A. F. Smeaton, A. R. Doherty, "LifeLogging: Personal Big Data," Foundations and

Trends in Information Retrieval 8(1), 1–125, 2014.

[38] Apple Machine Learning Research, "FastVLM: Efficient Vision Encoding for Vision Language

Models," Proc. CVPR, 2025. arXiv:2412.13303 SOMA — AN INPUT-ONLY WEARABLE MEMORY REFERENCES

[39] J. F. Gemmeke et al., "Audio Set: An ontology and human-labeled dataset for audio events," Proc.

ICASSP, 2017.

[40] S. Newman, Monolith to Microservices, O'Reilly, 2019 — on strangler-style incremental migration.

Internal primary sources (SOMA repository) ops/NORTH_STAR.md — product source of truth: the three-stage machine, the attention principle, metrics, prototype tiers, honest critiques.

ops/ROADMAP.md — canonical implementation spec: central hypothesis, the (A)/(B) instrument, sufficiency→necessity→efficiency, phases and gates, the anti-diversion law. ops/MARKET_AND_SCOPE.md — quadrant analysis, named acquirers, scope boundaries. ops/enrichment_scheduler_design.md — salience scheduler design note (Swift portability contract).

docs/PHASE0_REPORT.md — verified Phase 0 state: gate output, coverage, known debt, contamination flags.

README.md — orientation; locked architecture decisions; current privacy status. docs/interactive/soma-architecture.html — the interactive companion to this document: live node graph, the crow example, the membrane.

SOMA — AN INPUT-ONLY WEARABLE MEMORY REFERENCES APPENDIX A The Napkin, Transcribed and Mapped The founding sketch, transcribed line by line, with each phrase's production counterpart. The napkin reads top-to-bottom as two blocks: the "Standard Model" header and the EXECUTION pipeline.

A.1 The Standard Model block "World → Senses (Eyes, Ears, Organs) → Brain. Standard Model. (Because we can't manufacture other senses, or most of the information is obtained through this.)" Mapped: Chapter 2's epistemology. Eyes and ears become camera and microphone; "organs" becomes the sensor suite (pose, motion, place) — the one sense the phone can manufacture beyond sight and sound, and the one that answers spatial questions. A.2 The EXECUTION block, phrase by phrase Napkin phrase Production meaning Where "World → Video (Eyes), Audio (Ears)" capture substrate, always-on cheap senses Ch. 5.1, 9.1 "Extraction Black Box" frame gating + scaffold stamping Ch. 5.2 "Coordinates, time stamps" the spatio-temporal scaffold on every datum Ch. 7.1–7.2 "Blurry frames discarded, Signal–Noise deciphered" + "Context" quality gating; context rides with every emission Ch. 5.2 "A macro picture of what's happening ⇒ VLM" salience-gated scene gist Ch. 5.3, 9.4 "A specialized eye or helper for various tasks; called as needed" the helper stratum: OCR, ASR, sounds, detector Ch. 5.4, 9.1 "Best understanding possible of the world → TEXT" typed open-vocabulary observations Ch. 5.5, 7.1 "Text from various helpers marked by coordinates" provenance + anchors on every line Ch. 7.2 SOMA — AN INPUT-ONLY WEARABLE MEMORY THE NAPKIN, TRANSCRIBED AND MAPPED "Binder ⇒ binding the coordinates, physicality & temporality together" co-occurrence fusion Ch. 5.6, 10 "First thought or raw material that can be marinated on. Note: this is not a complete Node, it's raw material" append-only observation log as episodic store Ch. 5.6, 8.2 "Node Creation Black Box" consolidation → evidence graph Ch. 5.7, 10 "A physical living breathing cell that can combine with fellow nodes to derive new things — 1+1=4 ≠ 2" entities + derived bindings; the crow's habit node Ch. 6.7, 10.2 "Always running in the background but better nightly" incremental + nightly binding Ch. 2.3, 10.3 "Encryption, i.e. people using our app can decipher" AES-256-GCM user-key codec Ch. 12.3 "Discarder of meta, i.e. the marinated content that's not useful is discarded, not the raw material" disposable projections over an immutable log Ch. 8.2, I3 "Information Supplier Black Box" recall retrieval + grounding gate Ch. 5.8, 11 "Just Enough Context for local LLM" the evidence dossier Ch. 11.2 "LLM does what LLM does" commodity reasoner at the end of the pipe Ch. 11.1 Nothing on the napkin failed to survive contact with implementation; what changed is that every phrase acquired a type, a file, and a test.

SOMA — AN INPUT-ONLY WEARABLE MEMORY THE NAPKIN, TRANSCRIBED AND MAPPED APPENDIX B Glossary Term Definition Observation one typed, provenance-bearing emission from a perceiver; the atom of memory Provenance (event id, source channel, capture time) — the birth certificate of any datum Confidence a probability in [0,1], intended calibrated; the currency of trust Entity a stable identity (crow_1) that observations resolve to Binding a subject–predicate–object edge with confidence and evidence Derived node a binding produced from other nodes, not from a sensor (the 1+1=4 output) Evidence graph the disposable projection of entities and bindings built from the log Event log the append-only, immutable store of all observations; the single source of truth Projection any structure derived from the log; rebuildable, discardable Helper a narrow, cheap, always-on perceiver (OCR, ASR, sound events, detector) Salience dwell × (0.6·novelty + 0.4·stability); what earns the expensive eye Enrichment ladder overview → attributes → minutiae; depth of attention buys depth of knowledge Token bucket the hard hourly budget governing deep looks Binder the consolidation process fusing observations by co-occurrence Night shift / SLEEP the nightly deep binding pass Weak-link refusal dropping (not down-weighting) any binding below the confidence floor SOMA — AN INPUT-ONLY WEARABLE MEMORY GLOSSARY Dossier the just-enough-context evidence package handed to the reasoner Grounding gate claim-level verification that every assertion traces to citations TextEgress the only type allowed off-device: text + source event ids EgressGuard the runtime wall that rejects any non-TextEgress payload RAS (correct − made-up)/total on a blind adversarial battery OAG of oracle-answerable questions, the share the text memory cannot answer (A) miss the fact was never captured — build the missing channel (B) miss the fact was captured but unused — fix binding/retrieval/refusal Hero capture the pinned proving-ground clip with its frozen question set Cold capture a never-tuned-on recording used as the anti-overfit guard Strangler fig incremental replacement of the legacy engine behind a stable boundary The napkin the founding sketch; transcribed in Appendix A SOMA — AN INPUT-ONLY WEARABLE MEMORY GLOSSARY APPENDIX C The Domain Model, Formally The complete public surface of src/soma/domain/, stated as contracts. (The code is the authority; this listing is for readers without the repository.) Attribute(name: str, value: str) — rejects empty name or value. Provenance(event_id: str, source_channel: str, captured_at_ms: int ≥ 0) — rejects empty ids/channels, negative times.

Confidence(value: float ∈ [0,1]) — rejects out-of-range.

Observation(kind: str, subject: str, attributes: tuple[Attribute,...], t_ms: int ≥ 0, spatial_anchor: str|None, confidence: Confidence, provenance: Provenance, refutation_cue: str|None = None) — rejects empty kind/subject, negative t, and t_ms ≠ provenance.captured_at_ms.

Entity(entity_id: str, kind: str, label: str) — rejects any empty field. Binding(binding_id: str, subject_id: str, predicate: str, object_id: str|None, object_text: str|None, confidence: Confidence, evidence: tuple[Provenance,...]) — rejects empty identity fields; requires exactly one of object_id/object_text; requires non-empty evidence. Method: is_usable(minimum_confidence) → confidence.value ≥ floor.

Query(text: str) — rejects empty. Citation(node_id: str, t_ms: int|None). RecallAnswer(text: str, citations: tuple[Citation,...]).

TextEgress(text: str, source_event_ids: tuple[str,...]) — rejects empty text or empty sources. The application-layer counterpart: EgressGuard.text(payload) raises PrivacyViolationError unless payload is a TextEgress.

Ports (Protocols): Perceiver.perceive(payload, captured_at_ms) → tuple[Observation,...] · Ocr.read(pixels) → tuple[str,...] · Asr.transcribe(audio) → str · VlmRunner.describe(pixels) → str · TextReasoner.reason(prompt) → str · MemoryStore.append(obs) / .observations() · RecallBackend.answer(query, memory_reference) → RecallAnswer.

SOMA — AN INPUT-ONLY WEARABLE MEMORY THE DOMAIN MODEL, FORMALLY APPENDIX D The Evaluation Instrument D.1 Shape of a question battery Each hero capture carries a frozen adversarial set (~25 questions) spanning: object identity and attributes ("what brand was my backpack?"), text in the world ("what did the laptop screen say?"), audio facts ("what did the announcement say?"), spatial relations ("which side of the platform was the bench on?"), binary states ("was the station crowded?" — gold: no, empty), counting, absence/negation ("did I see a dog?" — gold: no), and unanswerables planted to reward refusal. Gold keys carry acceptable-answer lists and are hash-pinned; founder verdicts resolve disputes; questions are written blind to what the system captured. D.2 Scoring a run Each answer is graded correct / wrong / refused; wrong answers asserting unperceived facts count as made-up. RAS = (correct − made-up)/total. In parallel, the oracle (a strong model with the raw clip) answers the same battery; OAG = among oracle-correct questions, the fraction the text memory missed. Every miss receives an (A)/(B) tag from the what-the-brain-looked-at log. A run's report is: RAS, hallucination rate, OAG, the tagged miss list — and, per I7, the miss list is the backlog.

D.3 The walk baseline, as a worked scorecard The 92-second outdoor walk, 25 questions, frozen June answers: 16 correct, 6 wrong, 3 refused → RAS 40.0, hallucination 27.3%. Diagnosis: 8/9 misses (B) — wrong-object bindings (three questions), confident-wrong binaries (zip state, draft state), one counting failure, two retrieval misses; 1/9 (A) — head-pose for the two spatial questions, correctly refused rather than fabricated. Consequence, already executed in the follow-on branch: a consensus binder with weak-link refusal (36 entities / 58 bindings / 144 refusals on this clip) and cited answers on the previously-missed screen-text and brand questions — with egomotion capture queued as the sole sensor build the data authorizes. SOMA — AN INPUT-ONLY WEARABLE MEMORY THE EVALUATION INSTRUMENT APPENDIX E Annotated Bibliography The bibliography, re-read with intent: for each cluster of sources, what it establishes and which SOMA decision rests on it.

E.1 Memory science Tulving [1] establishes the episodic/semantic distinction that SOMA's two stores mirror: the time-stamped observation log is episodic (events located in time and place), the bound evidence graph is semantic (consolidated knowledge). The mapping is load-bearing, not decorative — it predicts the interface between the stores: consolidation runs episodic→semantic, never the reverse, exactly as the binder reads the log and never writes it. Bartlett [2] demonstrates that human recall is reconstructive and schema-driven — people confidently invent congruent detail. This is simultaneously SOMA's permission (a words-only memory is not a diminished memory; it is how memory works) and its warning (reconstruction without evidence discipline is confabulation — hence the grounding gate). Klinzing, Niethard & Born [3] review sleep-dependent systems consolidation: the brain replays and integrates by night because deep integration and live perception compete for the same machinery. SOMA's night shift is the same scheduling theorem applied to silicon thermals. Zacks et al. [4] show perception segments experience at change boundaries and encodes richly there — the cognitive license for gated deep capture. Hebb [35] supplies the binder's slogan and its mechanism: co-occurrence-driven association. Itti & Koch [8] formalize salience as the currency of visual attention; the scheduler's dwell-novelty-stability score is a wearable-economics translation of that literature. E.2 Lifelogging and egocentric vision Bush [36] is the genre's founding document; its sixty-year lesson is that capture without retrieval-of-meaning is a landfill. Gemmell, Bell & Lueder [9] proved it empirically at life scale: MyLifeBits' bottleneck was never storage but structure. Hodges et al. [10] proved the opposite pole: even passive photo capture aids real memory (clinically), while every deployment surfaced the social cost of visible storage. Hoyle et al. [34] quantify that cost from the wearer's side — lifeloggers themselves censor, delete, and manage bystander exposure. Gurrin, Smeaton & Doherty [37] survey the field and converge on SOMA — AN INPUT-ONLY WEARABLE MEMORY ANNOTATED BIBLIOGRAPHY cues-and-facts over archives. Together these four justify SOMA's inversion: total capture, linguistic retention. Grauman et al. [11] (Ego4D) define the benchmark tasks SOMA's question batteries descend from and establish that long-horizon egocentric retrieval is hard even with the video — the context for reading OAG numbers honestly. E.3 Language models, retrieval, and honesty Brown et al. [7] mark text's coronation as the interlingua of machine reasoning — the substrate bet of §2.5. Lewis et al. [12] define the retrieve-then-generate shape of the ASK stage. Bohnet et al. [31] formalize attribution — answers that cite — as an evaluable property, which SOMA promotes from evaluation criterion to type obligation. Kamath, Jia & Liang [13] ground selective prediction: answering only above a confidence bar, measured as a risk-coverage trade — the formal frame for refusal. Guo et al. [20] show modern networks are miscalibrated by default and calibration must be measured and repaired — why Confidence is a contract, not a float. Ji et al. [32] taxonomize hallucination; the grounding gate's checklist (unsupported binaries, phantom objects, over-specificity) is that taxonomy operationalized.

E.4 Software architecture Cockburn [21] and Martin [22] supply the dependency discipline that keeps the domain pure and the substrates swappable. Evans [19] supplies the value-object doctrine — invariants enforced at construction — that makes invalid memory unrepresentable. Fowler

[23][24][25] supplies the three patterns that structure the monolith: event sourcing (the

append-only log as truth), CQRS-style projections (disposable understanding), and the strangler fig (the legacy engine's containment). Newman [40] documents strangler migrations at industrial scale. Tanenbaum & Wetherall [28] is the token bucket's textbook home.

E.5 Models and systems Redmon et al. / Ultralytics [26] — the always-on detector lineage. Vasu et al. [27] — MobileCLIP, the audited choice for on-device zero-shot naming: ANE-fast, words-not-prose, vocabulary growth without retraining. Radford et al. [30] — Whisper, the ASR default. Gemmeke et al. [39] — AudioSet, the ontology behind sound-event tagging. Gemma Team [17] and Qwen Team [18] — the local reasoner and VLM. Apple FastVLM [38] — the device-side VLM lineage in the app's history. Apple ARKit [15] — 6-DOF pose and relocalization, the egomotion substrate. Dworkin [33] — AES-GCM, the store's encryption. Hall & Llinas [16] — the multisensor-fusion frame the binder textualizes.

E.6 Privacy and law SOMA — AN INPUT-ONLY WEARABLE MEMORY ANNOTATED BIBLIOGRAPHY Cavoukian [5] names the standard SOMA meets architecturally rather than procedurally: privacy embedded in design. GDPR Art. 5(1)(c) [6] makes data minimization a legal principle; keeping meaning instead of medium is its strongest available reading for a perception device.

SOMA — AN INPUT-ONLY WEARABLE MEMORY ANNOTATED BIBLIOGRAPHY APPENDIX F The Question Battery, In Full Shape The hero walk's 25-question adversarial battery, by category, with what each category stresses. (Questions paraphrased from the frozen set; gold keys are hash-pinned in evaluation/.)

# Category Example question What it stresses 1–4 Object identity "What brand was my backpack?"

detector + enrichment L2 (logos, text on objects) 5–7 Text in the world "What did the laptop screen say?"

OCR channel; screen/sign reading 8–9 Spatial relations "Which side of the platform was the bench on?"

egomotion + anchors — the diagnosed (A) class 10–11 Audio facts "What did the announcement say?"

ASR; audio-visual binding Occupancy/binary state "Was the station crowded?" (gold: empty) binary-state discipline; absence evidence 13–15 Attributes "What color was the cyclist's jacket?"

cheap-channel attributes; color naming 16–17 Counting "How many trains passed?"

dedup + identity resolution over time 18–19 Negation/absence "Did I see a dog?" (gold: no) phantom-object defenses; honest negatives 20–21 Temporal order "What did I pass first, X or Y?"

timeline navigation 22–23 Cross-channel "What was making the humming sound?"

binder co-occurrence (the fan/hum class) 24–25 Unanswerable (planted) "What was written on the far poster?" (never legible) refusal calibration; RAS rewards the honest no Three design rules govern battery construction. Questions are written blind — the author has not seen what the system captured, so the battery samples the world's distribution, not SOMA — AN INPUT-ONLY WEARABLE MEMORY THE QUESTION BATTERY, IN FULL SHAPE the system's strengths. Gold keys carry acceptable-answer lists and founder verdicts resolve disputes. And planted unanswerables are mandatory: a battery without them cannot distinguish a calibrated system from a talkative one.

SOMA — AN INPUT-ONLY WEARABLE MEMORY THE QUESTION BATTERY, IN FULL SHAPE APPENDIX G The Decision Log Locked decisions, their rationale, and their revisit condition — the institutional memory of the architecture. (Decisions marked ◆ are founder-locked product decisions; ■ are audited engineering verdicts.)

Decision Rationale Revisit when ◆ Text-only retention (I1) privacy structural; text queryable/auditable sufficiency run falsifies losslessness (§16.1) ◆ Unconstrained questions (I6) constrained surface hides hallucination never — supersedes north star's older suggestion ◆ Refusal over fabrication (I5) trust is the product never ■ MobileCLIP-S0 for naming ANE-fast; words-not-prose; open vocab; audit: weak link was proposals, not naming desk-test diag shows naming (not proposals) is the bottleneck ■ ARKit for pose/reloc only free 6-DOF + relocalization on the hardware cross-day reloc fails at its measured gate ■ Append-only SQLite event log replay, audit, crash-safety; no server store outgrows device (not projected) ■ AES-256-GCM user-key codec authenticated encryption; versioned AAD crypto review mandates change ■ Strangler over rewrite for ask_home 2,900 lines of earned heuristics; rewrite risk strangling completes (celebration, not revisit) ■ No app rewrite before demo build+install loop is the only device-test loop after the pitch window ◆ Kill the 3D world renderer no question needed it (I7's founding case) a diagnosed (A) spatial miss that egomotion cannot close ■ Gemma-3-12B local / hatch to frontier text local-first economics; typed egress makes hatch safe measured local-vs-hatch delta justifies switch ◆ RAS ≥ 60, hallucination < 5% as prototype gate the stranger-amazement bar made numeric founder resets the bar SOMA — AN INPUT-ONLY WEARABLE MEMORY THE DECISION LOG APPENDIX H A Day in the Life of the System The architecture, narrated once more as an operational timeline — what is actually running, hour by hour.

06:58 — wake. The wearable starts with the wearer. Cheap channels spin up: detector, OCR, ASR, sound tagger, sensors. The token bucket begins refilling at its measured hourly rate. Nothing else runs; the reasoner sleeps.

07:42 — the balcony. The crow lands (Chapter 6). Five observations from three channels in four seconds; one enrichment token spent on the dwell-marked track; under a kilobyte written to the append-only log; zero frames retained. The morning continues: a receipt OCR'd at the bakery, a conversation transcribed at the kiosk, the espresso machine tagged, the door latch stamped on the way out. By commute's end the log holds a few thousand observations — the day so far, as words.

09:00–18:00 — the long middle. The scheduler's economics dominate. Familiar objects (the kettle, the desk, the monitor) accumulate dwell but not novelty — they sit below the enrichment line, represented by cheap words alone. The new thing — a colleague's unfamiliar prototype on the desk — crosses the line and earns a level-1 look; twenty minutes of continued dwell later, level 2 reads the label on its case. Battery and thermals hold because the expensive eye fired a handful of times an hour, not thirty times a second. 19:30 — a question, live. "Where did I put the pharmacy bag?" The supplier walks today's log — no night shift has run yet, so recall navigates the raw scaffold: the bag's last observation, 18:04, hallway shelf, one citation. Accelerator-not-gatekeeper, demonstrated: unbound memory still answers.

23:30 — the night shift. Charger connected; thermals irrelevant; the big model wakes. Congregate, dedupe, bind by co-occurrence; refuse the weak links (the day's coincidences die here); resolve identities (today's crow is crow_1, thickened, not crow_4); run the derivation pass (three trash-morning clusters become a habit node); rebuild the projections; run the self-play battery against the day and file the misses into the (A)/(B) queue. Toward dawn: the discarder drops the marinated structures the night's better judgment replaced. The SOMA — AN INPUT-ONLY WEARABLE MEMORY A DAY IN THE LIFE OF THE SYSTEM raw material it never touches.

06:58, again. The wearer wakes with a memory one day richer, a graph one night wiser, a backlog written by the system's own misses — and not one frame, anywhere, of anything. — end of document — SOMA — AN INPUT-ONLY WEARABLE MEMORY A DAY IN THE LIFE OF THE SYSTEM APPENDIX I The Capture Notation: Worked Records The wire format of memory, shown whole. Below are the actual record shapes for one minute of the crow morning, as they rest in the append-only log (field order as in src/soma/domain/observation.py; values illustrative).

I.1 A detector observation Field Value kind object subject black bird attributes (position: balcony_railing), (size: small), (motion: landing) t_ms 27_723_210 (07:42:03.210) spatial_anchor balcony/railing confidence 0.71 provenance (event_id: ev-4183, source_channel: detector, captured_at_ms: 27_723_210) refutation_cue track lost within 1s → possible shadow The refutation cue deserves a note: it is the observation announcing, at birth, what future evidence would disprove it. A shadow misread as a bird is expected to lose its track within a second; when the track instead persists forty seconds and earns a VLM look, the cue's condition fails and the observation's standing strengthens. Falsifiability is not a philosophy here; it is a field.

I.2 A sound observation Field Value kind sound_event SOMA — AN INPUT-ONLY WEARABLE MEMORY THE CAPTURE NOTATION: WORKED RECORDS subject corvid call (caw) attributes (loudness: moderate), (direction: east) t_ms 27_724_030 spatial_anchor balcony confidence 0.66 provenance (ev-4184, audio, 27_724_030) I.3 An enrichment observation (level 1) Field Value kind vlm_gist subject large corvid attributes (color: glossy black), (activity: perched, watching), (level: overview) t_ms 27_726_400 spatial_anchor balcony/railing confidence 0.78 provenance (ev-4188, vlm, 27_726_400) I.4 A binding, after the night shift Field Value binding_id b-0917 subject_id crow_1 predicate observed_at object_text balcony/railing @ tue 07:42 confidence 0.87 evidence (ev-4183, detector), (ev-4184, audio), (ev-4188, vlm) Note the constructor discipline visible even in a table: the binding has object_text and therefore no object_id (exactly one, enforced); it has three evidence entries (non-empty, enforced); its confidence is a probability (range-checked at construction). A malformed memory is not a bug to find later — it is an object that never existed. I.5 The whole minute, as storage SOMA — AN INPUT-ONLY WEARABLE MEMORY THE CAPTURE NOTATION: WORKED RECORDS Nine observations, one entity, two bindings: roughly 2.1 KB of text before compression. The same minute as 30 fps 4K video: roughly 1.4 GB. The ratio — about six orders of magnitude — is the entire economics of "never delete" (I3), and the reason a life fits on a phone.

SOMA — AN INPUT-ONLY WEARABLE MEMORY THE CAPTURE NOTATION: WORKED RECORDS APPENDIX J Substrates and Hardware Budgets The same architecture, three bodies. What changes per substrate is only the adapter ring; what never changes is the domain, the invariants, and the evaluation harness. J.1 V0 — the Mac The proving substrate: recorded or streamed capture processed on a Mac (MLX-hosted VLMs, Ollama-served reasoners), where thermal ceilings are irrelevant and the sufficiency question — does lossless-enough context plus a brain work at all — can be answered without budget noise. Everything in Chapter 13's method runs here first. The Mac is also where the night shift will always be allowed to be heaviest: consolidation is substrate-agnostic by construction, because its input is a replayable text log, not a device. J.2 V1 — the phone rig The moat substrate: chest-mounted iPhone, all-day. The constraints that shaped the architecture become measurable here: the Apple Neural Engine favors small always-on models (MobileCLIP's audit-winning property [27]); ARKit supplies 6-DOF pose and relocalization [15]; thermal and battery ceilings set the token bucket's refill rate empirically. The governance rule for this substrate is the build stamp (§14.2): no number is believed until read off a device artifact carrying the git SHA that produced it. Two open gates define V1 honesty: the all-day budget story (measured battery %/hr, enrichments/hr) and the live no-raw-persistence proof.

J.3 Glasses — the destination The form factor the architecture was shaped for rather than on: a device worn at eye level, socially tolerable precisely because it is architecturally incapable of recording. Everything hard about glasses — battery, heat, social acceptability — is a harder version of a constraint the phone rig already prices, which is why the phone rig is the right dress rehearsal. No glasses-specific engineering exists in the repository today, deliberately (I7: no missed question demands it yet).

SOMA — AN INPUT-ONLY WEARABLE MEMORY SUBSTRATES AND HARDWARE BUDGETS J.4 The budget table Resource Cheap stratum Expensive eye Night shift Cadence continuous tokens/hour (bucket) once nightly Model class detector, OCR, ASR, tagger, sensors 7–12B multimodal 12B+ text (or hatch) Power posture always-on, ANE-friendly budgeted bursts on charger Failure visibility (A) misses in OAG (A) misses in OAG (B) misses in RAS Where it runs (V0 / V1) Mac / device Mac / device Mac / device-on-charger SOMA — AN INPUT-ONLY WEARABLE MEMORY SUBSTRATES AND HARDWARE BUDGETS APPENDIX K Future Work Marked explicitly as unauthorized work in the I7 sense: none of it may be built until a missed question or a product gate demands it. It is recorded so that ambition is documented without being licensed.

Forgetting curves for projections. The discarder currently drops useless marination wholesale; a principled version would demote derived nodes along decay schedules informed by access patterns — semantic memory's own economics. The raw log never participates (I3).

Shared and multi-person memory. Two SOMA wearers who consent could bind across logs — "we both heard the same announcement" — raising consent, provenance, and key-architecture questions an order of magnitude harder than the single-wearer case. The typed-egress boundary (I2) is the natural interface: only text, only cited, only by mutual key exchange.

Refutation-driven revision. The refutation_cue field is stored but not yet acted upon at scale; a full implementation runs nightly refutation sweeps — evidence arriving later that triggers stored cues demotes or annotates the observations they guard. On-answer teaching. When the user corrects an answer ("that wasn't the North Face bag, it was the Patagonia"), the correction is itself an observation — user-channel, high confidence — that the next night's shift binds against the record. The memory would then be the first perception system whose owner can argue with it, with citations, and win. Question-cost forecasting. The scheduler currently spends attention on salience; a stronger version prices tracks by expected future question value learned from the wearer's own question history — closing the loop between what is asked and what is looked at. SOMA — AN INPUT-ONLY WEARABLE MEMORY FUTURE WORK APPENDIX L Reading Paths Three curated routes through this document, for three readers. The evaluator (an hour). Chapter 1 (the claim) → Chapter 6 (the crow, the claim made concrete) → Chapter 13 (how failure is measured) → Chapter 16 (what could kill it) → Appendix D (the scorecard). This path contains every number and every risk; nothing in the remaining chapters softens or contradicts it.

The engineer (an afternoon). Chapters 4–5 (invariants, pipeline) → Chapters 7–11 (domain to recall) → Appendix C (the formal surface) → Appendix I (the wire format) → then the repository itself, in the order README → ops/NORTH_STAR.md → ops/ROADMAP.md → src/soma/domain/.

The skeptic (an evening). Chapter 2 (why words) → Chapter 3 (who tried before) → Chapter 18 (the objections, at full strength) → Chapter 12 (the moat, and its honest residue §12.7) → Chapter 16 (the risk register). If the skeptic leaves with one sentence, it should be the one the architecture stakes everything on: the failure modes of this system are designed to be measurable, attributable, and named — and a system that can name its failures can fix them.

SOMA — AN INPUT-ONLY WEARABLE MEMORY READING PATHS APPENDIX M The Legacy Engine: An Archaeology and a Strangling Plan scripts/ask_home.py — roughly 2,900 lines — is the system's functioning ancestor: the answer engine that produced every baseline number in Chapter 13. It predates the domain model, violates most of the style gate, and contains 47 broad exception handlers. It is also a repository of earned answer-quality defenses, bought one hallucination at a time on real captures, and the strangling plan's first rule is that none of them may be lost in translation. M.1 What it knows that a rewrite would forget – Binary-state discipline. The engine refuses to assert occupancy and state claims (crowded/empty, open/closed, on/off, plugged/unplugged) unless a line directly and literally supports the state — a sound event does not prove a crowd; a stray cable does not prove a phone was connected. This is the grounding gate's ancestor, learned from specific scored failures.

– Phantom-class defenses. A deliberately narrow watchlist (locomotion, animate, crowd classes) guards existence questions — "did I see a dog?", "was there a train?" — the classes where prior plausibility most strongly tempts a model to invent. – Absence and negation handling. Explicit machinery for answering "no" from the absence of evidence plus positive contrary cues (the empty-platform class), the hardest honest answer for a generative system.

– Cross-lingual matching. English questions match German OCR (molecule↔Molekül, crowded↔leer) — a semantic-index lesson from captures in a bilingual environment. – Evidence dossiers. An 818-line dossier builder — oversized, but embodying the just-enough-context craft that Chapter 11 formalizes.

M.2 The strangling sequence Capability Legacy home New home Status SOMA — AN INPUT-ONLY WEARABLE MEMORY THE LEGACY ENGINE: AN ARCHAEOLOGY AND A STRANGLING PLAN Answer boundary + citations ad-hoc dict output Recall → RecallAnswer via LegacyAskHome done Bound memory bound_memory (empty, unusable) Binder consensus projection first real version on follow-on branch Grounded generation inline prompt rules GroundedRecall on local gemma first version on follow-on branch Claim verification scattered regex gates grounding_gate.py (Phase 3) boundary named Retrieval / indexes per-script builders projections over the event log migrating State/phantom/absence defenses prompt strings + regexes typed gate rules with tests to extract The migration's covenant: every extracted capability lands behind a port with tests that encode the legacy behavior it must preserve, and the baseline battery re-runs after each extraction — the strangler fig with a regression harness wrapped around it. When the last capability moves, the 47 broad excepts retire with the file, not before. SOMA — AN INPUT-ONLY WEARABLE MEMORY THE LEGACY ENGINE: AN ARCHAEOLOGY AND A STRANGLING PLAN APPENDIX N Threat Scenarios, Walked Abstract threat tables persuade engineers; scenarios persuade everyone else. Four walks through the membrane.

The stolen phone. A thief lifts the device from a café table mid-afternoon. What is on it: the day's append-only log and the graph — AES-256-GCM ciphertext under the user's key — and no media artifact of any kind. What the thief's forensic tooling recovers from a storage-first wearable in the same scenario: the owner's day, and every bystander in it, in video. The comparison is the product.

The subpoena. Litigation compels production of "all recordings" from a contested afternoon. SOMA's truthful response: no recordings exist; what exists is the owner's typed observation log — the same artifact class as a diary, with the same legal posture, readable by its owner, produced or contested under the same rules diaries have had for a century. The system has not made its owner a walking evidence locker for third parties. The cloud breach. The vendor's infrastructure is compromised entirely. Exposed: whatever guarded text the user's measured hatch decisions sent for deep reasoning — each payload provenance-stamped and text-only — and nothing else, because nothing else was ever transmissible (I2). The breach headline for a storage-first competitor is a media archive; for SOMA it is a subset of an already-minimal text stream.

The coerced unlock. The hardest scenario, stated honestly: an adversary with the user and the user's key — an abusive partner, a border agent — reads text. The text is the day as words: real exposure, and §12.7's residue made concrete. What the architecture still withholds is the replayable stream — no scrubbing through footage of who the user met, no faces of third parties, no audio to re-hear. Harm is bounded to what words carry; that bound is the difference between a diary seized and a surveillance archive seized. SOMA — AN INPUT-ONLY WEARABLE MEMORY THREAT SCENARIOS, WALKED APPENDIX O Binding Arithmetic: How 0.87 Happens The crow's binding confidence, decomposed. The binder scores a candidate join over evidence features; the shape below is the contract (weights illustrative, tuned per Chapter 13's method, never hand-trusted): Feature Crow join (ev-4183 + ev-4184 + ev-4188) Chime join (ev-4191 + crow_1) Temporal proximity (window overlap)


### 0.95 — within 3.2s


### 0.71 — within 7s

Spatial agreement (anchor match)


### 0.9 — railing ⊂ balcony


### 0.4 — chime anchored next-door

Kind compatibility (object↔sound↔gist priors)


### 0.85 — corvid call ↔ bird ↔

corvid gist


### 0.2 — chime ↔ animal: no prior

Channel independence bonus +: three channels agree −: single channel, single event Recurrence support n/a (first day) → neutral none Score → calibrated confidence 0.87 0.31 Floor (0.55) bind refuse Two properties of the arithmetic matter more than its constants. Independence is rewarded: three channels agreeing is evidence in a way three emissions of one channel is not — the fusion literature's core lesson [16]. And calibration is audited downstream: Chapter 13's scoring checks that bindings at 0.8x are right at roughly that rate, because a binder whose


### 0.87 behaves like a 0.6 poisons every threshold above it [20].

O.1 Recurrence, formally On Wednesday the binder faces a choice: new entity or same? Identity resolution scores anchor consistency (same railing), kind and attribute consistency (corvid, glossy black), and behavioral signature (morning, brief perch) — resolving to crow_1 and pooling evidence. Confidence under pooling rises sublinearly (0.87 → 0.93, not → 0.99): repeated observation strengthens identity but never launders it into certainty. The asymptote is deliberate; certainty is reserved for the log itself (what was observed is a fact; what it was remains an inference forever).

SOMA — AN INPUT-ONLY WEARABLE MEMORY BINDING ARITHMETIC: HOW 0.87 HAPPENS APPENDIX P "Lossless-Enough," Formally The phrase carries the hypothesis, so it deserves a definition. Fix a question distribution Q — the questions a wearer's future self will ask, approximated by the adversarial batteries. For a day D, let O(D) be the answer set achievable by an oracle with the raw streams, and T(D) the answer set achievable by the same reasoner over SOMA's retained text. The retention is lossless-enough with respect to Q when: for questions drawn from Q: P[q answerable from T(D) | q answerable from O(D)] ≥ 1 − ε with ε the tolerated gap — and OAG is precisely the empirical estimate of that conditional miss rate (Chapter 13). Three consequences of writing it down. First, losslessness is relative to Q: no retention short of the stream itself is lossless against all possible questions, and the product claim never needs it to be — Q is human, finite, and skewed toward the memorable, which is what salience capture exploits. Second, ε is a product constant, not a research constant: the stranger-amazement bar sets it. Third, the definition cleanly separates the two failure terms the (A)/(B) instrument measures: capture loss shrinks T(D); reasoning loss fails to reach answers already inside it. The hypothesis of §1.3, restated: there exists an affordable channel set for which ε is small under the real question distribution. Everything else in this document is the machine for estimating ε fast.


## 19 — Conclusion

SOMA's argument compresses to four sentences. The valuable artifact of a lived day was never the footage; it was the bound, queryable meaning, and meaning survives translation to words while surveillance does not. A memory that keeps only words can be structurally incapable of the harms that have sunk every storage-first wearable, while remaining open to any question its perception actually answered. Whether words captured at the moment of living are enough — lossless enough, bindable enough, honest enough — is a falsifiable hypothesis, and this architecture is the instrument built to test it at maximum speed: append-only truth, disposable understanding, calibrated refusal, and a measurement loop in which every failure names its own fix. The crow on the railing either becomes a cited answer or an honest "I don't know" — and a system that can tell you which, and why, is a system worth building.

SOMA — AN INPUT-ONLY WEARABLE MEMORY CONCLUSION

[41] A. L. Yarbus, *Eye Movements and Vision*, Plenum Press, 1967.

[42] R. P. N. Rao and D. H. Ballard, "Predictive coding in the visual cortex: a functional interpretation of some extra-classical receptive-field effects," *Nature Neuroscience* 2(1), 79–87, 1999.

[43] A. M. Collins and E. F. Loftus, "A spreading-activation theory of semantic processing," *Psychological Review* 82(6), 407–428, 1975.

[44] J. L. McClelland, B. L. McNaughton, and R. C. O'Reilly, "Why there are complementary learning systems in the hippocampus and neocortex," *Psychological Review* 102(3), 419–457, 1995.

[45] M. A. Wilson and B. L. McNaughton, "Reactivation of hippocampal ensemble memories during sleep," *Science* 265, 676–679, 1994.

[46] S. Diekelmann and J. Born, "The memory function of sleep," *Nature Reviews Neuroscience* 11, 114–126, 2010.

[47] J. O'Keefe and L. Nadel, *The Hippocampus as a Cognitive Map*, Oxford University Press, 1978.

[48] E. F. Loftus and J. C. Palmer, "Reconstruction of automobile destruction: an example of the interaction between language and memory," *Journal of Verbal Learning and Verbal Behavior* 13, 585–589, 1974.

[49] K. Friston, "The free-energy principle: a unified brain theory?", *Nature Reviews Neuroscience* 11, 127–138, 2010.

[50] S. A. Jelbert, A. H. Taylor, L. G. Cheke, N. S. Clayton, and R. D. Gray, "Using the Aesop's Fable paradigm to investigate causal understanding of water displacement by New Caledonian crows," *PLoS ONE* 9(3), e92895, 2014.
