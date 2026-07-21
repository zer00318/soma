// ═══════════════════════════════════════════════════════════════════
// TRACE — the architecture thesis · v2.0 · July 2026
// Sources of truth: the napkin (Appendix A), the tracemem repository,
// the v0 stack. All 42 external references verified against live
// sources (arXiv API, doi.org, CrossRef, publisher URLs) 2026-07-21.
// Build: typst compile main.typ
// ═══════════════════════════════════════════════════════════════════

#set document(
  title: "TRACE — An Input-Only Wearable Memory",
  author: "Venkata Sai Pranav Regulagedda",
  keywords: ("TRACE", "wearable memory", "architecture", "privacy", "on-device AI"),
)
#set page(paper: "a4", margin: (x: 2.4cm, top: 2.6cm, bottom: 2.8cm))
#set text(font: "Libertinus Serif", size: 10.5pt, lang: "en")
#set par(justify: true, leading: 0.62em)
#set heading(numbering: "1.1")

#let ember = rgb("#D9480F")
#let inkgray = rgb("#6b6960")

#show heading.where(level: 1): it => {
  pagebreak(weak: true)
  v(2.2em)
  block[
    #if it.numbering != none [
      #text(size: 9pt, fill: inkgray, tracking: 0.18em)[#upper[Chapter #counter(heading).display()]]
      #v(0.3em)
    ]
    #text(size: 20pt, weight: 700)[#it.body]
    #v(1.2em)
  ]
}
#show heading.where(level: 2): it => block(above: 1.6em, below: 0.8em)[
  #text(size: 12.5pt, weight: 700)[#counter(heading).display() #it.body]
]
#show raw: set text(font: "DejaVu Sans Mono", size: 9pt)
#show link: set text(fill: ember.darken(20%))

#let REAL = text(fill: rgb("#1f7a33"), weight: 700, size: 8.5pt)[IMPLEMENTED]
#let FAKES = text(fill: ember, weight: 700, size: 8.5pt)[ON FAKES]
#let STUB = text(fill: ember, weight: 700, size: 8.5pt)[STUBBED]
#let NOTYET = text(fill: inkgray, weight: 700, size: 8.5pt)[NOT YET]
#let partpage(title) = {
  pagebreak(weak: true)
  v(9cm)
  align(center)[
    #line(length: 3.6cm, stroke: 0.7pt + ember)
    #v(1em)
    #text(size: 22pt, weight: 700)[#title]
    #v(1em)
    #line(length: 3.6cm, stroke: 0.7pt + ember)
  ]
  pagebreak()
}

// ─────────────────────────── COVER ───────────────────────────
#page(margin: (x: 2.4cm, y: 3cm), header: none, footer: none)[
  #v(3.2cm)
  #align(center)[
    #text(size: 44pt, weight: 800, tracking: 0.22em)[TRACE]
    #v(0.4em)
    #text(size: 14pt, fill: inkgray)[An Input-Only Wearable Memory]
    #v(1.2em)
    #line(length: 5.2cm, stroke: 0.7pt + ember)
    #v(1.6em)
    #text(size: 12pt)[
      Architecture, rationale, and the case for a memory \
      that keeps words instead of footage
    ]
    #v(4.2cm)
    #text(size: 11pt, weight: 600)[Venkata Sai Pranav Regulagedda]
    #v(0.25em)
    #text(size: 9.5pt, fill: inkgray)[Founder · KIT · Max Planck Institute for Plasma Physics]
    #v(1.4em)
    #text(size: 9.5pt, fill: inkgray)[
      Technical exposition · prepared for the founding team \
      July 2026 · version 2.0
    ]
    #v(2.2cm)
    #text(size: 8.5pt, fill: inkgray)[
      The architecture of record is a hand-drawn napkin, photographed 2026-07-18, \
      transcribed verbatim in Appendix A. On any conflict, the napkin outranks this document.
    ]
  ]
]

#set page(
  numbering: "1",
  header: context {
    if counter(page).get().first() > 1 [
      #text(size: 8pt, fill: inkgray, tracking: 0.12em)[TRACE — AN INPUT-ONLY WEARABLE MEMORY]
      #h(1fr)
      #text(size: 8pt, fill: inkgray)[v2.0 · July 2026]
    ]
  },
)

// ─────────────────────────── ABSTRACT ───────────────────────────
#heading(numbering: none, outlined: false)[Abstract]

TRACE is a wearable memory system built on one uncompromising invariant: raw
media never persists and never leaves the device; only typed text may cross
the boundary. On-device perception converts the live world into
open-vocabulary, coordinate-marked, provenance-bearing text at the moment of
capture; the raw pixels and audio that produced it are discarded within
milliseconds. A consolidation process — deliberately modeled on biological
sleep — binds the day's scattered observations into a typed evidence graph by
spatial and temporal co-occurrence, attaching a calibrated confidence to every
link and refusing weak ones outright. A recall engine answers unconstrained
natural-language questions from this bound text alone, citing the exact
observations that support each claim and refusing honestly when the answer was
never perceived.

This document is the complete argument for that architecture. It derives the
design from first principles (Chapters 1–2), situates it against forty years
of lifelogging, egocentric-vision, and retrieval-augmented-generation research
(Chapter 3), states the seven locked invariants that govern all implementation
(Chapter 4), and walks the full pipeline from photons to answers (Chapter 5) —
including a complete worked example followed end to end from a single reach
toward a jar to a derived habit no sensor ever observed (Chapter 6). It then
descends into the machine: the formal domain model (Chapter 7), the
contract-first software architecture (Chapter 8), the salience-governed
perception subsystem (Chapter 9), consolidation (Chapter 10), and grounded
recall with calibrated refusal (Chapter 11). The remaining chapters treat the
privacy architecture and its threat model (Chapter 12), the evaluation
methodology that makes every failure diagnosable (Chapter 13), engineering
governance (Chapter 14), the project's two stacks and the migration between
them (Chapter 15), market position (Chapter 16), honest risks (Chapter 17),
the strongest objections answered at full strength (Chapter 18), and the road
ahead (Chapter 19).

The central hypothesis — that perception can be decomposed into channels
which reconstruct lossless-enough textual context for a tractable reasoner to
answer arbitrary retroactive questions at near-zero hallucination — is stated
throughout as what it is: falsifiable and instrumented. Every architectural
decision in this document exists to test it faster.

// ─────────────────── EXECUTIVE SUMMARY ───────────────────
#heading(numbering: none)[Executive summary]

_For the reader with ten minutes. Every claim below is developed, evidenced,
and stress-tested in the body; section pointers are given throughout._

*The product.* TRACE is a wearable memory you can question. It senses the day
through always-on, cheap perception; turns everything into words the instant
it happens — never keeping one frame of video or one second of audio; binds
those words into understanding at night; and answers any question about the
past with citations to what it actually perceived, or an honest "I don't
know."

*The insight.* The valuable artifact of a lived day was never the footage —
it was the bound, queryable meaning. Storage-first wearables keep the toxic
artifact (raw media: subpoenable, breachable, socially unacceptable) while
deferring the valuable one (extracted, connected facts). TRACE extracts at
the moment of capture and keeps only the value (Chapters 1–2).

*The moat.* Surveillance is not forbidden by policy; it is impossible by
architecture. The only object that can leave the device is typed text
carrying the identifiers of the observations it came from; everything else
dies at a guard short enough to audit in one breath. The store is encrypted
under the user's own key. A competitor cannot copy this posture without
abandoning the stored-media foundation its product is built on (Chapters 12,
16).

*The machine, in one breath.* Cheap senses run continuously (detection, OCR,
speech, sound events, motion); an attention scheduler spends a hard hourly
budget of deep vision-model looks only where dwell, novelty, and stability
earn them; every emission is a typed, timestamped, provenance-bearing claim
in an append-only log; consolidation fuses claims by co-occurrence into
living nodes — refusing every weak link — and derives new facts no sensor
observed; at question time, a supplier hands a local reasoner just enough
cited evidence to answer or refuse (Chapters 5, 9–11). Chapter 6 walks one
memory through every stage.

*The discipline.* Seven locked invariants govern all code (Chapter 4): no raw
persistence; text-only egress; append-only truth; provenance on everything;
calibrated confidence with refusal over fabrication; unconstrained questions;
and nothing built until a missed question demands it. Most are enforced by
construction — an invalid memory object cannot exist.

*The measurement.* Two instruments keep the system honest (Chapter 13). RAS
scores answers with fabrication subtracted — a made-up answer costs what a
correct one earns. OAG measures what verbalization lost: of the questions a
raw-footage oracle can answer, the share the retained text cannot. Every
miss is mechanically diagnosed as (A) never captured or (B) captured but
unused, and the miss list is the backlog. The first measured baseline was
poor and is reported anyway (RAS 40.0, hallucination 27.3% on the proving
clip); the refusal-calibration research line — run with research
collaborator Latheesh Roy — subsequently drove confident-wrong answers to
*zero on the reproducible benchmark battery*, and holding that zero on cold
captures is a standing gate, not a claim of final victory (§13.5, §13.8).
On the perception side, extraction currently recovers 97.4% of what a
frontier-model oracle reads from the same 111 real frames (§9.5).

*The state of the build.* The full thinking machinery — binder,
consolidation, supplier, grounded recall — is implemented and passes an
end-to-end crown test on synthetic weeks; the hardware senses are still
adapters-on-fakes; and a v0 stack has run live capture daily since June 2026
while the greenfield rebuild strangles it organ by organ (Chapter 15). The
ledger on the next page states exactly what runs, what runs on fakes, and
what does not yet exist.

*The hypothesis, stated as one.* That textual channels can carry
lossless-enough context for near-zero-hallucination recall is falsifiable
and instrumented rather than assumed. The method: prove sufficiency offline
with unlimited compute first; discover the necessary channel set by ablation
second; optimize for the live budget last (Chapter 13, Appendix K).

// ─────────────────── WHAT IS REAL TODAY ───────────────────
#heading(numbering: none)[What is real today]

The reader deciding whether to join this project should not have to excavate
the truth from an argument. This table is transcribed from the build ledgers
of the two repositories on 2026-07-21. Each row names its evidence.
Staleness warning: these are facts about a fast-moving codebase, correct on
the date above and demoted to hearsay a month later.

#table(
  columns: (1fr, auto, 1.35fr),
  stroke: 0.4pt + rgb("#ddd"),
  inset: 6.5pt,
  table.header([*Component*], [*Status*], [*Evidence*]),
  [Domain model · claim log · rendering], REAL, [`tracemem` M0–M1, green tests],
  [Binder — reconcile, tombstones], REAL, [`tracemem` M3],
  [Consolidation — guardrails, selector, judge, pruner, remap], FAKES, [`tracemem` M4 — implemented against synthetic inputs],
  [Information supplier — cue, retrieve, pack, ground], REAL, [`tracemem` M5],
  [`.trace` container — format, keyring, sync, boundary], [#REAL / #STUB], [M6; libsodium crypto adapter stubbed],
  [Extraction cascade], [#FAKES / #STUB], [M7 — logic real, hardware adapters (OCR/ASR/eyes/tap) stubbed],
  [Crown test: shuffled synthetic week → episodes → entities → nightly patterns → cited answer → honest abstention], REAL, [`tests/test_crown.py`, passing],
  [Unit wall], REAL, [274 green · 1 xfail (the TODO ledger, each naming its spec section)],
  [Measured extraction gap], REAL, [L1-verbatim recall 0.974 (gap 0.026) over 111 real frames; ceilings audited],
  [Confident-wrong answers on the benchmark battery], REAL, [0% — refusal-calibration line (with Latheesh Roy); cold-capture guard still open],
  [Falsification gate on real captured weeks], NOTYET, [the gate needs real captured weeks — the next milestone that matters],
  [v0 stack: live capture, hub, nightly job, phone app], REAL, [running since June 2026; being strangled, not extended],
)

*The number that matters most is one that is absent:* frames kept — zero, by
construction, in both stacks. There is no code path that writes a frame to
disk.

// ─────────────────── HOW TO READ THIS ───────────────────
#heading(numbering: none)[How to read this document]

This document is written for six kinds of reader. Do not read it linearly
unless you want to.

- *In 10 minutes:* the Executive Summary, the ledger above, and Chapter 6.
- *The evaluator (an hour):* Chapter 1 (the claim) → Chapter 6 (the claim
  made concrete) → Chapter 13 (how failure is measured) → Chapter 17 (what
  could kill it) → Appendix C (the scorecard). This path contains every
  number and every risk; nothing in the remaining chapters softens or
  contradicts it.
- *The engineer (an afternoon):* Chapters 4–5 → Chapters 7–11 → Appendix F
  (the wire format) → then the repository itself.
- *The skeptic (an evening):* Chapter 2 (why words) → Chapter 3 (who tried
  before) → Chapter 18 (the objections, at full strength) → Appendix L (the
  case against, from the literature) → Chapter 12 (the moat and its honest
  residue) → Chapter 17 (the risk register).
- *Cognitive science:* Chapters 2, 6, and 10 — the biological arguments are
  load-bearing, and you are the reader best placed to break them.
- *Investors and diligence:* the ledger above, then Chapters 15–19.

#outline(depth: 2, indent: 1.2em)

// ═══════════════════ PART I ═══════════════════
#partpage[Part I · Foundations]

= Introduction and problem statement

== The problem: lives are forgotten by the people who live them

People forget most of their lives. Where the keys were left. What the doctor
actually said, as opposed to what anxiety later reconstructed. Whether the
door was locked. The name attached to a face met once at a dinner. Which
pharmacy the prescription went to. What the contractor promised, verbally, in
the hallway. The moments that matter are sparse, unpredictable in advance,
and irretrievable by the time they are needed. Human episodic memory was
never designed for retrieval on demand; it is a reconstructive process,
optimized for gist over fidelity, and it degrades precisely along the
dimensions — exact words, exact places, exact times — that everyday questions
require [1][2].

The obvious remedy is to record everything. It fails twice, and both failures
are fundamental rather than incidental.

The first failure is social and legal. A person wearing an always-on camera
that stores video is a walking surveillance device. Every bystander is
recorded without consent; every stored hour is subject to subpoena, theft,
breach, and misuse; every intimate space the wearer enters becomes an
archive. The history of wearable cameras is a history of this failure: from
the earliest sousveillance experiments to the public rejection of camera
glasses, storage-first capture has been socially unacceptable everywhere it
has been tried at scale [10][34]. No privacy policy fixes this, because
policies are promises, and promises about stored media are exactly what
nobody believes.

The second failure is functional. Raw footage is the wrong artifact. Nobody
rewatches their life; a day of video is a day long. What people actually want
from a memory is not playback but answers: they want to query the past the
way they query a database, in natural language, and get back a short, true,
cited response. The valuable artifact was never the footage — it was the
bound, queryable meaning that a mind would have extracted from it.
Storage-first systems defer that extraction forever and so never deliver it.

== The problem statement

TRACE's problem statement follows directly:

#block(inset: (left: 1.5em, right: 1.5em))[
_Build a system that perceives a person's day through always-on, cheap
senses; converts everything to words the instant it happens — never keeping
one frame of video or one second of audio; consolidates those words,
continuously and best nightly, into bound understanding; and later answers
arbitrary questions from that understanding with citations, or refuses
honestly._
]

Three phrases in that statement carry the whole design, and each is defended
at length in this document. "The instant it happens" is the privacy
architecture (Chapter 12): ephemerality at the source, not deletion after the
fact. "Bound understanding" is the binder and the node layer (Chapters 5,
10): isolated observations are raw material, not memory; memory is what
emerges when the label, the spoken sentence, and the reach are fused into one
moment. "Or refuses honestly" is the epistemology (Chapters 11 and 13): a
memory that fabricates is worse than no memory at all, so refusal is a
first-class outcome and fabrication is priced into the headline metric at the
cost of a correct answer.

== The central hypothesis

Everything rests on one hypothesis, repeated here because intellectual
honesty about it is the whole game:

#block(inset: (left: 1.5em, right: 1.5em))[
_Perception can be decomposed into channels that reconstruct lossless-enough
textual context for a tractable local reasoner to answer arbitrary
retroactive questions at near-zero hallucination._
]

It is falsifiable — Appendix K states it formally, and the
oracle-answerability gap of Chapter 13 is its direct empirical estimator. It
is instrumented rather than assumed. And it is not yet proven on real
captured weeks; the falsification gate that would confirm or kill it is the
project's named next milestone.

== What TRACE is not

TRACE is not a lifelogger: it keeps no log of life, only text extracted from
it. It is not a surveillance device: the artifact surveillance requires is
never created. It is not a retrieval-augmented chatbot: retrieval here feeds
a memory that was built for retrieval under a privacy invariant, not a pile
of documents that happen to exist. It is not a model company: the language
model is the last and least special box in the machine, ordinary and
swappable by design. And it is not finished: the ledger in the front matter
is the boundary between the built and the intended, and this document never
blurs it.

== Contributions of this document

First, a first-principles derivation of an input-only memory architecture
from the biology of human memory and the failure history of lifelogging.
Second, seven locked invariants, each with rationale, enforcement, and the
failure mode it forecloses. Third, a complete pipeline exposition with one
moment walked through every stage. Fourth, a formal domain model in which
invalid memory is unrepresentable. Fifth, an evaluation method in which
every miss mechanically names the work that fixes it. Sixth, a candid
account of the project's two stacks and the strangling plan between them.
Seventh, the strongest objections to all of the above, answered at full
strength, including the counter-literature (Chapter 18, Appendix L).

= Conceptual foundations

== The standard model: a brain never touches the world

The napkin's first drawing is not of the product; it is of every mind that
has ever existed: `[World] → Eyes/Ears → [Brain]`, with the loop closing
back into the world, annotated: _"because we can't manufacture other senses,
or most of the information is obtained through this."_ A brain never touches
the world directly. It receives narrow, lossy sensory streams, extracts
meaning at the moment of perception, and stores the meaning — never the
stimulus. TRACE copies exactly this: video for eyes, audio for ears,
extraction at the moment of capture, retention of meaning only. This is not
biomimicry for its own sake; it is the observation that the only working
memory system we know of is input-only, and that its constraints are
load-bearing. Eyes and ears become camera and microphone; the napkin's
"organs" become the sensor suite — pose, motion, place — the one sense a
device can manufacture beyond sight and sound, and the one that answers
spatial questions.

== Episodic memory is reconstruction, not playback

Human recall does not replay footage, because there is none. Remembering is
reconstruction from consolidated traces, schema-driven and confident even
when wrong [2]. Tulving's episodic/semantic distinction [1] maps directly
onto TRACE's two stores: the time-stamped claim log is episodic — events
located in time and place, sparse and literal — while the bound evidence
graph is semantic: consolidated, cross-referenced, queryable. The mapping is
load-bearing, not decorative. It predicts the interface between the stores:
consolidation runs episodic→semantic, never the reverse, exactly as the
night shift reads the log and never writes it. And the system's honesty
about reconstruction exceeds the biological original: where human recall
silently invents schema-consistent detail, TRACE's recall is forbidden to
assert anything that does not trace to a logged claim, and says "I don't
know" where a human would confabulate.

== Sleep consolidation: why the binder runs at night

The decision to concentrate deep binding in a nightly pass is likewise
borrowed from biology. Systems-consolidation research shows that the
mammalian brain replays the day's hippocampal traces during slow-wave sleep,
gradually binding them into neocortical structure [3] — an architecture
forced by the same constraint TRACE faces: deep integration is expensive,
and the organism cannot afford it while also perceiving. Night is when the
device is charging, thermally unconstrained, and free to run the big model
over the whole day at leisure. The napkin's phrase is exact: node creation
is _"always running in the background, but better nightly."_ Incremental
binding accelerates; the night shift perfects. The Hebbian slogan — cells
that fire together, wire together [35] — is the binder's actual operating
principle, transposed to text: claims that co-occur in time and place,
repeatedly, get bound into shared structure.

== Event segmentation: why capture is gated, not uniform

Human perception does not sample the world uniformly; it carves experience
into events at boundaries of change, and encodes richly at those boundaries
[4]. TRACE's capture follows the same economics (Chapter 9): the cheap
channels run continuously precisely because they are cheap, while the
expensive channel — deep visual description by a vision-language model —
fires only on attention, dwell, or change. Uniform deep capture would be
both unaffordable and pointless: most moments do not matter, and the value
of a memory is concentrated in the few that do. The scheduler that makes
this call is not an optimization detail; it is the system's model of what
deserves to be remembered well, which is why the project treats it as part
of the moat.

== Text as the retention format: the four arguments

The load-bearing decision — keep words, not media — rests on four arguments.

_Privacy._ Text is the only format whose retention can be made socially and
legally safe by construction. A sentence about a bystander is a
fundamentally different object from their stored face; the residue this does
not discharge is treated honestly in §12.7.

_Sufficiency._ The hypothesis under test is precisely that words carry
enough. Language is the interlingua in which modern machine reasoning is
strongest [7], and retrieval-then-reason over text is the best-understood
recall architecture available [12]. The strongest evidence against — the
verbal-overshadowing literature, in which describing a face degrades later
recognition of it [42] — is engaged directly in Chapter 18 and Appendix L,
because it is a critique of human verbalization under a recognition
criterion, not of machine extraction under a question-answering criterion,
and the distinction is measurable.

_Economy._ Text is orders of magnitude smaller than the media it replaces —
Appendix F's worked minute is roughly 2 KB against roughly 1.4 GB of 4K
video for the same span — and a lifetime of it fits on a phone. "Never
delete" (I3) is affordable only because of this ratio.

_Auditability._ A user can read every single thing the system knows about
them, line by line — an impossible offer for embeddings or media, and the
foundation of the trust the product sells.

== The resolution of the central tension

"Remember everything" and "respect everyone" are in tension only while the
retained artifact is media. Retain extracted meaning instead and the tension
dissolves: recall quality becomes a function of extraction quality — which
is measurable and improvable — while the surveillance artifact simply never
exists.

= Prior art and position

== The memex lineage: total capture as an old dream

Bush's 1945 memex [36] founded the genre and set its sixty-year trajectory:
capture everything, organize later. The lineage's lesson is that "later"
never comes — capture without retrieval-of-meaning is a landfill. Sellen and
Whittaker's constructive critique of lifelogging [41] sharpened the lesson
into design guidance a decade before this project: the value of a memory aid
lies in retrieving the right cues and facts, not in total archives, and
systems should be designed around the "five R's" of remembering rather than
around storage. TRACE takes that critique as a requirement rather than an
objection: it is a cues-and-facts system by construction, and the archive it
refuses to keep is precisely the one the critique found worthless.

== MyLifeBits and SenseCam: storage-first, and what it taught

Gemmell, Bell and Lueder proved the landfill empirically at life scale [9]:
MyLifeBits' bottleneck was never storage but structure. SenseCam [10] proved
the opposite pole — even passive photo capture measurably aids clinical
memory — while every deployment surfaced the social cost of visible storage.
Hoyle et al. quantified that cost from the wearer's own side: lifeloggers
themselves censor, delete, and manage bystander exposure [34]. Gurrin,
Smeaton and Doherty's survey of the field converges on cues-and-facts over
archives [37]. Together these justify TRACE's inversion: total capture,
linguistic retention.

== Ego4D and egocentric vision: the demand curve, measured

Ego4D [11] defines the benchmark tasks TRACE's question batteries descend
from — episodic memory queries against first-person video — and establishes
that long-horizon egocentric retrieval is hard even with the video retained.
That is the honest context for reading every recall number in this document:
the ceiling is not 100%, even for an oracle holding the footage.

== Retrieval-augmented generation: the supplier's ancestry

Lewis et al. [12] define the retrieve-then-generate shape the information
supplier inherits. TRACE departs from RAG in what is retrieved from: not a
corpus that happens to exist, but a memory constructed for retrieval under a
privacy invariant, with provenance and confidence as type obligations rather
than metadata conventions. Attribution — answers that cite — is promoted
from an evaluation criterion [31] to a construction rule; selective
prediction [13] and calibration [20] supply the formal frame for refusal;
the hallucination taxonomy of Ji et al. [32] is operationalized as the
grounding gate's checklist.

== The commercial field: an empty quadrant

Two axes organize the field: what persists (raw media versus derived text)
and where reasoning happens (cloud versus device). Screen-recording memory
tools, audio pendants, and camera glasses all sit in the raw-persistence
half-plane, differing only in which medium they hoard. The text-only,
device-perception quadrant is empty, and not by accident: occupying it
requires giving up the raw stream, which storage-first architectures cannot
do retroactively — their features, their indexes, and their user
expectations are built on the archive. Chapter 16 develops the consequence.

== Knowledge graphs and open vocabulary

The node layer is a knowledge graph in the broad sense of Hogan et al. [14],
with one deliberate deviation: open vocabulary everywhere. There is no fixed
ontology of entity types or predicates; the world names itself through the
extractors' text, and structure emerges from co-occurrence rather than from
a schema. The cost of that choice is weaker global consistency; the payment
comes at answer time, where evidence is quoted rather than inferred across
long relational chains.

= The seven invariants

Architecture is what remains constant while everything else iterates. TRACE
locks seven invariants; each is stated with its rationale, its enforcement
mechanism, and the failure mode it forecloses. Code that violates an
invariant does not merge — several are enforced by construction, so
violating them does not even compile against the domain model.

== I1 — No raw persistence

_Statement._ Raw pixels and audio are discarded the instant words are
extracted from them. There is no record path, no cache, no "temporary"
buffer that survives the perceptual moment.

_Rationale._ Every stored frame is a liability with no compensating asset:
it cannot be queried directly, and it is the artifact whose existence makes
the system a surveillance device. Ephemerality at the source is the only
privacy claim that survives an adversarial audit — deletion policies,
retention windows, and encryption of stored media all reduce to promises.

_Enforcement._ Capture code converts and drops in one motion; the
repository's ignore rules block media files as defense-in-depth; and in
`tracemem` the law is inherited in its hardest form: _raw is immutable and
no update path exists; pixels never leave the device._ Honesty note:
evaluation gold frames exist on the founder's development machine as
oracles — they are the measuring instrument (§13.2), not the product path,
and the phone build has never persisted a frame.

== I2 — Text-only egress

_Statement._ The only payload type permitted to cross the device boundary is
typed text carrying the identifiers of the source events it derives from.

_Rationale._ Local models may hit a quality wall (Chapter 17); the
architecture must allow routing reasoning to a stronger model without ever
routing media anywhere. Typing the boundary makes the safe path the only
path.

_Enforcement._ In the v0 stack, an eleven-line egress guard raises a privacy
violation for any payload that is not typed text with non-empty provenance —
short enough to audit in one breath, which is the point. In `tracemem` the
same contract lives in the container's boundary module.

== I3 — Append-only truth

_Statement._ The claim log is immutable and append-only; it is the single
source of truth. Everything derived from it — the evidence graph, every
index — is a disposable, replayable projection.

_Rationale._ Consolidation is experimental and will be wrong often;
retrieval structures will be redesigned repeatedly. If derived structure
were the truth, every such change would risk memory loss. With an immutable
log, any projection can be thrown away and rebuilt — the napkin's discarder
rule: marinated content that proves useless is dropped, never the raw
material.

_Enforcement._ The store exposes no update and no delete; corrections are
expressed as new claims and tombstones (Chapter 7), never as mutation.
Replays are deterministic, which Chapter 13's evaluation depends on.

== I4 — Provenance everywhere

_Statement._ Every claim, binding, citation, and egress payload carries the
event identifiers it derives from. An unsourced assertion is a construction
error.

_Rationale._ Citations are the product (answers must show their evidence),
diagnosis is the method (a wrong answer must be traceable to the claim that
misled it), and audit is the promise (the user can see where every
remembered fact came from).

_Enforcement._ Constructors: a binding rejects an empty evidence tuple; a
claim rejects a timestamp that disagrees with its provenance; an egress
payload rejects empty source lists. Provenance is not a logging convention —
it is a type obligation [19].

== I5 — Calibrated confidence; refusal over fabrication

_Statement._ Every binding carries a confidence intended to be calibrated;
links below the floor are refused, not hardened; at answer time,
insufficient evidence yields "I don't know."

_Rationale._ A memory's worth is its trustworthiness. One confident
fabrication — "you locked the door" when you did not — costs more trust
than a hundred honest refusals. The metric agrees: RAS subtracts
fabrications from corrects, so the optimizer and the ethics point the same
way.

_Enforcement._ Confidence is range-checked at construction; the refusal
floor is the binder's default disposition of weak evidence (Chapter 10);
calibration itself is a measured property (Chapter 13), per [20]; and in
`tracemem`, _grade degrades with derivation depth_ is a hard law — deep
derivations must be proportionally better-evidenced to be spoken.

== I6 — Unconstrained questions

_Statement._ There is no fixed question taxonomy, no menu of supported query
types. Users ask anything, natively.

_Rationale._ A constrained question surface is a product decision
masquerading as a safety decision: it hides hallucination by refusing to
hear the questions that would expose it. The honest path is open vocabulary
end to end — open observation kinds, open predicates, open questions — with
calibrated refusal as the safety mechanism instead of a menu.

_Enforcement._ The query type is a bare text string by design, and the
founder's locked decision to keep it so is recorded in the decision log
(Appendix D).

== I7 — Nothing is built until a missed question demands it

_Statement._ Every helper, sensor, channel, and feature must be authorized
by a diagnosed failure on a real question from a real capture.

_Rationale._ Perception systems invite infinite plausible work; intuition
about which channel matters is reliably wrong. The project's own history
supplies the cautionary tale: a 3D world renderer was built on intuition,
answered nothing, and was killed. The discovery loop — ask, miss, diagnose,
build exactly the missing channel — replaces guessing with evidence, and the
overnight self-play harness automates the asking.

_Enforcement._ Governance (Chapter 14): the plan-gate requires naming the
missed question before any build starts. The (A)/(B) diagnosis log supplies
missed questions mechanically. Even the two `tracemem` modules that exceed
the napkin — a prediction spine and the falsification harness — are flagged
_beyond-napkin_ in the constitution file, awaiting an explicit founder
ruling: the invariant applied to the repository itself.

== The invariants as a system

The seven interlock. I1 and I2 make the privacy claim structural; I3 and I4
make memory auditable and experimentation safe; I5 and I6 together make "ask
anything" compatible with "near-zero hallucination" — the refusal gate
absorbs what open vocabulary exposes; and I7 aims the whole machine at
evidence. Remove any one and the others weaken: without I3, diagnosis loses
its replay; without I4, refusal loses its justification; without I7, the
roadmap reverts to guessing.

// ═══════════════════ PART II ═══════════════════
#partpage[Part II · The Machine]

= The pipeline: from photons to answers

This chapter is the napkin's EXECUTION line, expanded stage by stage.
Appendix A maps every napkin phrase to its production counterpart; the
interactive companion (`interactive/metamorphosis.html`) renders the same
pipeline as one continuous transformation. The pipeline in one line:

#align(center)[
  #text(size: 9.5pt)[`[World] → Extraction ⬛ → TEXT → Binder → Node Creation ⬛ → Supplier ⬛ → LLM`]
]

== Stage 1 — Senses

Two streams open onto every second: video for eyes, audio for ears, plus the
device's manufactured sense — pose, motion, place — standing in for the
napkin's "organs." Neither audiovisual stream is a recording. Frames and
samples exist transiently in working memory, are read, and die; what
survives is only what was read from them. The cheap stratum (Chapter 9)
watches continuously; nothing else is awake.

== Stage 2 — Extraction

Extraction turns raw light and sound into addressed text, through four
mechanisms. The _blur gate_ triages every frame before anything else sees
it: a frame whose content cannot be read — motion smear, defocus — is
discarded immediately, and a frame that cannot be read is never written. The
_spend dial_ sets resolution and framerate by what the world is doing, not
by a clock: a still room is sampled almost for free, a fast reach is frozen
with a burst, a settled scene earns one expensive deep look. The _address
stamp_ fixes normalized coordinates and a timestamp on every reading before
meaning is attached: nothing is remembered without its address, and any
later claim can be walked back to the pixel and second that produced it.
The _signal–noise decipherer_ of the napkin is the composite of gate and
dial: what remains after both is signal, stamped and contextualized.

== Stage 3 — The macro picture

A vision-language model produces the napkin's _"macro picture of what's
happening"_: a scene-level gist — a morning kitchen, someone reaching for a
jar — that supplies context in both directions. Downward, it tells the
scheduler what matters in this scene; upward, it rides with every emission
so that later binding and answering know the setting a claim was born in.

== Stage 4 — The helpers

With context established, specialists are called for the job: an OCR reader
for the label, a state extractor for the jar, a detector for objects, ASR
for the voice, a sound tagger for the room. Each is the best available
understanding of its one slice of the world; each writes text; none knows
the others exist. No helper is architecture — remove any one and the rest
carry on — and the helper set is open-ended by design, discovered by
ablation rather than capped by a guess (§13.4).

== Stage 5 — TEXT

The output of extraction is the napkin's boxed word: TEXT. Text from all
helpers, marked by coordinates, appended to the immutable log. Every line
carries where, when, which helper, and how sure. This is the entire output
of perception: text the owner could read aloud.

== Stage 6 — The binder

The binder makes many readings into one moment. It does not understand the
kitchen; it observes that several lines share a where and a when — _"binding
the coordinates, physicality & temporal together"_ — and fuses them on that
evidence alone. Binding is evidence-driven, not semantic, which is why a
wrong binding can be reconciled later without touching what was read. The
output is the napkin's _first thought_: raw material that can be marinated
on. The napkin's own note is the design's humility: _"this is not a complete
Node, it's raw material."_

== Stage 7 — Node creation

Raw material becomes living cells — _"a physical living breathing cell that
can combine with fellow nodes to derive new things — 1+1 = 4, ≠ 2."_ A node
is a persistent thing (a jar, a person, a shelf) that thickens every time
the world confirms it. Nodes combine: co-firing histories derive facts no
sensor observed. The box carries the napkin's two governance rules:
encryption — only the person using the app can decipher (Chapter 12) — and
the discarder of meta: derived content that proves useless is deleted; the
raw beneath it, never.

== Stage 8 — The information supplier

A question does not go to the archive; it goes to the supplier, whose
contract is the napkin's phrase _just enough context_. The supplier walks
the graph, selects the few claims that bear on the question — three
memories, not three thousand — and packs them with their citations for the
reasoner. Retrieval quality, not model quality, is where answers are won,
which is why the supplier is a named black box and the model is not.

== Stage 9 — The LLM does what an LLM does

The last box is the least special. An ordinary local model [29] receives the
packed context and writes the sentence, under a grounding gate that admits
only clauses the packet supports. The model is swappable by design; the
memory that feeds it is not.

== What flows between stages

One direction, one format. World→Extraction: transient media, dead in
milliseconds. Extraction→TEXT: addressed claims. TEXT→Binder: claims.
Binder→Nodes: bound moments. Nodes→Supplier: evidence with provenance.
Supplier→LLM: a small cited packet. LLM→user: a sentence whose every clause
walks back to a claim, or a refusal. Nothing flows backward; nothing mutates
upstream.

= One moment, end to end

The worked example is the napkin's own scene. Times are illustrative; the
mechanics are the shipped ones, and Appendix F shows the same machinery as
raw wire-format records from a real v0 capture.

== 09:14:07, Tuesday, the kitchen

A person reaches for a jar and says something: _"we're nearly out of the
hazelnut stuff."_ Light and sound. This is the only moment that will ever
happen; everything after is about keeping it.

== The same second, inside extraction

The blur gate discards the smeared frames of the reach and keeps one legible
frame. The spend dial, idling on a still kitchen, spikes for the motion and
settles into one deep look. The macro eye reads the scene — a morning
kitchen, a reach toward a shelf — and calls the specialists. Three helpers
write four lines:

#block(inset: (left: 1.2em))[
#raw("09:14:07  x .44 y .48   label reads \"NUSSGOLD\"        verbatim 1.00
09:14:07  x .31 y .42   glass jar, ¼ full, lid ajar   gist 0.72
09:14:07  whole frame   morning kitchen, a reach      gist 0.61
09:14:09  mic           \"…nearly out of the hazelnut  verbatim 0.93
                         stuff\"", block: true)
]

The background is transcribed too — a kettle click at 09:14:05, footsteps
leaving at 09:14:12 — because one day the question will be "did I put the
kettle on?", and the answer will exist. The frame that produced all of this
lived roughly a hundred milliseconds. Frames kept: zero.

== The binder, that evening

Same spatial region, same seconds: the label line, the jar-state line, and
the spoken line fuse into one bound moment — _09:14, kitchen: the jar is
nearly empty, and it was said aloud._ The chime from the neighbor's balcony,
seven seconds and one wall away, is scored against the same arithmetic and
refused (Appendix J shows the numbers). Raw material; not yet a node.

== The night

The moment is absorbed into cells. The JAR node thickens — seen seven times
since 12 May, a quarter full today. The PERSON node records that it was
said aloud. The PANTRY shelf carries its forty-one sightings. Nodes fire
together, and the night shift derives a third thing no sensor observed:
_you run out roughly every six weeks_ — graded as derived, citing the three
readings that earned it. A second candidate, "prefers the 400 g size,"
finds no rent-paying evidence and is deleted. The raw beneath is untouched,
so a better idea tomorrow gets the same evidence.

== Weeks later: the question

_"Do we need more of that spread?"_ The supplier walks the nodes and packs
three memories: the quarter-full sighting with its date, the spoken
sentence, the derived six-week cycle. The model writes: _"Almost certainly.
It was a quarter full on 12 June, you said so yourself — and it's been about
six weeks."_ Each clause carries its citation. Ask instead "which brand does
my sister buy?" and the answer is _"I have never observed that."_

== What the example proves

That the pipeline composes: address-stamped extraction makes binding
possible; binding makes nodes possible; nodes make derivation possible;
provenance makes the final sentence auditable and the refusal principled.
And what it does not prove: that extraction is rich enough on real, messy
weeks — which is exactly what the falsification gate exists to test.

= The domain model

The vocabulary below is the live system's. The unit of memory is the
_claim_; the v0 stack's equivalent object is the observation, and Appendix F
shows its wire format.

== Claim — the atom

A claim is one line of extracted text with its address and its provenance:
what was read, where in the frame (normalized coordinates), when
(timestamp), by which helper, and how it is graded. Claims are immutable and
append-only (I3). The claim log renders back to a human-readable
transcript — the memory can be read, in order, line by line. One field
deserves special note, inherited from the v0 observation record: the
_refutation cue_, in which a claim announces at birth what future evidence
would disprove it. A shadow misread as a bird is expected to lose its track
within a second; when the track instead persists and earns a deep look, the
cue's condition fails and the claim's standing strengthens. Falsifiability
is a field, not a philosophy.

== Provenance — the birth certificate

Event identifier, source channel, capture time. Every structure above the
log — episodes, entities, patterns, citations, egress payloads — carries the
provenance of everything it was built from (I4). A wrong answer is
therefore traceable, mechanically, to the claim that misled it.

== Grade and confidence — the currency of trust

Confidence is a probability, range-checked at construction and intended
calibrated [20]; grade orders trust across derivation depth. A claim read
directly off the world — a verbatim label, a transcribed sentence — is
witnessed; everything built above it carries a grade that degrades with
derivation depth, a hard law of the repository. The refusal gate consumes
grades: deep derivations must be proportionally better-evidenced to be
spoken at answer time.

== Episode — the bound moment

The binder's output: claims fused by co-occurrence in space and time into
one event, carrying the evidence tuple that formed it. Episodes are
projections — rebuildable from the log — and subject to _reconcile_: when
later evidence shows a binding was wrong, a tombstone retires it and a
corrected episode replaces it. Correction is new information, never
mutation.

== Entity and pattern — the living cells

An entity is a node with a history: the jar, the person, the shelf — each a
list of dated confirmations, resolved across days by identity scoring
(Appendix J.1). A pattern is a nightly derivation over entities: the
six-week cycle, the morning routine. Patterns are the napkin's 1+1=4, and
they are deliberately the most disposable layer in the system: the pruner
deletes any that stop paying rent, and the raw claims beneath guarantee
they can be re-derived or replaced.

== Query, citation, and the answer contract

Answering is a typed pipeline: cue (read the question), retrieve (walk
entities and episodes for bearing claims), pack (assemble just-enough
context, every item citable), ground (emit only clauses the packet
supports; abstain otherwise). The contract's output is either a cited
answer or an honest abstention; there is no third shape. The query type
itself is a bare text string (I6).

== Constructors, not validators

Throughout, invalid states are unrepresentable rather than checked-for:
claims without provenance, confidences outside range, bindings without
evidence do not pass construction [19][22]. A malformed memory is not a bug
to find later — it is an object that never existed.

= Software architecture

== The order of authority

The `tracemem` constitution file states a precedence unusual enough to
quote: the napkin outranks the code; the code outranks the tests; the tests
outrank the campaign documents; the campaign documents outrank the specs.
Prose lost its authority in this project once already (Chapter 15), and the
ordering makes sure the running system, not the latest document, wins
arguments.

== Contract-first modules

Every source file carries a contract header: what it OWNS, its IN→OUT, its
TEST, and its spec reference. The module tree maps one-to-one onto the
napkin's boxes — `extraction/`, `text/`, `binder/`, `nodes/`, `container/`,
`supplier/`, `llm/` — so a reader can hold the drawing in one hand and the
repository in the other. Implemented logic is tested green; unimplemented
bodies raise `NotImplementedError`, and their acceptance oracles exist
ahead of them as xfail-marked tests.

== The test suite as ledger

The test run is the project's status report, by design: green is the
regression wall (implemented and guaranteed); xfail is the TODO ledger,
each entry naming the spec section it awaits; a failure is a real bug that
outranks all other work. As of 2026-07-21: 274 green, 1 xfail, and the
remaining stubs are exactly the hardware/model adapter set — the boundary
between the thinking machinery (real) and the senses (fakes), stated
plainly.

== Hexagonal: ports and adapters

The v0 stack is hexagonal in the classical sense [21][22] — a pure domain,
an application layer of use-cases, ports outward, adapters inward — and
`tracemem` keeps the discipline where it matters most: every hardware and
model dependency (OCR, ASR, camera eyes, the cipher, the local LLM) sits
behind a port with a deterministic fake. The crown test exercises the
entire pipeline on fakes; making an adapter real changes no domain code.

== Event sourcing and disposable projections

The append-only log as truth and everything else as replayable projection
is event sourcing [23] with CQRS-flavored read models [24], chosen for
exactly the property Chapter 10 needs: consolidation can be wrong, thrown
away, and re-run over history without loss. Replays are deterministic;
evaluation depends on it.

== The hard laws

Five laws inherited from v0's operational history bind all of it: raw is
immutable — no update path exists; pixels never leave the device; one model
on the GPU at a time (a thermal and correctness constraint learned when
live capture went dark, silently, under a shared GPU); grade degrades with
derivation depth; and every capture gap is witnessed — if the senses were
dark, the memory must say so rather than paper over it.

== The crown test

One test stands above the suite: a shuffled synthetic week is fed through
the whole machine — episodes form, entities accrete, nightly patterns
derive, a question is asked, a cited answer comes back, and an unanswerable
question is honestly abstained from. It passes. It is the executable form
of Chapters 5–7, and it is what "the thinking machinery exists" means when
this document says it.

= The perception subsystem

== The cheap stratum: always-on helpers

Perception is two economies. The cheap stratum — detection [26], OCR,
speech recognition [30], sound-event tagging against the AudioSet ontology
[39], motion and pose [15] — runs continuously because it can: these models
are small, neural-engine-friendly, and power-light. Open-vocabulary naming
rides on MobileCLIP [27], chosen by audit for exactly the properties the
substrate demands: fast on the neural engine, words rather than prose,
vocabulary growth without retraining. The expensive eye — deep description
by a vision-language model [17][18][38] — runs rarely, because it must.

== Salience: deciding what deserves the expensive eye

The scheduler prices every track by dwell, novelty, and stability — a
wearable-economics translation of the computational-attention literature
[8]. A still room earns almost nothing; an entering hand spikes the
framerate; a settled new object earns the deep look. This is event
segmentation (Chapter 2) turned into a scheduler.

== The budget: a token bucket with no overdraft

Deep looks are governed by a token bucket [28]: a hard hourly budget,
refilled at a measured rate, spent by salience, with no overdraft path.
Attention is a budget, not a vibe; the system can always account for why it
looked hard at one moment and not another, and the budget's refill rate is
an empirical property of the device, not a config guess.

== The progressive enrichment ladder

Attention deepens in rungs — glance (a jar), read (the label), state
(three-quarters empty, lid ajar), context (a German promo sleeve, and
therefore probably a German kitchen) — and each rung emits only the delta:
what the previous rung did not already know. The same fact is never stored
twice; storage grows with new knowledge, not with time spent looking.

== The measured frontier

The first real number exists, and it is encouraging without being
sufficient: over 111 real captured frames, mechanically scored against
pinned frontier-model ceilings (§13.2), L1-verbatim recall is *0.974* — a
2.6% gap between what the extraction stack reads and what the best
available oracle reads from the same frames. The audit also produced a
diagnosed lesson — a cropping law confirmed on meal scenes (2/4 recovered
on crops versus 0/4 on full frames) — the miss-diagnose-fix loop of I7
operating on perception itself. The honest caveats: L1-verbatim is the
mechanical tier of the claim-match instrument, not the full score; and 111
frames are frames, not weeks.

= Consolidation: the night shift

== The job

Read the day's claim log; bind by co-occurrence; thicken entities; derive
patterns; refuse weak links; discard failed meta; touch nothing raw. The
napkin's underlined words — _always running in the background, but better
nightly_ — set the schedule: incremental passes keep the memory current;
the night pass, on a charging and thermally free device, does the deep
work. Congregate, dedupe, bind; resolve identities (today's jar is the same
jar, thickened, not a fourth jar); run the derivation pass; rebuild the
projections; toward dawn, let the discarder drop what the night's better
judgment replaced.

== The anatomy

The consolidation heart is built as guarded stages: _guardrails_ (classes
of assertion that may never be derived, because they would outrun any
evidence); four _derivation kinds_ (the legitimate shapes of 1+1);
a _selector_ (which co-firing histories deserve the model's attention
tonight); a _judge_ (does the candidate cite enough to survive — refusal is
the default disposition); the _night_ runner; the _pruner_ (rent collection
on old patterns); and _remap_ (re-pointing structure when reconcile retires
an episode). All of it runs today against synthetic weeks; its inputs
become real when the extraction adapters do.

== Accelerator, not gatekeeper

Consolidation makes answers better and faster; it must never become the
condition for answering at all. The supplier can serve from episodes alone —
unconsolidated memory is slower and flatter, not absent. Chapter 6's
pharmacy-bag class of question — asked the same evening, before any night
shift — is answered from the raw scaffold with a single citation. A memory
that only works after a good night's sleep is a demo, not an organ.

== The devil's advocate, kept in the room

Derivation is where a memory system starts lying to itself, which is why
the judge prices skepticism in: every candidate pattern must survive an
explicit attempt to refute it from the same evidence, weak links are
refused at write time rather than hardened, and the system deletes its own
failed thoughts without sentiment. The napkin's discarder is not cleanup;
it is epistemic hygiene.

= Recall: grounded answering with calibrated refusal

== The loop

Cue → retrieve → pack → ground. The question is read for its entities, time
hints, and kind; the supplier walks the graph; the packet is assembled
small — just enough context, every item citable; and the grounding gate
lets a clause through only if the packet supports it. The reasoner is local
[29] and ordinary; on v0 the heuristic fallback refuses everything, which
is the correct degenerate behavior for a memory: no reasoner, no guessing.

== The grounding gate

The gate's checklist is the hallucination taxonomy [32] operationalized,
inherited clause by clause from the legacy engine's scar tissue (Appendix
E of the strangling plan): binary-state discipline — occupancy, open/closed,
on/off asserted only on direct literal support; phantom-class defenses on
existence questions, where prior plausibility most strongly tempts
invention; absence and negation handled from positive contrary cues, the
hardest honest answer for a generative system; and over-specificity
suppressed — the answer may not be more precise than its evidence.

== Refusal as calibration

Refusal is not a failure mode; it is the mechanism that makes open
questions (I6) safe. The formal frame is selective prediction [13]: answer
only above a confidence bar, and measure the risk–coverage trade rather
than assert it. Attribution completes it [31]: citations are checkable
objects, so a wrong answer is a diagnosable event. The refusal-calibration
line (§13.8) is where this chapter's theory earned its first zero.

== What answering feels like

Short, cited, and honest. _"Almost certainly — a quarter full on 12 June,
you said so aloud, and it's been about six weeks."_ Or: _"I have never
observed that."_ The product bet, stated in Chapter 18.12: users forgive a
memory that sometimes says "I don't know" and never forgive one that lies
once.

// ═══════════════════ PART III ═══════════════════
#partpage[Part III · Reality]

= The privacy architecture

== Layer 1 — Ephemerality at the source

Raw media is converted and dropped in one motion (I1). There is no
retention window to configure, no deletion policy to trust, no archive to
breach. The privacy property is not that stored media is protected; it is
that stored media does not exist.

== Layer 2 — The typed boundary

Only typed text with provenance may leave the device (I2). The guard is
deliberately tiny — eleven lines in the v0 stack — because auditability of
the boundary is itself a security property.

== Layer 3 — Encryption under the user's key

The text memory is encrypted with AES-256-GCM [33]: key derived from the
user's secret, a random 96-bit nonce per payload, and the container format
version bound as associated data, so ciphertexts authenticate their own
container. The napkin's phrase — _"encryption, i.e. people using our app
can decipher"_ — is this codec: unreadable to the platform, the cloud, and
the thief; readable only to the user's own application holding the user's
key. The `.trace` container carries three layers with deliberately
asymmetric guarantees: a header readable without the key (version, device,
counts); the RAW claim log, append-only and encrypted; and the META layer —
nodes, edges, confidence — encrypted, deletable, and re-derivable. Lose the
meta and nothing is lost; lose the raw and everything is. Status honesty:
`tracemem`'s cipher adapter (libsodium) is presently stubbed, and the
ledger in the front matter says so.

== Layer 4 — Repository and process hygiene

Defense-in-depth extends to the development process: the repository's
ignore rules block raw video, audio, and still formats globally; the commit
gate verifies zero media binaries staged; the CI gate runs on every push.
The team's own workflow is subject to the invariant it ships.

== The threat model, tabulated

#table(
  columns: (1fr, 1.1fr, 1.1fr),
  stroke: 0.4pt + rgb("#ddd"),
  inset: 6pt,
  table.header([*Threat*], [*Storage-first system*], [*TRACE*]),
  [Device theft], [media archive exposed], [ciphertext under user key; text-only plaintext],
  [Cloud breach], [media archive exposed], [nothing off-device but guarded text with provenance],
  [Subpoena], [stored footage discoverable], [no footage exists; the text store is the complete universe],
  [Insider access (vendor)], [policy-limited], [architecturally empty: no media to access],
  [Bystander recording], [permanent images of non-consenting parties], [no image persists; bystanders appear only as typed gist],
  [Function creep (a future feature "re-opens" media)], [one flag away], [impossible: the media was never kept],
)

Appendix I walks four of these as scenarios, including the hardest one —
the coerced unlock — where the honest answer is that text is real exposure,
bounded to what words carry.

== Regulatory alignment

Text-only, minimal, purpose-bound retention is data minimisation under GDPR
Article 5(1)(c) [6]; capture-time conversion is privacy-by-design in the
original, architectural sense [5]; user-key-only decryption aligns with
data-protection-by-default. None of this is claimed as legal clearance —
wearables face jurisdiction-specific recording law — but the architecture
starts from the strongest position a perception device can occupy: the
sensitive artifact class is never instantiated.

== What architecture cannot discharge

Honesty requires the residue stated. Perceiving people into text still
touches privacy: "Anna said she's pregnant" is sensitive with no pixel
involved. The bystander literature on wearable cameras [34] transfers in
part to any wearable perception. Product-level obligations therefore
remain: disclosure norms for wearers, redaction policies for bystander
speech, retention and export controls in the user's hands, and the wearer's
own social contract. The architecture makes the worst artifact impossible;
it does not make the remaining ones weightless. This section exists so that
no investor, customer, or regulator can say the project hid the residue
behind the moat.

= Evaluation: every miss names the next build

Measurement is the most opinionated subsystem in TRACE. It is designed so
that failure is never ambient — every miss is attributed, mechanically, to
a cause that names the work that fixes it.

== RAS: fabrication priced like a loss, because it is one

The headline metric over a blind adversarial battery on a real capture:

#align(center)[RAS = (correct − made-up) / total]

A fabricated answer subtracts what a correct one adds; an honest refusal
costs nothing. The metric encodes the product ethics (I5) so directly that
optimizing the number and behaving honestly are the same act. The
qualitative bar attached to it: a stranger asks about your day and is
amazed, with near-zero made-up answers.

== OAG: the price of throwing the pixels away

The oracle-answerability gap: among questions an offline oracle with the
raw frames can answer, the percentage the retained text cannot. OAG is the
direct measurement of the retention decision's cost (§2.5) and the
empirical estimator of the central hypothesis (Appendix K). Raw media's
only legitimate role in the system is here — oracle-side, offline, never
entering production recall. In `tracemem` the same idea is systematized as
pinned _ceilings_: frontier-model readings of the same frames, cached and
versioned, so every extraction score is a fraction of a known maximum
rather than a free-floating number. Current audited state: 111 ceiling
frames carrying 4,674 claims; against their mechanical tier the extraction
stack reads 97.4% (§9.5). Ceilings are re-pinned when the frontier moves;
the score is always relative to the best reader rentable, which is the only
honest definition of "lossless-enough."

== The (A)/(B) instrument

Every miss is classified: (A) the fact was never captured — the context was
not lossless enough — or (B) the fact was in the store and the brain failed
to reach, hold, or reason over it. The classification is mechanical, not
judged: every answer logs what the reasoner looked at, so a miss either had
the evidence in view or did not. (A) misses authorize new channels (I7);
(B) misses direct work to binding, retrieval, or refusal calibration. If a
miss cannot be classified, the instrument itself is declared broken.

== The method: sufficiency, then necessity, then efficiency

Three questions, answered strictly in order, never conflated. _Sufficiency_
(brute force, offline): on a recorded clip, thermal and token limits do not
apply; throw everything — deep VLM on every frame, full pose track, OCR
everywhere, full audio — and ask only whether the brain can answer the hard
set at approximately zero hallucination at all. This isolates "does the
idea work" from "can we afford it." _Necessity_ (ablation): remove one
channel at a time and re-score; a removal that breaks no answer is not
load-bearing, and the helper set is thereby discovered rather than guessed.
_Efficiency_ (last): only with the necessary set known does the salience
scheduler return, to approximate that set within the live budget.
Optimizing before sufficiency is proven is how projects die with beautiful,
useless engineering.

== The first honest baseline

The v0 proving ground was a 92-second outdoor walk with a 25-question
adversarial set, scored from frozen answers: 16 correct, 6 wrong, 3
refused — RAS 40.0, hallucination 27.3%. The diagnosis: 8 of 9 misses were
(B) — wrong-object bindings, confident-wrong binary states, one counting
failure, retrieval misses — and 1 was (A), the head-pose channel that two
spatial questions demanded, correctly refused rather than fabricated. The
number was poor, the diagnosis was precise, and both are reported because
a document that hides its worst number teaches readers to distrust its
best one. Appendix C carries the full scorecard.

== Anti-overfit machinery

Gold answer keys are hash-pinned; a silent edit to an answer key breaks the
build. Datasets carry tuning-exposure flags, and the baseline's own
validation clip is flagged as tuning-contaminated rather than quietly
promoted. The pitch-readiness bar includes a cold second capture — never
tuned on — passing a private regression check before any external claim.
Question batteries are written blind: the author has not seen what the
system captured, so the battery samples the world's distribution, not the
system's strengths.

== The self-play flywheel

Question generation itself is automated: an overnight job drives batteries
against the day's memory, mines the misses, and files them into the (A)/(B)
queue. The system that answers questions by night also discovers, by night,
which questions it cannot answer — turning I7's discipline into a
continuously running loop rather than a quarterly ritual.

== From 27.3% to zero: the refusal-calibration line

The gap between the baseline and the invariant was the project's daily work
for weeks, and it is the workstream where the second contributor deserves
naming: the refusal-calibration and benchmark line, run with research
collaborator *Latheesh Roy* under the founder's direction, tightened the
grounding gate and the confidence floors until confident-wrong answers
reached *zero on the reproducible benchmark battery* — the measured basis
for the product claim "it cannot lie to you," demonstrated as: it runs, it
cites, it refuses. Two honesty notes bound the result. The zero is a
battery property, not a theorem: it holds on the frozen adversarial set and
its planted unanswerables, and the cold-capture guard (§13.6) exists
precisely because a zero that has not survived a never-tuned capture is a
provisional zero. And the zero is bought partly with refusals: driving
made-up answers to nothing raises the refusal rate, and whether users
accept that trade is a product question (§18.12) the beta exists to answer.

= Engineering governance

A small team with an ambitious architecture survives on discipline that is
cheaper to follow than to break. TRACE's governance is code where possible,
ritual where necessary.

== The merge gate

One command enforced identically three ways — locally, as the pre-push
hook, and in CI on every push: formatting and linting; strict typing over
domain and application; complexity and function-length ceilings; dead-code
detection with zero tolerance in production code; frozen-gold hash
verification; the focused evaluator tests; and a coverage floor over the
domain (87% at the v0 baseline). The gate is the definition of done.

== One source of truth, read first, updated last

The repository's constitution and specs govern execution. Every working
session starts by reading them and ends by updating them. The rule exists
because the project's early history includes divergence between
documentation and reality — including an acceptance failure traced to
desk-testing a stale build — and the fixes are procedural: a build stamp
(the git SHA in the app's status line and in every posted artifact),
artifact-level verification, and the standing instruction to never trust
"installed."

== The plan-gate and the anti-diversion law

Before any build: name the roadmap item and the missed question that
authorizes it (I7). No authorization, no build. The law's origin is a real
casualty — the 3D world renderer, built on intuition, needed by no
question, killed on diagnosis — and its function is to make that class of
detour structurally difficult. Corollaries: pruning is measured, never
aesthetic; and re-evaluation of locked component choices requires new
diagnostic evidence, not new enthusiasm.

== Honesty as an artifact

Phase reports record what was verified against the live code, including
corrections of prior claims; evaluation reports carry their contamination
flags; the README states which invariants are proven and which are targets.
The document you are reading inherits the same rule — see §4.1, §9.5,
§12.3, §13.8 — and the front-matter ledger is its enforcement.

= Two stacks, one product: an honest history

== v0: the stack that runs

The reader doing diligence will find two repositories, and deserves the
story before the surprise. v0 has run continuously since June 2026: live
capture feeding an always-on hub, a nightly consolidation job, an encrypted
store, an iPhone capture app, and the evaluation battery. It produced the
first disciplined binder — 36 entities, 58 bindings, 144 weak links refused
on the proving clip — the first honest scores (§13.5), the
refusal-calibration zero (§13.8), and most of the hard laws (§8.6). It also
accumulated what every first stack accumulates: prose documents that
drifted from the code until, in mid-July 2026, the founder deleted every
one of them and declared that the present tense lives only in code, tests,
and running processes. That deletion is why this document cites ledgers
instead of promises.

== The greenfield: the napkin, rebuilt

Days later the architecture was redrawn by hand — the napkin — and
`tracemem` was scaffolded from it: specs first, contract headers in every
file, fakes behind every port, the crown test as the spine, xfail as the
TODO ledger. The napkin was transcribed verbatim into the repository as its
constitution, outranking everything including the specs. v0's lessons are
inherited as laws rather than as code.

== The legacy engine: what v0 knows that a rewrite would forget

v0's answer engine — roughly 2,900 lines that produced every baseline
number — predates the domain model and contains 47 broad exception
handlers. It is also a repository of earned answer-quality defenses, bought
one hallucination at a time on real captures, and the strangling plan's
first rule is that none of them may be lost in translation: the
binary-state discipline (a sound event does not prove a crowd; a stray
cable does not prove a phone was connected); the phantom-class watchlist
guarding existence questions; absence-and-negation machinery for answering
"no" from positive contrary cues; cross-lingual matching, learned from
captures in a bilingual environment, where English questions must match
German OCR; and the dossier-building craft that Chapter 11 formalizes as
the supplier.

== The strangling sequence

The migration follows the strangler fig [25][40]: v0 keeps running as the
capture organ and the measuring baseline while `tracemem`'s adapters come
real in dependency order — cipher, OCR/ASR, the camera eyes, the phone tap.
Every extracted capability lands behind a port with tests that encode the
legacy behavior it must preserve, and the baseline battery re-runs after
each extraction. The operational scar tissue transfers with it: capture
dies silently under a shared GPU and must be watched by liveness checks;
embeddings needed a different engine than the reasoner; phone deploys stall
in reproducible ways; a store must be snapshotted and shadow-served to be
measured without killing capture. v0 is decommissioned by explicit founder
decision when the falsification gate runs green on the new stack — not by
drift, and not before.

= Market position and the moat

== The quadrant

Two axes organize the field: what persists (raw media versus derived text)
and where reasoning happens (cloud versus device). Screen-recording memory
tools, audio pendants, and camera glasses all sit in the raw-persistence
half-plane — differing only in which medium they hoard. The text-only,
device-perception quadrant is empty, and not by accident: occupying it
requires giving up the raw stream, which storage-first architectures cannot
do retroactively — their features, their indexes, and their user
expectations are built on the archive. An incumbent cannot follow without
abandoning its own foundation. That is what makes the position a moat
rather than a feature.

== Why now

Three curves cross. On-device AI crossed the capability threshold: billions
of phones run local models, and sub-second on-device vision is commodity.
AI wearables ship in volume — roughly seven million camera glasses in 2025
alone — proving demand for the form factor while their retention
architecture proves the objection: the always-on recorder category is a
graveyard, its best-funded entrant shut down with assets sold to HP for
\$116M in February 2025. And the EU AI Act's biometric provisions, in force
since February 2025, turn "structurally non-retaining" from a philosophy
into a procurement criterion, on the continent where this company is being
built.

== Why incumbents want it and cannot build it

For platform acquirers, an input-only memory is the wearable strategy
without the surveillance liability that has repeatedly burned camera
products. Their business models monetize retained data; their privacy
stacks deliberately stop at the digital life. The acquisition logic is
strengthened, not weakened, by the moat's nature: the asset is an
architecture and its measured evidence — the invariants, the evaluation
trail, the scheduler — none of which can be bolted onto a storage-first
product without a rewrite indistinguishable from starting over. If the
capability matters to them, they license it or acquire it; both outcomes
require TRACE to exist first. The licensing precedent is the layer
companies — Arm and Dolby own a layer, not a box — and the `.trace`
container plus the text-only context boundary are designed to be exactly
such a licensable layer.

== The demo that proves the moat

The pitch deliverable is designed to make the architecture felt: a hero
capture answered live with citations; the no-raw-media proof panel — frames
visibly converting to text and dying, the store shown text-only; and the
live "ask it anything" moment where an honest refusal lands as a feature.
An audience that watches surveillance become structurally impossible on
stage has understood the company.

= Risks and open problems

Stated plainly, ordered by severity, with the mitigation that exists and
the trigger that would escalate each.

== The central hypothesis may be false

Text may not carry enough of the visual world. Mitigation: OAG and the
ceilings exist to measure exactly this; the sufficiency phase brute-forces
the best case before efficiency constrains it; the measured frame-level gap
is 2.6% (§9.5). Escalation trigger: a sufficiency run on a clean real week
in which the brute-force text scaffold still misses a material share of
oracle-answerable questions. That result would demand rethinking the
retention format itself, and no amount of scheduling cleverness would
matter. The project fails honestly in that world rather than pivoting to
stored media.

== The zero must survive the cold

Confident-wrong answers are at zero on the reproducible battery (§13.8);
the risk is distribution shift. Mitigation: the cold-capture guard — a
never-tuned capture must pass a private regression before any external
claim; hash-pinned golds; contamination flags. Escalation trigger:
hallucination reappearing on cold captures under a disciplined binder
would point at the reasoner, opening the measured text-only hatch (I2-safe
by construction).

== The senses are not real yet

The thinking machinery runs; the hardware adapters are stubs. The risk is
not that the adapters are hard — v0 proves each exists — but that their
quality on device, on battery, all day, is below what the ceilings assume.
The battery and thermal budget on glasses-class hardware is unmeasured, and
this document says so rather than extrapolating.

== Local models may be the wall

The local reasoner and VLM [17][18] may cap binding or answering quality.
Mitigation: the hatch — binding and answering can escalate to a frontier
text-only model with the privacy posture unchanged, because text was the
only thing allowed out from the first commit. The decision is a benchmark
delta, not a philosophy. Residual: dependence on a frontier vendor for the
deep pass, bounded by the fact that only guarded text ever leaves.

== Consolidation may not hold at life scale

If disciplined binding degrades over weeks — entity resolution drifting,
derived nodes accumulating subtle wrongness — the graph's value erodes.
Mitigation: accelerator-not-gatekeeper (the scaffold always answers);
replayability (every binder version can re-run history, I3); refusal (the
graph prefers silence to error). Honesty: this is the research risk. The
crown test binds cleanly; a life is noisier than a test.

== Two stacks is a tax, and one founder built this

Every week both stacks run is a week of split attention; the strangling
plan bounds it, and the tax is admitted. Bus factor is one, and the seat
this document exists to fill is empty (Chapter 19). The mitigations are the
ones in evidence: a constitution, contracts, tests as ledger — a repository
built to be joined — plus the collaboration already running (the
refusal-calibration line, §13.8).

== Bystander and social risk

Architecture removes stored media; it does not remove the social fact of
being perceived. §12.7's product obligations stand; recording-law
heterogeneity across jurisdictions is a compliance program, not an
architecture patch; and the possibility that society rejects even text-only
wearable perception is priced in Chapter 18.3 rather than assumed away.

= Objections and responses

Every serious reader of this architecture raises a version of the same
dozen objections. They deserve direct answers, in one place, at full
strength. Where an objection is partially right, the response says so.

== "If you throw away the pixels, you'll throw away the answer."

The strongest objection, and the one the whole evaluation apparatus exists
to face. It is a measurable claim, not a debate: OAG quantifies exactly the
questions the raw-frame oracle answers that the text cannot; the
sufficiency phase maximizes the text side before any efficiency constraint
bites; and the enrichment ladder exists to spend deep perception where
tomorrow's question is likeliest to land. The honest current state: the
frame-level gap is 2.6% (§9.5), the week-level gap is unmeasured, and if
the gap ever proves irreducible at the sufficiency limit, the hypothesis is
falsified and the premise fails — a possibility the risk register states
rather than hides. What the objection cannot claim is that the alternative
escapes the problem: storage-first systems defer extraction, they do not
solve it, and they pay the surveillance price forever while deferring.

== "A verbal description of a scene is a pale shadow of the scene."

True — and the wrong comparison. The competitor is not the scene; it is
human memory of the scene, which is itself a sparse verbal-categorical
trace reconstructed on demand [1][2]. TRACE does not need to beat the
videotape; it needs to beat the wearer's own recollection, with citations,
at near-zero fabrication. The strongest scientific form of this objection
is the verbal-overshadowing result [42]: describing a face in words
degrades later recognition of that face. Appendix L takes it seriously,
and the two-part response is structural. First, overshadowing is a human
phenomenon — the verbal trace interferes with the human's own perceptual
memory; TRACE's extraction does not overwrite anyone's memory, it
supplements it with a second, citable one. Second, the criterion differs:
overshadowing hurts recognition (pick the face from a lineup), while TRACE
is evaluated on question-answering over facts — and where a described
detail is genuinely unrecoverable from text, OAG counts it, which is
exactly what the instrument is for.

== "People will not wear a camera, period."

The social objection. People already carry always-on microphones and
cameras in their pockets and on their wrists; what they reject — and what
jurisdictions legislate against — is retention and replay. TRACE's answer
is not "trust us" but "there is nothing to distrust": no stored image of
any bystander exists one second after the moment. That claim is
demonstrable on stage and auditable in code. It may still fail socially —
§12.7 and §17.7 keep that residue on the books — but it fails from a
categorically stronger position than any recording device.

== "Local models are too weak to bind a day correctly."

Possibly. The architecture's response is the measured hatch: binding and
answering can escalate to a frontier text-only model with the privacy
posture unchanged (I2). The decision is a benchmark delta, not a
philosophy: local is preferred, cloud-text is permitted, raw egress is
impossible. The objection's teeth are economic, and the mitigation is the
same as everywhere in this design: spend depth only where salience earns
it.

== "The graph will silt up with garbage over months."

The scaling objection, and the project's honest research risk (§17.5).
Three structural answers: weak-link refusal keeps coincidence out of the
graph at write time; projections are disposable, so a better binder can
re-marinate history at any time (I3); and the graph is an accelerator,
never a gatekeeper — recall can always fall back to the raw scaffold. What
these do not answer is whether any binder discipline holds at life scale;
that is what the phased evaluation is for.

== "Why not just embeddings? Vector search over frames is simpler."

Embeddings are in the system — as projections, rebuildable accelerators
for retrieval. They are disqualified from being the truth for three
reasons: they are not auditable by the owner (no one can read what a
vector of their kitchen contains); they are not citable at the claim level
(I4); and they freeze a model's worldview into the store — a new encoder
means re-embedding, which is fine for an index and catastrophic for a
memory. Text is the only format that is simultaneously queryable,
auditable, citable, and model-independent.

== "OCR and ASR errors will poison the memory."

They will enter it — every channel is noisy. The defenses are layered:
per-claim confidence at capture; cross-channel corroboration at binding
(an OCR misread that nothing else co-occurs with binds to nothing); the
refusal floor at answer time; and the refutation-cue field, which invites
later evidence to overturn earlier error. The design position: noise in an
auditable text store is a manageable disease; noise in an unauditable one
is undiagnosable.

== "This is just RAG with extra steps."

The recall stage is RAG-shaped, and the document says so [12]. The extra
steps are the product: a corpus that is machine-perceived under a privacy
invariant rather than scraped; provenance as a type obligation rather than
a convention; refusal as a scored, calibrated outcome rather than a
failure; and a nightly consolidation layer that RAG systems do not have
because their corpora do not accrete a life. Dismissing a system by naming
its weakest structural analogy is a critique this chapter welcomes — it is
how the 3D renderer died — but here the analogy covers one of nine stages.

== "The salience scheduler will miss the moment that matters."

Sometimes it will — a budget is a bet. Two answers. First, the cheap
stratum never blinks: OCR, ASR, sounds, and sensors record continuously,
so a missed deep look is a degraded memory, not an absent one. Second,
every such miss is visible: it surfaces as an (A)-diagnosed failure, and
the budget, weights, or ladder thresholds move in response (I7). The
scheduler is not claimed optimal; it is claimed instrumented — its errors
are the training signal for its own next version.

== "Encryption with no vendor key means no recovery."

Correct, and chosen. A memory this intimate with a vendor-side recovery
path is a memory with a second reader. The design accepts the
consumer-grade consequence — lose the key hierarchy, lose the memory — in
exchange for the categorical claim of §12.3; key-escrow-by-user-choice can
exist as product surface without weakening the default.

== "A team this small cannot build this."

The scope objection. The architecture is its own answer: a domain layer
small enough to read in a sitting; one substrate at a time behind ports; a
legacy engine strangled rather than rewritten; a machine that generates
its own backlog from missed questions and runs its own night shifts. The
governance chapter is not process theater — it is how a small team rents
the discipline of a larger one. The risk that remains is focus, and the
anti-diversion law exists because the team has already paid once for
losing it.

== "Why would anyone pay for honest refusals?"

Because the alternative is confident fabrication about their own life, and
one such fabrication ends the relationship with the product. Refusal is
not the product; trust is, and refusal is trust's price. The demo bets on
this directly: the "ask it anything" moment treats an honest "I didn't
perceive that" as a feature. If users in fact prefer comfortable invention
to honest silence, then this product should not exist — and its founders
would rather learn that than build the alternative.

= The road, and the ask

== Prototype tiers

#table(
  columns: (auto, 1fr, auto),
  stroke: 0.4pt + rgb("#ddd"),
  inset: 6pt,
  table.header([*Tier*], [*Definition*], [*Horizon*]),
  [V0], [Mac-processed, generalizing, trustworthy: record → one command → ask → cited answers], [running],
  [V1], [live, on-device, attention-gated, all-day (phone rig) — the moat made wearable], [weeks–months],
  [Glasses], [the same architecture in the target form factor], [months+],
)

Everything hard about glasses — battery, heat, social acceptability — is a
harder version of a constraint the phone rig already prices, which is why
the phone rig is the right dress rehearsal. No glasses-specific engineering
exists in either repository today, deliberately (I7).

== The near road

_Now → 6 months — harden._ Make the extraction adapters real (cipher,
OCR/ASR, the camera eyes, the phone tap); run the falsification gate on
real captured weeks; close the diagnosed gaps until the battery scores
survive contact with a lived life; hold the confident-wrong zero through
the cold-capture guard. _6 → 12 months._ Wearable form factor off the
phone; closed beta; the founding team complete. _12 → 24 months._ Public
product, multi-device, first licensing conversations from an evidence
position.

== The open seat

This document is, among other things, an offer: a technical cofounder
seat — equity, not employment. The profile is deliberately open across the
six readers of the reading guide, because the work spans perception,
systems, and product; the seat owns one thing above all: making the senses
real and proving the hypothesis on real weeks, at parity with the founder.
The collaboration pattern already exists in evidence — the
refusal-calibration line with Latheesh Roy (§13.8) is how this project
works with people: a named line of attack, an instrument, and a number
that moved.

== The first 90 days

Day one is not a whiteboard: it is a repository with a constitution, 274
green tests, one xfail ledger, and a falsification gate waiting for real
weeks. The first 90 days are the strangling sequence's first organs — the
cipher adapter, OCR/ASR, the first real captured week through the crown
pipeline — and the first gate run whose verdict neither founder can
predict. That verdict is the point; this is a project that has arranged to
be told it is wrong.

== What would change our minds

If the falsification gate shows an irreducible extraction gap on questions
that matter, the hypothesis dies and the project with it. If refusal rates
at the ethics-mandated confidence floor make the product unusable, the bet
behind I5 and I6 was wrong. If a year of evidence shows the social residue
is rejected even without retention, the market is not there. Each sentence
is written down before the evidence arrives, because that is the only time
such sentences are credible.

== Conclusion

The argument compresses to four sentences. The valuable artifact of a
lived day was never the footage; it was the bound, queryable meaning, and
meaning survives translation to words while surveillance does not. A
memory that keeps only words can be structurally incapable of the harms
that have sunk every storage-first wearable, while remaining open to any
question its perception actually answered. Whether words captured at the
moment of living are enough — lossless enough, bindable enough, honest
enough — is a falsifiable hypothesis, and this architecture is the
instrument built to test it at maximum speed: append-only truth,
disposable understanding, calibrated refusal, and a measurement loop in
which every failure names its own fix. The jar on the shelf either becomes
a cited answer or an honest "I don't know" — and a system that can tell
you which, and why, is a system worth building.

#include "appendix.typ"
