// ═══════════════════════════════════════════════════════════════════
// TRACE — the architecture thesis · v2.0
// Built 2026-07-21. Successor to the SOMA v1.0 exposition (retired).
// Sources of truth: the napkin (NAPKIN.md, verbatim in Appendix A),
// the tracemem repository (~/Documents/trace), the legacy v0 stack
// (~/Documents/VLM). All 40 external references verified against
// live sources on 2026-07-21 (arXiv API, doi.org, cited URLs).
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
      July 2026 · version 2.0 — supersedes the SOMA v1.0 exposition
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
media never persists and never leaves the device; only typed text may cross the
boundary. On-device perception converts the live world into coordinate-marked,
provenance-bearing text at the moment of capture; the pixels and audio that
produced it are discarded within milliseconds. A consolidation process —
always running in the background, but better nightly — binds the day's
observations into living nodes by spatial and temporal co-occurrence, derives
what was never directly observed, and discards failed derivations without ever
touching the raw record beneath them. A supplier answers unconstrained
questions by handing an ordinary local language model _just enough context_ —
three memories, not three thousand — every clause of every answer walking back
to the exact reading that justifies it, and refusing honestly where no reading
exists.

This document is the complete argument for that architecture: its first
principles (Chapters 1–2), its forty years of prior art (Chapter 3), the seven
invariants that govern implementation (Chapter 4), the pipeline from photons
to answers with one lived moment followed through every stage (Chapters 5–6),
the machine itself (Chapters 7–11), and — separated with care, because the
distinction is the difference between a claim and a hope — _what runs today,
what runs on synthetic fakes, and what is not yet built_ (Chapters 12–17).
The central hypothesis is stated as what it is: unvalidated, falsifiable, and
instrumented. Every architectural decision in this document exists to test it
faster.

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
  [Node creation & night shift — guardrails, selector, judge, pruner, remap], FAKES, [`tracemem` M4 — implemented against synthetic inputs],
  [Information supplier — cue, retrieve, pack, ground], REAL, [`tracemem` M5],
  [`.trace` container — format, keyring, sync, boundary], [#REAL / #STUB], [M6; libsodium crypto adapter stubbed],
  [Extraction cascade], [#FAKES / #STUB], [M7 — logic real, hardware adapters (OCR/ASR/eyes/tap) stubbed],
  [Crown test: shuffled synthetic week → episodes → entities → nightly patterns → cited answer → honest abstention], REAL, [`tests/test_crown.py`, passing],
  [Unit wall], REAL, [274 green · 1 xfail (the TODO ledger, each naming its spec section)],
  [First measured extraction gap], REAL, [L1-verbatim recall 0.974 (gap 0.026) over 111 real frames; ceilings audited],
  [Falsification gate on real captured weeks], NOTYET, [the REAL gate needs real captured weeks — the next milestone that matters],
  [Legacy stack (v0): live capture, hub, nightly job, phone app], REAL, [running since June 2026; being strangled, not extended],
)

*The number that matters most is one that is absent:* frames kept — zero, by
construction, in both stacks. There is no code path that writes a frame to
disk.

// ─────────────────── HOW TO READ THIS ───────────────────
#heading(numbering: none)[How to read this document]

This document is written for six different kinds of reader. Do not read it
linearly unless you want to.

- *In 10 minutes:* the Abstract, the table above, and Chapter 6 — one moment
  followed end to end.
- *ML / CV / data science:* Chapters 5, 9, and 13 — the pipeline, the
  perception economics, and the evaluation instrument.
- *Cognitive science:* Chapters 2 and 6 — the biological arguments are
  load-bearing, not decorative, and you are the reader best placed to break
  them.
- *Backend / systems:* Chapters 7, 8, and 14 — the domain model, the
  contract-first architecture, and the two-stack strangling plan.
- *Product / frontend:* Chapters 1, 6, and 11 — the problem, the lived
  example, and what answering actually feels like.
- *Investors and diligence:* the table above, then Chapters 15–17 — honest
  risks stated against ourselves, position, and the road.

#outline(depth: 2, indent: 1.2em)

// ═══════════════════ PART I ═══════════════════
#partpage[Part I · Foundations]

= Introduction and problem statement

== The problem: lives are forgotten by the people who live them

People forget most of their lives. Where the keys were left. What the doctor
actually said, as opposed to what anxiety later reconstructed. Whether the
door was locked. The name attached to a face met once at a dinner. What the
contractor promised, verbally, in the hallway. The moments that matter are
sparse, unpredictable in advance, and irretrievable by the time they are
needed. Human episodic memory was never designed for retrieval on demand; it
is a reconstructive process, optimized for gist over fidelity, and it degrades
precisely along the dimensions — exact words, exact places, exact times —
that everyday questions require [1][2].

The obvious remedy is to record everything. It fails twice, and both failures
are fundamental rather than incidental.

The first failure is social and legal. A person wearing an always-on camera
that stores video is a walking surveillance device. Every bystander is
recorded without consent; every stored hour is subject to subpoena, theft,
breach, and misuse; every intimate space the wearer enters becomes an archive.
The history of wearable cameras is the history of this failure: from the
earliest sousveillance experiments to the public rejection of camera glasses,
storage-first capture has been socially unacceptable everywhere it has been
tried at scale [10][34]. No privacy policy fixes this, because policies are
promises, and promises about stored media are exactly what nobody believes.

The second failure is functional. Raw footage is the wrong artifact. Nobody
rewatches their life; a day of video is a day long. What people actually want
from a memory is not playback but answers: to query the past the way one
queries a database, in natural language, and get back a short, true, cited
response. The valuable artifact of a lived day was never the footage — it was
the bound, queryable meaning a mind would have extracted from it.
Storage-first systems defer that extraction forever, and so never deliver it.

== The problem statement

Build a system that perceives a person's day through always-on, cheap senses;
converts everything to words the instant it happens — never keeping one frame
of video or one second of audio; consolidates those words, continuously and
best nightly, into bound understanding; and later answers arbitrary questions
from that understanding with citations, or refuses honestly.

Three phrases in that statement carry the whole design. _"The instant it
happens"_ is the privacy architecture (Chapter 12): ephemerality at the
source, not deletion after the fact. _"Bound understanding"_ is the binder
and the node layer (Chapters 5, 10): isolated observations are raw material,
not memory — the napkin is explicit that the binder's output "is not a
complete Node, it's raw material." _"Or refuses honestly"_ is the
epistemology (Chapters 11, 13): a memory that fabricates is worse than no
memory at all, so refusal is a first-class outcome and fabrication is priced
into the headline metric at the cost of a correct answer.

== The central hypothesis

Everything rests on one hypothesis: _perception can be decomposed into
channels which reconstruct lossless-enough textual context for a tractable
local reasoner to answer arbitrary retroactive questions at near-zero
hallucination._ It is unvalidated. It is falsifiable. It is instrumented
(Chapter 13), and the falsification gate that would kill or confirm it —
scoring the system against real captured weeks rather than synthetic ones —
is the project's named next milestone. Every architectural decision in this
document exists to reach that gate faster.

== What TRACE is not

TRACE is not a lifelogger: it keeps no log of life, only text extracted from
it. It is not a surveillance device: the artifact surveillance requires is
never created. It is not a retrieval-augmented chatbot: retrieval here feeds
a memory that was _built for_ retrieval, not a pile of documents that happen
to exist. It is not a model company: the language model is the last and least
special box in the machine, ordinary and swappable by design. And it is not
finished: the table on page 3 is the honest boundary between the built and
the intended.

== Contributions of this document

(1) A first-principles derivation of an input-only memory architecture from
the biology of human memory and the failure history of lifelogging. (2)
Seven locked invariants, each with rationale, enforcement, and the failure it
forecloses. (3) A complete pipeline exposition, from photons to a cited
answer, with one moment walked through every stage. (4) An honest,
mechanically-diagnosable evaluation method. (5) A candid account of the
project's two stacks — the running v0 and the greenfield rebuild — and the
strangling plan between them.

= Conceptual foundations

== The standard model: a brain never touches the world

The napkin's first drawing is not of the product; it is of every mind that
has ever existed: `[World] → Eyes/Ears → [Brain]`, with the loop closing back
into the world. The annotation beside it is the design's first principle:
_"because we can't manufacture other senses, or most of the information is
obtained through this."_ A brain never touches the world directly. It
receives two narrow, lossy, sensory streams, extracts meaning at the moment
of perception, and stores the meaning — never the stimulus. TRACE copies
exactly this: video for eyes, audio for ears, extraction at the moment of
capture, retention of meaning only. The architecture is not biomimicry for
its own sake; it is the observation that the only working memory system we
know of is input-only, and that its constraints are load-bearing.

== Episodic memory is reconstruction, not playback

Human recall does not replay footage, because there is none. Remembering is
reconstruction from consolidated traces, schema-driven and confident even
when wrong [2]. Tulving's episodic/semantic distinction [1] maps directly
onto TRACE's two stores: the time-stamped claim log is episodic — events
located in time and place, sparse and literal — while the bound node graph is
semantic: consolidated, cross-referenced, queryable. The mapping is
load-bearing, not decorative. It predicts the interface between the stores:
consolidation runs episodic→semantic, never the reverse, exactly as the
night shift reads the log and never writes it. And where human
reconstruction silently invents congruent detail, TRACE's reconstruction is
forbidden to assert anything that does not trace to a logged claim — it says
"I don't know" where a human would confabulate. The machine is honest about
reconstruction precisely because its biological original is not.

== Sleep consolidation: why the binder runs at night

The decision to concentrate deep binding in a nightly pass is likewise
borrowed from biology. Systems-consolidation research shows the mammalian
brain replays the day's hippocampal traces during slow-wave sleep, gradually
binding them into neocortical structure [3] — an architecture forced by the
same constraint TRACE faces: deep integration is expensive, and the organism
cannot afford it while also perceiving. Night is when the device is charging,
thermally unconstrained, and free to run the big model over the whole day at
leisure. The napkin's phrase is exact: node creation is _"always running in
the background, but better nightly."_ Incremental binding accelerates; the
night shift perfects. Hebb supplies the mechanism transposed to text [35]:
claims that co-occur in time and place, repeatedly, get bound into shared
structure.

== Event segmentation: why capture is gated, not uniform

Human perception does not sample the world uniformly; it carves experience
into events at boundaries of change and encodes richly at those boundaries
[4]. TRACE's capture follows the same economics: the cheap channels run
continuously precisely because they are cheap, while the expensive channel —
deep visual description by a vision-language model — fires only on attention,
dwell, or change. Uniform deep capture would be both unaffordable and
pointless: most moments do not matter, and the value of a memory is
concentrated in the few that do. The scheduler that makes this call is not
an optimization detail; it is the system's model of what deserves to be
remembered well (Chapter 9).

== Text as the retention format: the four arguments

The load-bearing decision — keep words, not media — rests on four arguments.
_Privacy:_ text is the only format whose retention can be made socially and
legally safe by construction; a sentence about a bystander is a fundamentally
different object from their stored face (the residue this does _not_
discharge is treated honestly in Chapter 12). _Sufficiency:_ the hypothesis
under test is precisely that words carry enough; language is the interlingua
in which modern machine reasoning is strongest [7], and retrieval-then-reason
over text is the best-understood recall architecture we have [12].
_Economy:_ text is thousands of times smaller than the media it replaces; a
lifetime fits on a phone. _Auditability:_ a user can read every single thing
the system knows about them, line by line, and delete none of it while
trusting all of it — an impossible offer for embeddings or media.

== The resolution of the central tension

"Remember everything" and "respect everyone" are only in tension while the
retained artifact is media. Retain extracted meaning instead and the tension
dissolves: recall quality becomes a function of extraction quality — which is
measurable and improvable — while the surveillance artifact simply never
exists. That is the whole company in two sentences.

= Prior art and position

== The memex lineage: total capture as an old dream

Bush's 1945 memex [36] founded the genre and set its sixty-year trajectory:
capture everything, organize later. The lesson of the lineage is that
"later" never comes — capture without retrieval-of-meaning is a landfill.

== MyLifeBits and SenseCam: what storage-first taught

Gemmell, Bell and Lueder proved the landfill empirically at life scale [9]:
MyLifeBits' bottleneck was never storage but structure. SenseCam [10] proved
the opposite pole — even passive photo capture measurably aids real, clinical
memory — while every deployment surfaced the social cost of visible storage.
Hoyle et al. quantified that cost from the wearer's own side: lifeloggers
themselves censor, delete, and manage bystander exposure [34]. Gurrin,
Smeaton and Doherty's survey converges on cues-and-facts over archives [37].
Together these justify TRACE's inversion: total capture, linguistic
retention.

== Ego4D: the demand curve, measured

Ego4D [11] defines the benchmark tasks TRACE's question batteries descend
from — and establishes that long-horizon egocentric retrieval is hard _even
with the video retained_. That is the honest context for every recall number
in this document: the ceiling is not 100%, even for an oracle with footage.

== Retrieval-augmented generation: the supplier's ancestry

Lewis et al. [12] define the retrieve-then-generate shape the information
supplier inherits. TRACE departs from RAG in what is retrieved from: not a
corpus that happens to exist, but a memory _constructed for_ retrieval, with
provenance and confidence as type obligations rather than metadata
conventions. Attribution — answers that cite — is promoted from evaluation
criterion [31] to construction rule; selective prediction [13] and
calibration [20] supply the formal frame for refusal; the hallucination
taxonomy of Ji et al. [32] is operationalized as the grounding gate's
checklist.

== The commercial field: an empty quadrant

Plot the field on two axes — physical-world context versus digital-only, and
zero retention versus raw-data retained — and the quadrant TRACE occupies is
empty. Camera glasses and AI pins retain media; PKM tools and assistant
platforms never touch the physical world. The two purpose-built recorders of
this generation died at the privacy wall (Chapter 16). Physical context has
always required retention; an architecture that supplies context without
retention is the first way into that quadrant.

== Knowledge graphs and open vocabulary

The node layer is a knowledge graph in the loose sense of Hogan et al. [14],
with one deliberate deviation: open vocabulary everywhere. There is no fixed
ontology of entity types or predicates; the world names itself through the
extractors' text, and structure emerges from co-occurrence, not from a
schema. The cost of that choice is weaker global consistency; the payment
comes at answer time, where evidence is quoted rather than inferred across
long relational chains.

= The seven invariants

Architecture is what remains constant while everything else iterates. TRACE
locks seven invariants. Each is stated with its rationale, its enforcement,
and the failure mode it forecloses. Code that violates an invariant does not
merge; several are enforced by construction, so violating them does not even
compile against the domain model.

== I1 — No raw persistence

_Statement._ Raw pixels and audio are discarded the instant words are
extracted from them. There is no record path, no cache, no "temporary" buffer
that survives the perceptual moment.

_Rationale._ Every stored frame is a liability with no compensating asset: it
cannot be queried directly, and it is the artifact whose existence makes the
system a surveillance device. Ephemerality at the source is the only privacy
claim that survives an adversarial audit — deletion policies, retention
windows, and encryption of stored media all reduce to promises.

_Enforcement._ In `tracemem` the law is inherited from the blueprint in its
hardest form: _raw is immutable and no update path exists; pixels never leave
the device._ Capture converts and drops in one motion. Honesty note: gold
frames used as evaluation oracles exist on the founder's development machine
only — they are the measuring instrument, not the product path, and the
phone build has never persisted a frame.

== I2 — Text-only egress

_Statement._ The only payload type permitted to cross the device boundary is
typed text carrying the identifiers of the source events it derives from.

_Rationale._ Local models may hit a quality wall (Chapter 15); the
architecture must allow routing _reasoning_ to a stronger model without ever
routing _media_ anywhere. Typing the boundary makes the safe path the only
path.

_Enforcement._ In the v0 stack this is an eleven-line guard that raises a
privacy violation for any non-text payload — short enough to audit in one
breath, which is the point. In `tracemem` the boundary lives in the
container's boundary module, with the same contract.

== I3 — Append-only truth

_Statement._ The claim log is immutable and append-only; it is the single
source of truth. Everything derived from it — episodes, entities, patterns,
every index — is a disposable, replayable projection.

_Rationale._ Consolidation is experimental and will be wrong often. If
derived structure were the truth, every experiment would risk memory loss.
With an immutable log, any projection can be discarded and rebuilt — the
napkin's discarder rule verbatim: _"the marinated content that's not useful
is discarded, NOT the raw material."_

_Enforcement._ The store exposes no update and no delete; corrections are
expressed as new claims and tombstones (Chapter 7), never as mutation.
Replays are deterministic, which the evaluation harness depends on.

== I4 — Provenance everywhere

_Statement._ Every claim, binding, derivation, citation, and egress payload
carries the identifiers of what it derives from. An unsourced assertion is a
construction error.

_Rationale._ Citations are the product; diagnosis is the method (a wrong
answer must be traceable to the claim that misled it); audit is the promise.

_Enforcement._ Constructors reject empty evidence. Provenance is not a
logging convention — it is a type obligation, in the value-object discipline
of domain-driven design [19]: invalid memory is unrepresentable.

== I5 — Calibrated confidence; refusal over fabrication

_Statement._ Every derived assertion carries a grade; the grade degrades with
derivation depth; links below the floor are refused, not hardened; at answer
time, insufficient evidence yields "I don't know."

_Rationale._ A memory's worth is its trustworthiness. One confident
fabrication — "you locked the door" when you did not — costs more trust than
a hundred honest refusals. The metric agrees: the scoring instrument
subtracts fabrications from corrects, so the optimizer and the ethics point
the same way. Modern networks are miscalibrated by default and calibration
must be measured, not assumed [20].

_Enforcement._ Grade is a domain type; _grade degrades with derivation
depth_ is one of `tracemem`'s hard laws; refusal is the default disposition
of weak evidence in the night shift's judge; abstention is a first-class
answer in the crown test.

== I6 — Unconstrained questions

_Statement._ There is no fixed question taxonomy, no menu of supported query
types. Users ask anything, natively.

_Rationale._ A constrained question surface is a product decision
masquerading as a safety decision: it hides hallucination by refusing to hear
the questions that would expose it. The honest path is open vocabulary end to
end, with calibrated refusal as the safety mechanism instead of a menu.

_Enforcement._ The query type is a bare text string by design, and the
founder's decision to keep it so is recorded.

== I7 — Nothing is built until a missed question demands it

_Statement._ Every helper, sensor, channel, and feature must be authorized by
a diagnosed failure on a real question from a real capture.

_Rationale._ Perception systems invite infinite plausible work, and intuition
about which channel matters is reliably wrong. The project's own history
supplies the cautionary tale: a 3D world renderer was built on intuition,
answered nothing, and was killed. The discovery loop — ask, miss, diagnose,
build exactly the missing channel — replaces guessing with evidence.

_Enforcement._ Governance: a build starts by naming the missed question it
answers. The miss-diagnosis log (Chapter 13) supplies those questions
mechanically. Even the two modules in `tracemem` that exceed the napkin
(a prediction spine and the falsification harness) are explicitly flagged
_beyond-napkin_ in the constitution file, awaiting a founder ruling — the
invariant applied to the repository itself.

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

This chapter is the napkin's EXECUTION line, expanded stage by stage. The
interactive walkthrough (`interactive/architecture-live.html`) renders it
live; this is its paper form. The pipeline in one line:

#align(center)[
  #text(size: 9.5pt)[`[World] → Extraction ⬛ → TEXT → Binder → Node Creation ⬛ → Supplier ⬛ → LLM`]
]

== The world: two channels, no recording

Two streams open onto every second: video for eyes, audio for ears — the
napkin's justification annotated on the drawing itself: we cannot manufacture
other senses, and most information arrives through these two. Neither stream
is a recording. Frames and samples exist transiently in memory, are read, and
die; what survives is only what was read from them.

== Extraction: the first black box

Extraction turns raw light and sound into addressed text. Inside the box,
four mechanisms:

_The blur gate._ Every frame is triaged before anything else sees it. A frame
whose content cannot be read — motion smear, defocus — is discarded
immediately: _"blurry frames discarded"_ is on the napkin. A frame that
cannot be read is never written; there is nothing to store, leak, or
subpoena.

_The spend dial._ Resolution and framerate follow the world, not a clock
(Chapter 9). A still room is sampled almost for free; a fast reach is frozen
with a burst; a settled scene earns one expensive deep look. Spend follows
salience — the signal/noise decipherer of the napkin.

_The address stamp._ Every reading is stamped with normalized coordinates and
a timestamp before meaning is attached. Nothing is remembered without its
address; x·y·second is the primary key of the whole machine, and any later
claim can be walked back to the pixel and the second that produced it.

_The macro eye and the helpers._ A vision-language model produces the macro
picture — _"a macro picture of what's happening ⇒ VLM"_ — which supplies
context: what matters in this scene and which specialists to summon. Helpers
are then called for the job: a reader for the label, a state extractor for
the jar, a listener for the voice. Each is the best available understanding
of its one slice of the world; each writes text; none knows the others exist.
No helper is architecture — remove any one and the rest carry on.

== TEXT: the only thing kept

The output of extraction is the napkin's boxed word: TEXT. Text from various
helpers, marked by coordinates, appended to an immutable log. Every line
carries where, when, which helper, and how sure. This is the entire output of
perception: text you could read aloud.

== The binder: physicality and temporal, together

The binder makes many readings into one moment. It does not understand the
kitchen; it observes that several lines share a where and a when — _"binding
the coordinates, physicality & temporal together"_ — and fuses them on that
evidence alone. Binding is evidence-driven, not semantic, which is why a
wrong binding can be reconciled later (tombstones, Chapter 7) without
touching what was read. The output is the napkin's _first thought_: raw
material that can be marinated on. The napkin's own note is the design's
humility: _"this is not a complete Node, it's raw material."_

== Node creation: the second black box

Raw material becomes living cells — _"a physical living breathing cell that
can combine with fellow nodes to derive new things — 1+1 = 4, ≠ 2."_ A node
is a persistent thing (a jar, a person, a shelf) that thickens every time the
world confirms it. Nodes combine: co-firing histories derive facts no sensor
observed. The box also carries the napkin's two governance rules: encryption
— only the person using the app can decipher (the container, Chapter 12) —
and the discarder of meta: derived content that proves useless is deleted;
the raw beneath it, never.

== The information supplier: the third black box

A question does not go to the archive; it goes to the supplier, whose
contract is the napkin's phrase _just enough context_. The supplier walks the
nodes, selects the few claims that bear on the question — three memories, not
three thousand — and packs them with their citations for the reasoner. The
supplier is the product decision; retrieval quality, not model quality, is
where answers are won.

== The LLM does what an LLM does

The last box is the least special. An ordinary local model receives the
packed context and writes the sentence. It is swappable by design; the memory
that feeds it is not. Grounding is enforced as a contract: a clause without
supporting evidence is not emitted, and the system abstains rather than
guesses.

== What flows between stages

One direction, one format. World→Extraction: transient media, dead in
milliseconds. Extraction→TEXT: addressed claims. TEXT→Binder: claims;
Binder→Nodes: bound moments (raw material). Nodes→Supplier: evidence with
provenance. Supplier→LLM: a small cited packet. LLM→user: a sentence whose
every clause walks back to a claim — or a refusal. Nothing flows backward;
nothing mutates upstream.

= One moment, end to end

The worked example is the napkin's own scene, the same one the interactive
walkthrough renders. Times are illustrative; the mechanics are the shipped
ones.

== 09:14:07, Tuesday, the kitchen

A person reaches for a jar and says something: _"we're nearly out of the
hazelnut stuff."_ Light and sound. This is the only moment that will ever
happen; everything after is about keeping it.

== The same second, inside extraction

The blur gate discards the smeared frames of the reach and keeps one legible
frame. The spend dial, which had been idling on a still kitchen, spikes for
the motion and settles into one deep look. Three helpers write four lines:

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

Same x/y region, same second: the label line, the jar-state line, and the
spoken line fuse into one bound moment — _09:14, kitchen: the jar is nearly
empty, and it was said aloud._ Raw material; not yet a node.

== The night

The moment is absorbed into cells. The JAR node thickens (seen 7 times since
12 May; ¼ full today); the PERSON node records that it was said aloud; the
PANTRY shelf carries its 41 sightings. Nodes fire together, and the night
shift derives a third thing no sensor observed: _you run out roughly every
six weeks_ — graded as derived, citing the three readings that earned it. A
second candidate — "prefers the 400 g size" — finds no rent-paying evidence
and is deleted. The raw beneath is untouched, so a better idea tomorrow gets
the same evidence.

== Weeks later: the question

_"Do we need more of that spread?"_ The supplier walks the nodes and packs
three memories: the ¼-full sighting with its date, the spoken sentence, the
derived six-week cycle. The model writes: _"Almost certainly. It was a
quarter full on 12 June, you said so yourself — and it's been about six
weeks."_ Each clause carries its citation. Ask instead "which brand does my
sister buy?" and the answer is _"I have never observed that"_ — the refusal
is the feature.

== What the example proves

That the pipeline composes: address-stamped extraction makes binding
possible; binding makes nodes possible; nodes make derivation possible;
provenance makes the final sentence auditable and the refusal principled. And
what it does not prove: that extraction is rich enough on real, messy weeks —
which is exactly what the falsification gate (Chapter 13) exists to test.

= The domain model

The vocabulary below is the live system's (`tracemem`), not its
predecessor's. The unit of memory is the _claim_.

== Claim — the atom

A claim is one line of extracted text with its address and its provenance:
what was read, where in the frame (normalized coordinates), when (timestamp),
by which helper, and how it is graded. Claims are immutable and append-only
(I3). The claim log renders back to a human-readable transcript — the memory
can be _read_, in order, line by line.

== Grade — witnessed, then downhill

Grades order trust. A claim read directly off the world (a verbatim label, a
transcribed sentence) is _witnessed_; everything built above it — bindings,
patterns, derived facts — carries a grade that _degrades with derivation
depth_, one of the repository's hard laws. The grade is not a float
decoration; it is the input to the refusal gate. Deep derivations must be
proportionally better-evidenced to be spoken at answer time.

== Episode — the bound moment

The binder's output: claims fused by co-occurrence in space and time into one
event. Episodes are projections (rebuildable from the log), carry the
evidence tuple that formed them, and are subject to _reconcile_: when later
evidence shows a binding was wrong, a tombstone retires it and a corrected
episode replaces it — correction as new information, never as mutation.

== Entity and pattern — the living cells

An entity is a node with a history: the jar, the person, the shelf — each a
list of dated confirmations. A pattern is a nightly derivation over entities:
the six-week cycle, the morning routine. Patterns are the napkin's 1+1=4 and
they are the most disposable layer in the system: the pruner deletes any that
stop paying rent, and the raw claims beneath guarantee they can be re-derived
or replaced.

== The ask contract

Answering is a typed pipeline: _cue_ (read the question), _retrieve_ (walk
entities and episodes for bearing claims), _pack_ (assemble just-enough
context, every item citable), _ground_ (emit only clauses supported by the
packet; abstain otherwise). The contract's output is either a cited answer or
an honest abstention — there is no third shape.

== Constructors, not validators

Throughout, invalid states are unrepresentable rather than checked-for:
claims without provenance, confidences outside range, bindings without
evidence do not pass construction [19][22]. The domain does not trust its
callers, including us.

= Software architecture

== The order of authority

`tracemem`'s constitution file states a precedence unusual enough to quote:
the napkin outranks the code; the code outranks the tests; the tests outrank
the campaign documents; the campaign documents outrank the specs. Prose lost
its authority in this project once already (Chapter 14); the ordering makes
sure the running system, not the latest document, is what wins arguments.

== Contract-first modules

Every source file carries a contract header: what it OWNS, its IN→OUT, its
TEST, and its spec reference. The module tree maps one-to-one onto the
napkin's boxes — `extraction/`, `text/`, `binder/`, `nodes/`, `container/`,
`supplier/`, `llm/` — so a reader can hold the drawing in one hand and the
repository in the other. Implemented logic is tested green; unimplemented
bodies raise `NotImplementedError`, and their acceptance oracles exist ahead
of them as xfail-marked tests.

== The test suite as ledger

The test run is the project's status report, by design: _green_ is the
regression wall (implemented and guaranteed); _xfail_ is the TODO ledger,
each entry naming the spec section it awaits; _FAILED_ means a real bug that
outranks all other work. As of 2026-07-21: 274 green, 1 xfail. The remaining
stubs are exactly the hardware/model adapter set — the boundary between the
thinking machinery (real) and the senses (fakes), stated plainly.

== Ports, adapters, and fakes

The v0 stack is hexagonal in the classical sense [21][22] — domain,
application, ports, adapters — and `tracemem` keeps the discipline where it
matters: every hardware and model dependency (OCR, ASR, camera eyes, the
sodium cipher, the local LLM) sits behind a port with a deterministic fake.
The crown test exercises the entire pipeline on fakes; making an adapter real
changes no domain code. Event-sourcing and disposable projections [23][24]
are the storage discipline; the strangler fig [25][40] is the migration
discipline (Chapter 14).

== The hard laws

Five laws inherited from the blueprint bind all of it: raw is immutable — no
update path exists; pixels never leave the device; one model on the GPU at a
time (a thermal and correctness constraint learned the hard way on v0);
grade degrades with derivation depth; every capture gap is witnessed — if
the senses were dark, the memory must say so rather than paper over it.

== The crown test

One test stands above the suite: a shuffled synthetic week is fed through the
whole machine — episodes form, entities accrete, nightly patterns derive, a
question is asked, a cited answer comes back, and an unanswerable question is
honestly abstained from. It passes. It is the executable form of this
document's Chapters 5–7, and it is what "the thinking machinery exists" means
when this document says it.

= The perception subsystem

== The cheap stratum and the expensive eye

Perception is two economies. The cheap stratum — detection, OCR, speech,
sound events, motion — runs always, because it can. The expensive eye — deep
VLM description — runs rarely, because it must. The architecture's job is to
spend the expensive looks exactly where the day's value is.

== Salience: the spend dial

The dial moves by itself, many times a second, on dwell, novelty, and
stability [8]: a still room earns almost nothing; an entering hand spikes the
framerate; a settled new scene earns the one deep look. This is event
segmentation (Chapter 2) turned into a scheduler, and it is why all-day
capture is affordable at all.

== The budget: no overdraft

Deep looks are governed by a token bucket [28]: a hard hourly budget,
refilled steadily, spent by salience, with no overdraft path. Attention is a
budget, not a vibe — the system can always account for why it looked hard at
one moment and not another.

== The enrichment ladder

Attention deepens in rungs — glance (a jar), read (the label), state (¾
empty, lid ajar), context (a German promo sleeve, therefore probably a German
kitchen) — and each rung emits _only the delta_: what the previous rung did
not already know. The same fact is never stored twice; storage grows with new
knowledge, not with time spent looking.

== The measured frontier

The first real number exists, and it is encouraging without being sufficient:
over 111 real captured frames, mechanically scored against frontier-model
ceilings, L1-verbatim recall is *0.974* — a 2.6% gap between what the
extraction stack reads and what the best available oracle reads. The audit
also produced a diagnosed lesson (a cropping law confirmed on meal scenes:
2/4 versus 0/4 on full frames) — the miss-diagnose-fix loop of I7 operating
on perception itself. The honest caveat: L1-verbatim is the _mechanical_
tier of the claim-match instrument, not the full score, and 111 frames are
frames, not weeks.

= Consolidation: the night shift

== The job

Read the day's claim log; bind by co-occurrence; thicken entities; derive
patterns; refuse weak links; discard failed meta; touch nothing raw. The
napkin's underlined words — _always running in the background, but better
nightly_ — set the schedule: incremental passes keep the memory current;
the night pass, on a charging and thermally free device, does the deep work.

== The anatomy

The consolidation heart (M4) is built as guarded stages: _guardrails_ (what
may never be derived, e.g. assertions that would outrun their evidence);
four _derivation kinds_ (the taxonomy of what 1+1 may legitimately make);
a _selector_ (which co-firing histories deserve the model's attention
tonight); a _judge_ (does the candidate cite enough to survive — refusal is
the default); the _night_ runner; the _pruner_ (rent collection on old
patterns); and _remap_ (re-pointing structure when reconcile retires an
episode). All of it runs today — against synthetic weeks; its inputs become
real when the extraction adapters do.

== Accelerator, not gatekeeper

Consolidation makes answers better and faster; it must never become the
condition for answering at all. The supplier can serve from episodes alone —
unconsolidated memory is slower and flatter, not absent. A memory that only
works after a good night's sleep is a demo, not an organ.

== The devil's advocate, kept in the room

Derivation is where a memory system starts lying to itself, which is why the
judge prices skepticism in: every candidate pattern must survive an explicit
attempt to refute it from the same evidence, and the system deletes its own
failed thoughts without sentiment. The napkin's discarder is not cleanup —
it is epistemic hygiene.

= Recall: grounded answering with calibrated refusal

== The loop

Cue → retrieve → pack → ground. The question is read for its entities, time
hints, and kind; the supplier walks the graph; the packet is assembled small
— just enough context, every item citable; and the grounding gate lets a
clause through only if the packet supports it. The reasoner is local [29],
ordinary, and swappable; on v0 the heuristic fallback refuses everything,
which is the correct degenerate behavior for a memory: no reasoner, no
guessing.

== Refusal as calibration

Refusal is not a failure mode; it is the mechanism that makes open questions
(I6) safe. The formal frame is selective prediction [13]: answer only above a
confidence bar, and measure the risk–coverage trade rather than assert it.
Attribution is the other half [31]: an answer's citations are checkable
objects, so a wrong answer is a diagnosable event, not a shrug.

== What answering feels like

Short, cited, and honest. _"Almost certainly — ¼ full on 12 June, you said so
aloud, and it's been six weeks."_ Or: _"I have never observed that."_ The
product bet is that users forgive a memory that sometimes says "I don't
know" and never forgive one that lies once.

// ═══════════════════ PART III ═══════════════════
#partpage[Part III · Reality]

= The privacy architecture and its threat model

== Structural, not procedural

The privacy claims rest on the two structural invariants: no raw persistence
(I1) and text-only egress (I2). What does not exist cannot be stolen,
subpoenaed, or leaked; what cannot cross the boundary cannot be exfiltrated
by a bug in a feature. This is privacy by design in Cavoukian's strict sense
[5] — embedded in architecture, not policy — and it is the strongest
available reading of GDPR's data-minimisation principle [6]: retain meaning,
not medium.

== The container

Retained text lives in the `.trace` container: a specified format anyone can
implement and only the user can open. Three layers with deliberately
asymmetric guarantees: a header readable without the key (version, device,
counts); the RAW claim log — append-only, immutable, encrypted; and the META
layer — nodes, edges, confidence — encrypted, _deletable, and re-derivable_.
Lose the meta and nothing is lost; lose the raw and everything is. Encryption
at rest is AES-256-GCM [33] on v0; `tracemem`'s cipher adapter (libsodium) is
presently stubbed — recorded as such in the ledger on page 3, because a
privacy document that overstates its own crypto status has already failed.

== Threats, walked

_Device theft:_ the container is ciphertext under the user's key; the header
leaks counts, not content. _Cloud breach:_ there is no cloud; nothing to
breach. _Subpoena:_ what can be produced is the text the user can already
read — and nothing else exists. _Malicious app update:_ the egress guard is
the choke point; media has no path out to leak. _A compromised model
vendor:_ models run locally; the reasoner sees packed text, and only on
device. The honest residual in each case is the text itself — which is why
the last section of this chapter exists.

== What architecture cannot discharge

Honesty requires the residue stated. Perceiving people into text still
touches privacy: "Anna said she's pregnant" is sensitive with no pixel
involved. The bystander literature on wearable cameras [34] transfers in
part to any wearable perception. Product-level obligations therefore remain:
disclosure norms for wearers, redaction policies for bystander speech,
retention and export controls in the user's hands, and the wearer's own
social contract. The architecture makes the worst artifact impossible; it
does not make the remaining ones weightless. This section exists so that no
investor, customer, or regulator can say the project hid the residue behind
the moat.

= The evaluation instrument

== The philosophy

Two failure modes destroy memory products: fabrication, and silent
information loss at capture time. The instrument is built to expose both,
mechanically, so that every miss becomes a work item rather than a debate.

== Scoring answers

The v0 instrument scores a question battery with fabrication priced in: a
made-up answer costs what a correct one earns, so the headline number cannot
be inflated by confident guessing. Every miss is mechanically diagnosed as
(A) never captured or (B) captured but unused — the (A)/(B) split is the
steering wheel: (A) misses buy sensors; (B) misses buy binder and reasoner
work. The v0 baseline on its 92-second proving clip was measured at RAS 40.0
with 27.3% hallucination, 8 of 9 misses diagnosed (B) — the honest starting
line that motivated the greenfield rebuild's discipline, recorded here
because a thesis that hides its worst number teaches its readers to distrust
its best one.

== Ceilings: knowing the maximum before claiming the score

`tracemem`'s harness pins _ceilings_: frontier-model readings of the same
frames, cached and versioned, so every extraction score is a fraction of a
known maximum rather than a free-floating number. Current audited state: 111
ceiling frames carrying 4,674 claims; against their mechanical tier the
extraction stack reads 97.4% (Chapter 9). Ceilings are re-pinned when the
frontier moves; the score is always _relative to the best reader we can
rent_, which is the only honest definition of "lossless-enough."

== Rehearsal, and the verdict format

Before real weeks, synthetic ones: a generated week with known ground truth
is pushed through the entire machine, and the report grades strata separately
— verbatim recall, factual recall, emergent (derived) recall — with a
one-word verdict. The first full rehearsal returned its verdict honestly:
`FIX_UPSTREAM` — verbatim 1.0, factual 0.5, emergent 0.0, with the gap
diagnosed to specific upstream stages and two invalid questions flagged. The
system grading itself harshly, in machine-readable form, is the culture the
instrument exists to enforce.

== The falsification gate

The gate that matters is still ahead, and this document refuses to blur
that: capture real weeks on the real device, run the full battery, diagnose
every miss. The hypothesis (Chapter 1) lives or dies there. Everything in
Part II exists to make reaching that gate a matter of adapters, not
architecture.

= Two stacks, one product: an honest history

== v0: the stack that runs

The reader doing diligence will find two repositories, and deserves the story
before the surprise. v0 has run continuously since June 2026: live capture
feeding an always-on hub, a nightly consolidation job at 03:30, an encrypted
store, an iPhone capture app, and an evaluation battery. It produced the
first disciplined binder (36 entities, 58 bindings, 144 weak links refused on
the proving clip), the first honest scores, and most of the hard laws — one
model on the GPU, capture goes dark silently if crowded, the embedding
endpoint that had to be replaced. It also accumulated what every v0
accumulates: prose documents that drifted from the code until, on
2026-07-17, the founder deleted every one of them and declared that the
present tense lives only in code, tests, and running processes. That
deletion is why this document cites ledgers instead of promises.

== The greenfield: the napkin, rebuilt

Two days later the architecture was redrawn by hand — the napkin — and
`tracemem` was scaffolded from it: specs first, contract headers in every
file, fakes behind every port, the crown test as the spine, xfail as the
TODO ledger. The napkin was transcribed verbatim into the repository as its
constitution, outranking everything including the specs. v0's lessons are
inherited as laws rather than as code.

== The strangling sequence

The migration follows the strangler fig [25][40]: v0 keeps running as the
capture organ and the measuring baseline while `tracemem`'s adapters come
real in dependency order — cipher, OCR/ASR, the camera eyes, the phone tap.
Each adapter that lands moves one organ from the old body to the new; the
crown test and the ceilings verify equivalence at each step. v0 is
decommissioned by explicit founder decision when the falsification gate runs
green on the new stack — not by drift, and not before.

== What v0 knows that a rewrite would forget

The operational scar tissue is the inheritance: that capture dies silently
when the GPU is shared, and must be watched by liveness checks; that
embeddings needed a different engine than the reasoner; that phone deploys
stall in reproducible ways; that a store must be snapshotted and
shadow-served to measure it without killing capture. None of this is in any
paper; all of it is in the laws and runbooks the new stack starts with.

= Honest risks

_The hypothesis may be false._ Text may lose something questions need at a
rate the enrichment ladder cannot close. This is the existential risk; it is
measurable (Chapter 13), the gap today is 2.6% on frames, and the number on
real weeks is unknown. If the gap on lived weeks proves irreducible, the
architecture does not survive by pivoting to stored media — the project
fails honestly instead.

_The senses are not real yet._ The thinking machinery runs; the hardware
adapters are stubs. The risk is not that adapters are hard — v0 proves each
exists — but that their _quality_ on device, on battery, all day, is below
what the ceilings assume. The battery and thermal budget on glasses-class
hardware is unmeasured and is called out as such.

_A single founder built this._ Bus factor one, and the seat this document
exists to fill is empty (Chapter 17). The mitigations are the ones in
evidence: specs with contracts, a constitution file, tests as ledger — the
repository is built to be joined.

_Two stacks is a tax._ Every week both run is a week of split attention. The
strangling plan bounds it, but the tax is real and admitted.

_Local models may plateau._ If on-device reasoning stalls, I2 permits
routing _text_ to a stronger model — a privacy-preserving escape hatch that
is nonetheless a product compromise and is treated as one.

_The social residue._ Chapter 12's residue section is a risk, not a
footnote: a wearer whose glasses transcribe speech is a social object the
world has already rejected once. The bet is that text-only, cited,
user-auditable memory is on the acceptable side of the line the recorders
died on. That bet can lose.

= Position and moat

== The empty quadrant

Physical-world context with zero retention: no shipping product occupies it.
The recorders that tried the adjacent quadrant died there — Humane's pin
shut down with its assets sold to HP for \$116M (February 2025); the
always-on recorder category is a graveyard because storage-first capture
meets the wall of Chapter 1. The digital-only assistants — however
personalized — cannot see the room. The quadrant is empty because physical
context has always required retention. TRACE's architecture is the first way
in without it.

== Why now

Three curves cross. On-device AI crossed the capability threshold — billions
of phones now run local models, and sub-second on-device vision is
commodity. AI wearables ship in volume — roughly seven million camera
glasses in 2025 alone — proving demand for the form factor while their
retention architecture proves the objection. And the EU AI Act's biometric
provisions (in force since February 2025) turn "structurally non-retaining"
from a philosophy into a procurement criterion, on the continent where this
company is being built.

== Why incumbents don't simply build it

Their business models monetize retained data and engagement; their privacy
stacks deliberately stop at the digital life. A zero-retention physical
layer contradicts the data economics that fund them. If the capability
matters to them, they license it or acquire it — both outcomes require TRACE
to exist first.

== The moat, precisely

Not the model (commodity, by design), not the app. The moat is the posture —
input-only, provable, GDPR-native — which storage-first competitors cannot
copy without abandoning their foundation; the evidence corpus — every
deployed week compounds the question batteries and diagnosis logs that tune
extraction; and the licensing position: a specified container and a
text-only context layer that any device maker can adopt, on the precedent of
Arm and Dolby — companies that own a layer, not a box.

= The road, and the ask

== The road

_Now → 6 months — harden._ Make the extraction adapters real (cipher, OCR,
ASR, eyes); run the falsification gate on real captured weeks; close the
diagnosed gaps until the battery scores survive contact with a lived life.
_6 → 12 months — the EXIST phase._ Wearable form factor off the phone;
closed beta; the founding team complete. _12 → 24 months — ship._ Public
product, multi-device, first licensing conversations from an evidence
position.

== The open seat

This document is, among other things, an offer: a technical cofounder seat,
equity not employment. The profile is deliberately open across the six
readers of the reading guide — the work spans perception, systems, and
product — but the seat owns one thing above all: making the senses real and
proving the hypothesis on real weeks, with the founder, at parity.

== The first 90 days

Day one is not a whiteboard: it is a repository with a constitution, 274
green tests, one xfail ledger, and a falsification gate waiting for real
weeks. The first 90 days are the strangling sequence's first organs — cipher
adapter, OCR/ASR, the first real captured week through the crown pipeline —
and the first gate run whose verdict neither of us can predict. That verdict
is the point. This is a project that has arranged to be told it is wrong.

== What would change our minds

If the falsification gate shows an irreducible extraction gap on questions
that matter, the hypothesis dies and the project with it — honestly. If
refusal rates make the product unusable at the confidence floor the ethics
require, the bet on I5/I6 was wrong. If a year of evidence shows the social
residue is rejected even without retention, the market is not there. Each of
these is written down _before_ the evidence arrives, which is the only time
such sentences can be written credibly.

// ═══════════════════ APPENDICES ═══════════════════

#heading(numbering: none)[Appendix A — The napkin, verbatim]

Handwritten by the founder; photographed 2026-07-18; transcribed into the
repository as its constitution. On any conflict it outranks code, tests,
campaign documents, and specs — in that order below it. Nothing in it may be
"improved" in place; a change to the architecture is a founder decision,
recorded on the board.

#block(inset: (left: 1em))[
#raw("## Standard Model

    [World] --Senses--> Eyes / Ears / Organs --> [Brain]
       ^______________________________________________|
    (because we can't manufacture other senses
     or most of the information is obtained through this)

## EXECUTION

    [World] -> Video (Eyes), Audio (Ears)
        -> [Extraction Black Box]
        -> Coordinates + time stamps
        -> Blurry frames discarded · Signal–Noise decipherer + Context
        -> A macro picture of what's happening => VLM
        -> A specialized eye or helper for various tasks are called   (Helper)
        -> Best understanding possible of the world
        -> [TEXT]

    Text from various helpers marked by coordinates
        -> [Binder] => binding the coordinates, physicality & temporal, together
        -> First thought or raw material that can be marinated on
           Note: This is not a complete Node, it's raw material
        -> [Node Creation Black Box]
             · Encryption, i.e. people using our app can decipher
             · A physical living breathing cell that can combine with
               fellow nodes to derive new things — 1+1 = 4, ≠ 2
             · Always running in the background but better nightly
             · Discarder of meta, i.e. the marinated content that's not
               useful is discarded, NOT the raw material

    [Information Supplier Black Box]
        -> Just Enough Context for local LLM
        -> LLM does what LLM does", block: true)
]

#v(1em)
The box→code map (subordinate to the drawing):

#table(
  columns: (1fr, 1fr),
  stroke: 0.4pt + rgb("#ddd"),
  inset: 6pt,
  table.header([*Napkin box*], [*Code*]),
  [Extraction Black Box], [`src/tracemem/extraction/`],
  [TEXT (raw, immutable, coordinate-marked)], [`src/tracemem/text/`],
  [Binder], [`src/tracemem/binder/`],
  [Node Creation Black Box], [`src/tracemem/nodes/` · `src/tracemem/container/`],
  [Information Supplier Black Box], [`src/tracemem/supplier/`],
  [LLM does what LLM does], [`src/tracemem/llm/`],
)

#heading(numbering: none)[Appendix B — Glossary]

#table(
  columns: (auto, 1fr),
  stroke: none,
  inset: (y: 4pt),
  [*claim*], [one line of extracted text with address, provenance, and grade — the atom of memory],
  [*grade*], [ordered trust level; _witnessed_ at the top, degrading with derivation depth],
  [*episode*], [claims bound by shared place and second — the napkin's "first thought," raw material],
  [*entity*], [a persistent node with a dated history (the jar, the shelf, the person)],
  [*pattern*], [a nightly derivation over entities — the napkin's 1+1=4; deletable, re-derivable],
  [*tombstone*], [the record that retires a wrong binding without mutating the log],
  [*ceiling*], [a frontier-model reading of the same frame, pinned and cached — the denominator of every extraction score],
  [*crown test*], [the end-to-end test: synthetic week → episodes → entities → patterns → cited answer → honest abstention],
  [*supplier*], [the third black box: cue → retrieve → pack → ground; three memories, not three thousand],
  [*`.trace`*], [the container: readable header · encrypted immutable RAW · encrypted re-derivable META],
  [*(A)/(B) miss*], [diagnosis of a failed answer: never captured (A) versus captured but unused (B)],
  [*strangler fig*], [the migration pattern: v0 keeps running while `tracemem`'s adapters replace its organs],
)

#heading(numbering: none)[Bibliography]

All numbered sources were verified against live externals on 2026-07-21:
arXiv identifiers checked title-and-authors against the arXiv API; DOIs
resolved through `doi.org` to their publishers; cited URLs confirmed
reachable. Books are cited from their canonical editions.

#set par(justify: false)
#set text(size: 9pt)

+ E. Tulving, "Episodic and Semantic Memory," in _Organization of Memory_, Academic Press, 1972; and _Elements of Episodic Memory_, Oxford University Press, 1983.
+ F. C. Bartlett, _Remembering: A Study in Experimental and Social Psychology_, Cambridge University Press, 1932.
+ J. G. Klinzing, N. Niethard, J. Born, "Mechanisms of systems memory consolidation during sleep," _Nature Neuroscience_ 22, 1598–1610, 2019. doi:10.1038/s41593-019-0467-3
+ J. M. Zacks, N. K. Speer, K. M. Swallow, T. S. Braver, J. R. Reynolds, "Event perception: a mind–brain perspective," _Psychological Bulletin_ 133(2), 273–293, 2007.
+ A. Cavoukian, _Privacy by Design: The 7 Foundational Principles_, Information & Privacy Commissioner of Ontario, 2009.
+ Regulation (EU) 2016/679 (GDPR), Article 5(1)(c) — data minimisation. #link("https://gdpr-info.eu/art-5-gdpr/")[gdpr-info.eu/art-5-gdpr]
+ T. Brown et al., "Language Models are Few-Shot Learners," _NeurIPS_, 2020. arXiv:2005.14165
+ L. Itti, C. Koch, "Computational modelling of visual attention," _Nature Reviews Neuroscience_ 2, 194–203, 2001.
+ J. Gemmell, G. Bell, R. Lueder, "MyLifeBits: a personal database for everything," _Communications of the ACM_ 49(1), 88–95, 2006. doi:10.1145/1107458.1107460
+ S. Hodges et al., "SenseCam: A Retrospective Memory Aid," _Proc. UbiComp_, 177–193, 2006. doi:10.1007/11853565_11
+ K. Grauman et al., "Ego4D: Around the World in 3,000 Hours of Egocentric Video," _Proc. CVPR_, 2022. arXiv:2110.07058
+ P. Lewis et al., "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks," _NeurIPS_, 2020. arXiv:2005.11401
+ A. Kamath, R. Jia, P. Liang, "Selective Question Answering under Domain Shift," _Proc. ACL_, 2020. arXiv:2006.09462
+ A. Hogan et al., "Knowledge Graphs," _ACM Computing Surveys_ 54(4), 1–37, 2021. arXiv:2003.02320
+ Apple Inc., ARKit documentation: ARWorldMap, world tracking and relocalization. #link("https://developer.apple.com/documentation/arkit")[developer.apple.com/documentation/arkit]
+ D. L. Hall, J. Llinas, "An introduction to multisensor data fusion," _Proceedings of the IEEE_ 85(1), 6–23, 1997.
+ Gemma Team, Google DeepMind, "Gemma 3 Technical Report," 2025. arXiv:2503.19786
+ Qwen Team, Alibaba Group, "Qwen2.5-VL Technical Report," 2025. arXiv:2502.13923
+ E. Evans, _Domain-Driven Design: Tackling Complexity in the Heart of Software_, Addison-Wesley, 2003.
+ C. Guo, G. Pleiss, Y. Sun, K. Q. Weinberger, "On Calibration of Modern Neural Networks," _Proc. ICML_, 2017. arXiv:1706.04599
+ A. Cockburn, "Hexagonal Architecture (Ports and Adapters)," 2005. #link("https://alistair.cockburn.us/hexagonal-architecture")[alistair.cockburn.us]
+ R. C. Martin, _Clean Architecture_, Prentice Hall, 2017.
+ M. Fowler, "Event Sourcing," 2005. #link("https://martinfowler.com/eaaDev/EventSourcing.html")[martinfowler.com]
+ M. Fowler, "CQRS," 2011. #link("https://martinfowler.com/bliki/CQRS.html")[martinfowler.com]
+ M. Fowler, "Strangler Fig Application," 2004 (updated 2024). #link("https://martinfowler.com/bliki/StranglerFigApplication.html")[martinfowler.com]
+ J. Redmon, S. Divvala, R. Girshick, A. Farhadi, "You Only Look Once: Unified, Real-Time Object Detection," _Proc. CVPR_, 2016. arXiv:1506.02640; Ultralytics YOLO documentation, docs.ultralytics.com.
+ P. K. A. Vasu, H. Pouransari, F. Faghri, R. Vemulapalli, O. Tuzel, "MobileCLIP: Fast Image-Text Models through Multi-Modal Reinforced Training," _Proc. CVPR_, 2024. arXiv:2311.17049
+ A. S. Tanenbaum, D. J. Wetherall, _Computer Networks_, 5th ed., Pearson, 2011 — §5.4, token-bucket traffic shaping.
+ Ollama — local large-model runtime. #link("https://ollama.com")[ollama.com]
+ A. Radford, J. W. Kim, T. Xu, G. Brockman, C. McLeavey, I. Sutskever, "Robust Speech Recognition via Large-Scale Weak Supervision" (Whisper), _Proc. ICML_, 2023. arXiv:2212.04356
+ B. Bohnet et al., "Attributed Question Answering: Evaluation and Modeling for Attributed Large Language Models," 2022. arXiv:2212.08037
+ Z. Ji et al., "Survey of Hallucination in Natural Language Generation," _ACM Computing Surveys_ 55(12), 1–38, 2023. arXiv:2202.03629
+ M. Dworkin, _NIST SP 800-38D: Galois/Counter Mode (GCM) and GMAC_, NIST, 2007. doi:10.6028/NIST.SP.800-38D
+ R. Hoyle, R. Templeman, S. Armes, D. Anthony, D. Crandall, A. Kapadia, "Privacy behaviors of lifeloggers using wearable cameras," _Proc. UbiComp_, 571–582, 2014. doi:10.1145/2632048.2632079
+ D. O. Hebb, _The Organization of Behavior_, Wiley, 1949.
+ V. Bush, "As We May Think," _The Atlantic Monthly_, July 1945.
+ C. Gurrin, A. F. Smeaton, A. R. Doherty, "LifeLogging: Personal Big Data," _Foundations and Trends in Information Retrieval_ 8(1), 1–125, 2014.
+ Apple Machine Learning Research, "FastVLM: Efficient Vision Encoding for Vision Language Models," _Proc. CVPR_, 2025. arXiv:2412.13303
+ J. F. Gemmeke et al., "Audio Set: An ontology and human-labeled dataset for audio events," _Proc. ICASSP_, 2017.
+ S. Newman, _Monolith to Microservices_, O'Reilly, 2019.

#v(2em)
#line(length: 100%, stroke: 0.4pt + rgb("#ddd"))
#v(0.6em)
#text(size: 8.5pt, fill: inkgray)[
  Typeset in Typst 0.15 · Libertinus Serif, fonts embedded · references
  verified against live sources 2026-07-21 · companion: the interactive
  walkthrough at `interactive/architecture-live.html` · TRACE, July 2026.
]
