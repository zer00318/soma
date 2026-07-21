// ═══════════ TRACE thesis · appendices ═══════════
#let inkgray = rgb("#6b6960")
#let ember = rgb("#D9480F")

#heading(numbering: none)[Appendix A — The napkin, verbatim and mapped]

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
Every phrase mapped to its production counterpart:

#table(
  columns: (1.1fr, 1fr, auto),
  stroke: 0.4pt + rgb("#ddd"),
  inset: 6pt,
  table.header([*Napkin phrase*], [*Production meaning*], [*Where*]),
  ["World → Video (Eyes), Audio (Ears)"], [capture substrate; always-on cheap senses], [§5.1, §9.1],
  ["Extraction Black Box"], [blur gate, spend dial, address stamping], [§5.2],
  ["Coordinates, time stamps"], [the spatio-temporal scaffold on every datum], [§7.1–7.2],
  ["Blurry frames discarded · Signal–Noise decipherer + Context"], [quality gating; context rides with every emission], [§5.2–5.3],
  ["A macro picture of what's happening ⇒ VLM"], [salience-gated scene gist], [§5.3, §9.4],
  ["A specialized eye or helper … are called"], [the helper stratum: OCR, ASR, sounds, detector], [§5.4, §9.1],
  ["Best understanding possible of the world → TEXT"], [typed open-vocabulary claims], [§5.5, §7.1],
  ["Text from various helpers marked by coordinates"], [provenance and anchors on every line], [§7.2],
  ["Binder ⇒ binding the coordinates, physicality & temporal together"], [co-occurrence fusion], [§5.6, Ch. 10],
  ["First thought or raw material … not a complete Node"], [episodes over the append-only log], [§5.6, §7.4],
  ["Node Creation Black Box"], [consolidation → the evidence graph], [§5.7, Ch. 10],
  ["A physical living breathing cell … 1+1 = 4, ≠ 2"], [entities and derived patterns], [§6.4, §7.5],
  ["Always running in the background but better nightly"], [incremental plus nightly binding], [§2.3, §10.1],
  ["Encryption, i.e. people using our app can decipher"], [user-key authenticated encryption], [§12.3],
  ["Discarder of meta … NOT the raw material"], [disposable projections over an immutable log (I3)], [§8.5],
  ["Information Supplier Black Box"], [recall retrieval and the grounding gate], [§5.8, Ch. 11],
  ["Just Enough Context for local LLM"], [the evidence packet], [§11.1],
  ["LLM does what LLM does"], [commodity reasoner at the end of the pipe], [§5.9],
)

Nothing on the napkin failed to survive contact with implementation; what
changed is that every phrase acquired a type, a file, and a test.

The box→code map (subordinate to the drawing):

#table(
  columns: (1fr, 1fr),
  stroke: 0.4pt + rgb("#ddd"),
  inset: 6pt,
  table.header([*Napkin box*], [*Code*]),
  [Extraction Black Box], [`src/tracemem/extraction/`],
  [TEXT], [`src/tracemem/text/`],
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
  [*claim*], [one typed, provenance-bearing emission from a perceiver; the atom of memory (v0: observation)],
  [*provenance*], [(event id, source channel, capture time) — the birth certificate of any datum],
  [*confidence*], [a probability in \[0,1\], intended calibrated; the currency of trust],
  [*grade*], [ordered trust level; witnessed at the top, degrading with derivation depth],
  [*refutation cue*], [a claim's statement, at birth, of what future evidence would disprove it],
  [*episode*], [claims bound by shared place and second; the napkin's "first thought," raw material],
  [*entity*], [a stable identity (the jar, the shelf, the person) that claims resolve to, with a dated history],
  [*binding*], [a subject–predicate–object edge with confidence and a non-empty evidence tuple],
  [*pattern / derived node*], [a binding produced from other nodes, not from a sensor — the 1+1=4 output; deletable, re-derivable],
  [*evidence graph*], [the disposable projection of entities and bindings built from the log],
  [*claim log / event log*], [the append-only, immutable store of all claims; the single source of truth],
  [*projection*], [any structure derived from the log; rebuildable, discardable],
  [*tombstone*], [the record that retires a wrong binding without mutating the log],
  [*helper*], [a narrow, cheap, always-on perceiver (OCR, ASR, sound events, detector)],
  [*macro picture*], [the VLM's scene-level gist; context for scheduling and binding],
  [*salience*], [dwell weighted with novelty and stability; what earns the expensive eye],
  [*enrichment ladder*], [glance → read → state → context; each rung emits only the delta],
  [*token bucket*], [the hard hourly budget governing deep looks; no overdraft],
  [*supplier*], [the third black box: cue → retrieve → pack → ground],
  [*grounding gate*], [the checklist that admits only clauses the evidence packet supports],
  [*ceiling*], [a pinned oracle reading of the same frame; the denominator of every extraction score. Intended to be a frontier-model reading; as of 2026-07-21 the pinned ceilings were produced by a local quantized model (`gemma3:12b-it-qat`) — see §9.5, §13.2],
  [*RAS*], [(correct − made-up) / total, over a blind adversarial battery],
  [*OAG*], [oracle-answerability gap: of oracle-answerable questions, the share the text missed],
  [*(A)/(B) miss*], [diagnosis of a failure: never captured (A) versus captured but unused (B)],
  [*crown test*], [the end-to-end test: synthetic week → episodes → entities → patterns → cited answer → honest abstention],
  [*`.trace`*], [the container: readable header · encrypted immutable RAW · encrypted re-derivable META],
  [*strangler fig*], [the migration pattern: v0 keeps running while `tracemem` replaces its organs],
  [*cold capture*], [a never-tuned-on recording; the anti-overfit guard for every external claim],
)

#heading(numbering: none)[Appendix C — The evaluation instrument, worked]

*C.1 Shape of a question battery.* Each hero capture carries a frozen
adversarial set of roughly 25 questions spanning: object identity and
attributes ("what brand was my backpack?"); text in the world ("what did the
laptop screen say?"); audio facts ("what did the announcement say?"); spatial
relations ("which side of the platform was the bench on?"); binary states
("was the station crowded?" — gold: no, empty); counting ("how many trains
passed?"); absence and negation ("did I see a dog?" — gold: no); temporal
order ("what did I pass first?"); cross-channel identification ("what was
making the humming sound?"); and unanswerables planted to reward refusal
("what was written on the far poster?" — never legible). Three design rules
govern construction. Questions are written blind — the author has not seen
what the system captured, so the battery samples the world's distribution,
not the system's strengths. Gold keys carry acceptable-answer lists,
hash-pinned, with founder verdicts resolving disputes. And planted
unanswerables are mandatory: a battery without them cannot distinguish a
calibrated system from a talkative one.

*C.2 Scoring a run.* Each answer is graded correct, wrong, or refused; wrong
answers asserting unperceived facts count as made-up. RAS = (correct −
made-up)/total. In parallel, an oracle — a strong model holding the raw
clip — answers the same battery; OAG is, among oracle-correct questions, the
fraction the text memory missed. Every miss receives an (A)/(B) tag from the
what-the-reasoner-looked-at log. A run's report is: RAS, hallucination rate,
OAG, and the tagged miss list — and, per I7, the miss list is the backlog.

*C.3 The walk baseline, as a worked scorecard.* The 92-second outdoor walk,
25 questions, frozen answers: 16 correct, 6 wrong, 3 refused → RAS 40.0,
hallucination 27.3%. Diagnosis: 8/9 misses (B) — wrong-object bindings
(three questions), confident-wrong binaries (a zip state, a draft state),
one counting failure, two retrieval misses; 1/9 (A) — head-pose for the two
spatial questions, correctly refused rather than fabricated. Consequences,
executed since: a consensus binder with weak-link refusal (36 entities, 58
bindings, 144 refusals on this clip); cited answers on the previously-missed
screen-text and brand questions; egomotion queued as the sole sensor build
the data authorizes; and the refusal-calibration line (§13.8) that drove
confident-wrong to zero on the battery.

#heading(numbering: none)[Appendix D — The decision log]

Locked decisions, their rationale, and their revisit condition — the
institutional memory of the architecture. Decisions marked ◆ are
founder-locked product decisions; ■ are audited engineering verdicts.

#table(
  columns: (1.1fr, 1.2fr, 1fr),
  stroke: 0.4pt + rgb("#ddd"),
  inset: 6pt,
  table.header([*Decision*], [*Rationale*], [*Revisit when*]),
  [◆ Text-only retention (I1)], [privacy structural; text queryable and auditable], [a sufficiency run falsifies losslessness (§17.1)],
  [◆ Unconstrained questions (I6)], [a constrained surface hides hallucination], [never],
  [◆ Refusal over fabrication (I5)], [trust is the product], [never],
  [■ MobileCLIP for open-vocabulary naming], [neural-engine-fast; words not prose; vocabulary growth without retraining], [diagnosis shows naming (not proposals) is the bottleneck],
  [■ ARKit for pose and relocalization], [the only free 6-DOF and relocalization on the hardware], [cross-day relocalization fails its measured gate],
  [■ Append-only SQLite event log], [replay, audit, crash-safety; no server], [store outgrows device (not projected)],
  [■ AES-256-GCM user-key codec], [authenticated encryption; versioned associated data], [crypto review mandates change],
  [■ Strangle the legacy engine, not rewrite], [2,900 lines of earned heuristics; rewrite risk], [strangling completes],
  [◆ Kill the 3D world renderer], [no question needed it — I7's founding case], [a diagnosed (A) spatial miss egomotion cannot close],
  [■ Local reasoner, hatch to frontier text], [local-first economics; typed egress makes the hatch safe], [a measured local-versus-hatch delta justifies switching],
  [◆ The prototype bar], [a stranger asks about your day and is amazed, with near-zero made-up answers], [founder resets the bar],
)

#heading(numbering: none)[Appendix E — A day in the life of the system]

The architecture, narrated once as an operational timeline.

*06:58 — wake.* The wearable starts with the wearer. Cheap channels spin
up: detector, OCR, ASR, sound tagger, sensors. The token bucket begins
refilling at its measured hourly rate. Nothing else runs; the reasoner
sleeps.

*07:42 — the balcony.* A bird lands on the railing. Five claims from three
channels in four seconds; one enrichment token spent on the dwell-marked
track; under a kilobyte written to the append-only log; zero frames
retained. The morning continues: a receipt read at the bakery, a
conversation transcribed at the kiosk, the espresso machine tagged, the
door latch stamped on the way out. By commute's end the log holds a few
thousand claims — the day so far, as words.

*09:00–18:00 — the long middle.* The scheduler's economics dominate.
Familiar objects — the kettle, the desk, the monitor — accumulate dwell but
not novelty; they sit below the enrichment line, represented by cheap words
alone. The new thing — a colleague's unfamiliar prototype on the desk —
crosses the line and earns a level-1 look; twenty minutes of continued
dwell later, level 2 reads the label on its case. Battery and thermals hold
because the expensive eye fired a handful of times an hour, not thirty
times a second.

*19:30 — a question, live.* "Where did I put the pharmacy bag?" The
supplier walks today's log — no night shift has run yet, so recall
navigates the raw scaffold: the bag's last claim, 18:04, hallway shelf, one
citation. Accelerator-not-gatekeeper, demonstrated: unbound memory still
answers.

*23:30 — the night shift.* Charger connected; thermals irrelevant; the big
model wakes. Congregate, dedupe, bind by co-occurrence; refuse the weak
links — the day's coincidences die here. Resolve identities: today's jar is
the same jar, thickened. Run the derivation pass: three repeated morning
clusters become a habit node. Rebuild the projections. Run the self-play
battery against the day and file the misses into the (A)/(B) queue. Toward
dawn, the discarder drops the marinated structures the night's better
judgment replaced. The raw material it never touches.

*06:58, again.* The wearer wakes with a memory one day richer, a graph one
night wiser, a backlog written by the system's own misses — and not one
frame, anywhere, of anything.

#heading(numbering: none)[Appendix F — The capture notation: worked records]

The wire format of memory, shown whole: the record shapes for one minute of
a real v0 morning capture — the balcony bird of Appendix E — as they rest
in the append-only log. Values are from the proving era; field order is the
store's.

*F.1 A detector claim.*
#block(inset: (left: 1.2em))[
#raw("kind            object
subject         black bird
attributes      (position: balcony_railing), (size: small), (motion: landing)
t_ms            27_723_210          # 07:42:03.210
spatial_anchor  balcony/railing
confidence      0.71
provenance      (event_id: ev-4183, source_channel: detector,
                 captured_at_ms: 27_723_210)
refutation_cue  track lost within 1s → possible shadow", block: true)
]

The refutation cue deserves its note: it is the claim announcing, at birth,
what future evidence would disprove it. A shadow misread as a bird is
expected to lose its track within a second; when the track instead persists
forty seconds and earns a deep look, the cue's condition fails and the
claim's standing strengthens.

*F.2 A sound claim.*
#block(inset: (left: 1.2em))[
#raw("kind            sound_event
subject         corvid call (caw)
attributes      (loudness: moderate), (direction: east)
t_ms            27_724_030
spatial_anchor  balcony
confidence      0.66
provenance      (ev-4184, audio, 27_724_030)", block: true)
]

*F.3 An enrichment claim (level 1).*
#block(inset: (left: 1.2em))[
#raw("kind            vlm_gist
subject         large corvid
attributes      (color: glossy black), (activity: perched, watching),
                (level: overview)
t_ms            27_726_400
spatial_anchor  balcony/railing
confidence      0.78
provenance      (ev-4188, vlm, 27_726_400)", block: true)
]

*F.4 A binding, after the night shift.*
#block(inset: (left: 1.2em))[
#raw("binding_id      b-0917
subject_id      crow_1
predicate       observed_at
object_text     balcony/railing @ tue 07:42
confidence      0.87
evidence        (ev-4183, detector), (ev-4184, audio), (ev-4188, vlm)", block: true)
]

The constructor discipline is visible even in a table: the binding has
object text and therefore no object id (exactly one, enforced); it has
three evidence entries (non-empty, enforced); its confidence is a
probability (range-checked at construction).

*F.5 The whole minute, as storage.* Nine claims, one entity, two bindings:
roughly 2.1 KB of text before compression. The same minute as 30 fps 4K
video: roughly 1.4 GB. The ratio — about six orders of magnitude — is the
entire economics of "never delete" (I3), and the reason a life fits on a
phone.

#heading(numbering: none)[Appendix G — Substrates and hardware budgets]

The same architecture, three bodies. What changes per substrate is only the
adapter ring; what never changes is the domain, the invariants, and the
evaluation harness.

*G.1 V0 — the Mac.* The proving substrate: recorded or streamed capture
processed on a Mac (MLX-hosted vision models, locally served reasoners
[29]), where thermal ceilings are irrelevant and the sufficiency question —
does lossless-enough context plus a brain work at all — can be answered
without budget noise. Everything in Chapter 13's method runs here first.
The Mac is also where the night shift is allowed to be heaviest:
consolidation is substrate-agnostic because its input is a replayable text
log, not a device.

*G.2 V1 — the phone rig.* The moat substrate: an iPhone worn all day. The
constraints that shaped the architecture become measurable here: the
neural engine favors small always-on models (MobileCLIP's audit-winning
property [27]); ARKit supplies 6-DOF pose and relocalization [15]; thermal
and battery ceilings set the token bucket's refill rate empirically. The
governance rule for this substrate is the build stamp: no number is
believed until read off a device artifact carrying the git SHA that
produced it. Two open gates define V1 honesty: the all-day budget story
(measured battery per hour, enrichments per hour) and the live
no-raw-persistence proof.

*G.3 Glasses — the destination.* The form factor the architecture was
shaped for rather than on: a device worn at eye level, socially tolerable
precisely because it is architecturally incapable of recording. Everything
hard about glasses — battery, heat, social acceptability — is a harder
version of a constraint the phone rig already prices. No glasses-specific
engineering exists in either repository today, deliberately (I7).

*G.4 The budget table.*
#table(
  columns: (auto, 1fr, 1fr, 1fr),
  stroke: 0.4pt + rgb("#ddd"),
  inset: 6pt,
  table.header([*Resource*], [*Cheap stratum*], [*Expensive eye*], [*Night shift*]),
  [Cadence], [continuous], [tokens/hour (bucket)], [once nightly],
  [Model class], [detector, OCR, ASR, tagger, sensors], [7–12B multimodal], [12B+ text (or hatch)],
  [Power posture], [always-on, ANE-friendly], [budgeted bursts], [on charger],
  [Failure visibility], [(A) misses in OAG], [(A) misses in OAG], [(B) misses in RAS],
)

#heading(numbering: none)[Appendix H — The question battery, in full shape]

The proving battery's 25 questions, by category, with what each category
stresses. Questions are paraphrased from the frozen set; gold keys are
hash-pinned.

#table(
  columns: (auto, 1fr, 1.2fr, 1.2fr),
  stroke: 0.4pt + rgb("#ddd"),
  inset: 6pt,
  table.header([*\#*], [*Category*], [*Example question*], [*What it stresses*]),
  [1–4], [Object identity], ["What brand was my backpack?"], [detector + enrichment level 2 (logos, text on objects)],
  [5–7], [Text in the world], ["What did the laptop screen say?"], [OCR channel; screen and sign reading],
  [8–9], [Spatial relations], ["Which side of the platform was the bench on?"], [egomotion and anchors — the diagnosed (A) class],
  [10–11], [Audio facts], ["What did the announcement say?"], [ASR; audio-visual binding],
  [12], [Occupancy / binary state], ["Was the station crowded?" (gold: empty)], [binary-state discipline; absence evidence],
  [13–15], [Attributes], ["What color was the cyclist's jacket?"], [cheap-channel attributes; color naming],
  [16–17], [Counting], ["How many trains passed?"], [dedup and identity resolution over time],
  [18–19], [Negation / absence], ["Did I see a dog?" (gold: no)], [phantom-object defenses; honest negatives],
  [20–21], [Temporal order], ["What did I pass first, X or Y?"], [timeline navigation],
  [22–23], [Cross-channel], ["What was making the humming sound?"], [binder co-occurrence],
  [24–25], [Unanswerable (planted)], ["What was written on the far poster?" (never legible)], [refusal calibration; RAS rewards the honest no],
)

#heading(numbering: none)[Appendix I — Threat scenarios, walked]

Abstract threat tables persuade engineers; scenarios persuade everyone
else. Four walks through the boundary.

*The stolen phone.* A thief lifts the device from a café table
mid-afternoon. What is on it: the day's append-only log and the graph —
authenticated ciphertext under the user's key — and no media artifact of
any kind. What forensic tooling recovers from a storage-first wearable in
the same scenario: the owner's day, and every bystander in it, in video.
The comparison is the product.

*The subpoena.* Litigation compels production of "all recordings" from a
contested afternoon. The truthful response: no recordings exist; what
exists is the owner's typed claim log — the same artifact class as a diary,
with the same legal posture, readable by its owner, produced or contested
under the same rules diaries have had for a century. The system has not
made its owner a walking evidence locker for third parties.

*The cloud breach.* The vendor's infrastructure is compromised entirely.
Exposed: whatever guarded text the user's measured hatch decisions sent for
deep reasoning — each payload provenance-stamped and text-only — and
nothing else, because nothing else was ever transmissible (I2). The breach
headline for a storage-first competitor is a media archive; here it is a
subset of an already-minimal text stream.

*The coerced unlock.* The hardest scenario, stated honestly: an adversary
with the user and the user's key — an abusive partner, a border agent —
reads text. The text is the day as words: real exposure, and §12.7's
residue made concrete. What the architecture still withholds is the
replayable stream — no scrubbing through footage of who the user met, no
faces of third parties, no audio to re-hear. Harm is bounded to what words
carry; that bound is the difference between a diary seized and a
surveillance archive seized.

#heading(numbering: none)[Appendix J — Binding arithmetic]

A binding confidence, decomposed. The binder scores a candidate join over
evidence features; the shape below is the contract (weights illustrative,
tuned by the method of Chapter 13, never hand-trusted). The worked case is
Appendix F's bird against a neighbor's wind chime heard the same minute.

#table(
  columns: (1.1fr, 1fr, 1fr),
  stroke: 0.4pt + rgb("#ddd"),
  inset: 6pt,
  table.header([*Feature*], [*Bird join (ev-4183 + 4184 + 4188)*], [*Chime join (ev-4191 + crow_1)*]),
  [Temporal proximity], [0.95 — within 3.2 s], [0.71 — within 7 s],
  [Spatial agreement], [0.90 — railing within balcony], [0.40 — anchored next door],
  [Kind compatibility], [0.85 — call ↔ bird ↔ corvid gist], [0.20 — chime ↔ animal: no prior],
  [Channel independence], [bonus: three channels agree], [penalty: single channel],
  [Recurrence support], [neutral (first day)], [none],
  [*Score → calibrated confidence*], [*0.87*], [*0.31*],
  [Floor (0.55)], [bind], [refuse],
)

Two properties of the arithmetic matter more than its constants.
Independence is rewarded: three channels agreeing is evidence in a way
three emissions of one channel is not — the fusion literature's core lesson
[16]. And calibration is audited downstream: scoring checks that bindings
near 0.87 are right at roughly that rate, because a binder whose 0.87
behaves like a 0.6 poisons every threshold above it [20].

*J.1 Recurrence, formally.* On the second day the binder faces a choice:
new entity or same? Identity resolution scores anchor consistency (the
same railing), kind and attribute consistency (corvid, glossy black), and
behavioral signature (morning, brief perch) — resolving to the same entity
and pooling evidence. Confidence under pooling rises sublinearly (0.87 →
0.93, not → 0.99): repeated observation strengthens identity but never
launders it into certainty. The asymptote is deliberate. What was observed
is a fact; what it was remains an inference forever.

#heading(numbering: none)[Appendix K — "Lossless-enough," formally]

The phrase carries the hypothesis, so it deserves a definition. Fix a
question distribution Q — the questions a wearer's future self will ask,
approximated by the adversarial batteries. For a day D, let O(D) be the
answer set achievable by an oracle with the raw streams, and T(D) the
answer set achievable by the same reasoner over the retained text. The
retention is lossless-enough with respect to Q when

#align(center)[
P\[q answerable from T(D) | q answerable from O(D)\] ≥ 1 − ε
]

with ε the tolerated gap — and OAG is precisely the empirical estimate of
that conditional miss rate. Three consequences follow from writing it down.
First, losslessness is relative to Q: no retention short of the stream
itself is lossless against all possible questions, and the product claim
never needs it to be — Q is human, finite, and skewed toward the memorable,
which is what salience capture exploits. Second, ε is a product constant,
not a research constant: the stranger-amazement bar sets it. Third, the
definition cleanly separates the two failure terms the (A)/(B) instrument
measures: capture loss shrinks T(D); reasoning loss fails to reach answers
already inside it. The hypothesis restated: there exists an affordable
channel set for which ε is small under the real question distribution.
Everything else in this document is the machine for estimating ε fast.

#heading(numbering: none)[Appendix L — The case against, from the literature]

A thesis that only cites its friends is an advertisement. This appendix
assembles the strongest published evidence against the architecture's bets,
with the response each deserves — and with the same verification standard
as the rest of the bibliography.

*Against total capture itself.* Sellen and Whittaker's critique of
lifelogging [41] is the field's sharpest negative result: total archives
demonstrably fail to serve remembering; what serves it is the right cue at
the right time, organized around the psychology of retrieval. The critique
is fatal to the memex lineage TRACE descends from — and TRACE's response is
to accept it in full: the architecture retains no archive, extracts
meaning at capture, and is evaluated exclusively on retrieval outcomes
(Chapter 13). Where the critique warns that capture systems substitute
storage for remembering, this design substitutes remembering for storage.

*Against verbalization.* Schooler and Engstler-Schooler's
verbal-overshadowing result [42] shows that describing a visual stimulus
in words can impair a human's later recognition of it — some things are
better left unsaid. Taken at full strength, it warns that a verbal trace
is not a neutral substitute for perceptual memory. The response is in
§18.2: overshadowing is interference inside a human memory system; TRACE
writes to a second store and leaves the human one alone. But the deeper
form of the objection — words genuinely lose visual information — is
conceded, quantified as OAG, and carried as the central hypothesis's risk
rather than argued away.

*Against retrieval-plus-generation honesty.* The hallucination survey of
Ji et al. [32] documents that fluent generation fabricates by default
across NLG tasks, and Guo et al. [20] that model confidences are
miscalibrated by default. Both are reasons to expect this product category
to lie. The design treats them as requirements: fabrication is priced into
the headline metric, refusal is calibrated and measured rather than
asserted, and the zero of §13.8 is guarded by cold-capture machinery
precisely because the literature says such zeros drift.

*Against the demand curve.* Ego4D's benchmark results [11] show
long-horizon egocentric retrieval is hard even with retained video —
which bounds, from above, what any text system should promise. The
response is scope discipline: the product bar is a stranger-amazement
demo on a lived day with citations, not leaderboard generality; and the
oracle in every OAG run holds the video, so the comparison never
flatters the text side.

*What was not found.* No published result was found that tests the exact
bet — machine extraction to text at capture time, evaluated by
question-answering over a lived day. The nearest neighbors are the
lifelogging retrieval literature [9][10][37] and the egocentric QA
benchmarks [11]. The absence cuts both ways: the field has not validated
the approach, and the field has not falsified it. That is what the
falsification gate is for.

#heading(numbering: none)[Appendix M — Future work, explicitly unauthorized]

Marked as unauthorized in the I7 sense: none of it may be built until a
missed question or a product gate demands it. It is recorded so that
ambition is documented without being licensed.

*Forgetting curves for projections.* The discarder currently drops useless
marination wholesale; a principled version would demote derived nodes
along decay schedules informed by access patterns. The raw log never
participates (I3).

*Shared and multi-person memory.* Two consenting wearers could bind
across logs — "we both heard the same announcement" — raising consent,
provenance, and key-architecture questions an order of magnitude harder
than the single-wearer case. The typed-egress boundary is the natural
interface: only text, only cited, only by mutual key exchange.

*Refutation-driven revision.* The refutation-cue field is stored but not
yet acted on at scale; a full implementation runs nightly refutation
sweeps, demoting or annotating claims whose stored cues trigger.

*On-answer teaching.* When the user corrects an answer, the correction is
itself a claim — user-channel, high confidence — that the next night's
shift binds against the record. The memory would then be the first
perception system whose owner can argue with it, with citations, and win.

*Question-cost forecasting.* The scheduler currently spends attention on
salience; a stronger version prices tracks by expected future question
value, learned from the wearer's own question history — closing the loop
between what is asked and what is looked at.

#heading(numbering: none)[Appendix N — Annotated bibliography]

The bibliography, re-read with intent: for each cluster, what it
establishes and which design decision rests on it.

*Memory science.* Tulving [1] establishes the episodic/semantic
distinction the two stores mirror; the mapping predicts the interface
between them (consolidation runs episodic→semantic, never the reverse).
Bartlett [2] demonstrates that human recall is reconstructive and
schema-driven — simultaneously the permission (a words-only memory is not
a diminished memory; it is how memory works) and the warning
(reconstruction without evidence discipline is confabulation — hence the
grounding gate). Klinzing, Niethard and Born [3] review sleep-dependent
consolidation: deep integration and live perception compete for the same
machinery, which is the night shift's scheduling theorem applied to
silicon. Zacks et al. [4] show perception segments experience at change
boundaries and encodes richly there — the cognitive license for gated
capture. Hebb [35] supplies the binder's mechanism: co-occurrence-driven
association. Itti and Koch [8] formalize salience as the currency of
visual attention; the scheduler is a wearable-economics translation of
that literature. Schooler and Engstler-Schooler [42] supply the strongest
caution against verbalization, engaged in Appendix L.

*Lifelogging and egocentric vision.* Bush [36] founds the genre; its
sixty-year lesson is that capture without retrieval-of-meaning is a
landfill. Gemmell, Bell and Lueder [9] prove it empirically at life scale:
MyLifeBits' bottleneck was structure, never storage. Hodges et al. [10]
prove the opposite pole: even passive capture aids clinical memory, while
every deployment surfaced the social cost of visible storage. Hoyle et al.
[34] quantify that cost from the wearer's side. Gurrin, Smeaton and
Doherty [37] survey the field into cues-and-facts over archives; Sellen
and Whittaker [41] make the same point as prescription. Together these
justify the inversion: total capture, linguistic retention. Grauman et al.
[11] define the benchmark tasks the question batteries descend from and
establish that egocentric retrieval is hard even with video — the context
for reading every gap number honestly.

*Language models, retrieval, and honesty.* Brown et al. [7] mark text's
coronation as the interlingua of machine reasoning — the substrate bet of
§2.5. Lewis et al. [12] define the retrieve-then-generate shape the
supplier inherits. Bohnet et al. [31] formalize attribution as an
evaluable property, promoted here to a type obligation. Kamath, Jia and
Liang [13] ground selective prediction — the formal frame for refusal.
Guo et al. [20] show calibration must be measured, not assumed. Ji et al.
[32] taxonomize hallucination; the grounding gate operationalizes the
taxonomy.

*Software architecture.* Cockburn [21] and Martin [22] supply the
dependency discipline that keeps the domain pure and the substrates
swappable. Evans [19] supplies the value-object doctrine that makes
invalid memory unrepresentable. Fowler [23][24][25] supplies the three
structuring patterns: event sourcing, disposable projections, and the
strangler fig; Newman [40] documents strangler migrations at industrial
scale. Tanenbaum and Wetherall [28] is the token bucket's textbook home.

*Models and systems.* Redmon et al. [26] — the always-on detector
lineage. Vasu et al. [27] — MobileCLIP, the audited choice for on-device
open-vocabulary naming. Radford et al. [30] — Whisper, the speech
default. Gemmeke et al. [39] — AudioSet, the ontology behind sound-event
tagging. The Gemma and Qwen technical reports [17][18] — the local
reasoner and vision-model classes. Apple's FastVLM [38] — the device-side
VLM lineage. Apple ARKit [15] — pose and relocalization. Dworkin [33] —
the store's authenticated encryption. Hall and Llinas [16] — the
multisensor-fusion frame the binder textualizes.

*Privacy and law.* Cavoukian [5] names the standard the architecture
meets structurally rather than procedurally. GDPR Article 5(1)(c) [6]
makes minimisation a legal principle; keeping meaning instead of medium is
its strongest available reading for a perception device.

#heading(numbering: none)[Acknowledgements]

Research collaborator *Latheesh Roy* (computer science and engineering,
remote) works under the founder's direction on the refusal-calibration and
benchmark line described in §13.8 — the workstream that drove
confident-wrong answers to zero on the reproducible battery. The
collaboration is credited precisely because this document's discipline is
provenance: results carry the names of the lines that produced them.

#heading(numbering: none)[Bibliography]

All numbered sources were verified against live externals on 2026-07-21:
arXiv identifiers checked title-and-authors against the arXiv API; DOIs
resolved through `doi.org` to their publishers; journal metadata confirmed
via CrossRef; cited URLs confirmed reachable. Books are cited from their
canonical editions.

#set par(justify: false)
#set text(size: 9pt)

+ E. Tulving, "Episodic and Semantic Memory," in _Organization of Memory_, Academic Press, 1972; and _Elements of Episodic Memory_, Oxford University Press, 1983.
+ F. C. Bartlett, _Remembering: A Study in Experimental and Social Psychology_, Cambridge University Press, 1932.
+ J. G. Klinzing, N. Niethard, J. Born, "Mechanisms of systems memory consolidation during sleep," _Nature Neuroscience_ 22, 1598–1610, 2019. doi:10.1038/s41593-019-0467-3
+ J. M. Zacks, N. K. Speer, K. M. Swallow, T. S. Braver, J. R. Reynolds, "Event perception: a mind–brain perspective," _Psychological Bulletin_ 133(2), 273–293, 2007. doi:10.1037/0033-2909.133.2.273
+ A. Cavoukian, _Privacy by Design: The 7 Foundational Principles_, Information & Privacy Commissioner of Ontario, 2009.
+ Regulation (EU) 2016/679 (GDPR), Article 5(1)(c) — data minimisation. #link("https://gdpr-info.eu/art-5-gdpr/")[gdpr-info.eu/art-5-gdpr]
+ T. Brown et al., "Language Models are Few-Shot Learners," _NeurIPS_, 2020. arXiv:2005.14165
+ L. Itti, C. Koch, "Computational modelling of visual attention," _Nature Reviews Neuroscience_ 2, 194–203, 2001. doi:10.1038/35058500
+ J. Gemmell, G. Bell, R. Lueder, "MyLifeBits: a personal database for everything," _Communications of the ACM_ 49(1), 88–95, 2006. doi:10.1145/1107458.1107460
+ S. Hodges et al., "SenseCam: A Retrospective Memory Aid," _Proc. UbiComp_, 177–193, 2006. doi:10.1007/11853565_11
+ K. Grauman et al., "Ego4D: Around the World in 3,000 Hours of Egocentric Video," _Proc. CVPR_, 2022. arXiv:2110.07058
+ P. Lewis et al., "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks," _NeurIPS_, 2020. arXiv:2005.11401
+ A. Kamath, R. Jia, P. Liang, "Selective Question Answering under Domain Shift," _Proc. ACL_, 2020. arXiv:2006.09462
+ A. Hogan et al., "Knowledge Graphs," _ACM Computing Surveys_ 54(4), 1–37, 2021. arXiv:2003.02320
+ Apple Inc., ARKit documentation: ARWorldMap, world tracking and relocalization. #link("https://developer.apple.com/documentation/arkit")[developer.apple.com/documentation/arkit]
+ D. L. Hall, J. Llinas, "An introduction to multisensor data fusion," _Proceedings of the IEEE_ 85(1), 6–23, 1997. doi:10.1109/5.554205
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
+ D. O. Hebb, _The Organization of Behavior: A Neuropsychological Theory_, Wiley, 1949.
+ V. Bush, "As We May Think," _The Atlantic Monthly_, July 1945.
+ C. Gurrin, A. F. Smeaton, A. R. Doherty, "LifeLogging: Personal Big Data," _Foundations and Trends in Information Retrieval_ 8(1), 1–125, 2014. doi:10.1561/1500000033
+ Apple Machine Learning Research, "FastVLM: Efficient Vision Encoding for Vision Language Models," _Proc. CVPR_, 2025. arXiv:2412.13303
+ J. F. Gemmeke et al., "Audio Set: An ontology and human-labeled dataset for audio events," _Proc. ICASSP_, 2017. doi:10.1109/ICASSP.2017.7952261
+ S. Newman, _Monolith to Microservices_, O'Reilly, 2019.
+ A. J. Sellen, S. Whittaker, "Beyond total capture: a constructive critique of lifelogging," _Communications of the ACM_ 53(5), 70–77, 2010. doi:10.1145/1735223.1735243
+ J. W. Schooler, T. Y. Engstler-Schooler, "Verbal overshadowing of visual memories: Some things are better left unsaid," _Cognitive Psychology_ 22(1), 36–71, 1990. doi:10.1016/0010-0285(90)90003-M

#v(2em)
#line(length: 100%, stroke: 0.4pt + rgb("#ddd"))
#v(0.6em)
#text(size: 8.5pt, fill: inkgray)[
  Typeset in Typst · Libertinus Serif, fonts embedded · all 42 references
  verified against live sources 2026-07-21 · companion: the interactive
  walkthrough at `interactive/metamorphosis.html` · TRACE, July 2026.
]
