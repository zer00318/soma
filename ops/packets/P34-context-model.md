# P34 — THE CONTEXT MODEL: from text bags to relations (founder step-back 2026-07-05)

## The indictment (founder, on his own phone, verbatim spirit)
"Rao Bahadur (2026) is not in YouTube — it's a separate website." The brain
answered from a text bag and could not know a tab title from the playing
video. "Maximum context doesn't mean just text information like OCR, it's
about the play too — relations between objects, the WWH, more questions that
could be asked. Distinguish what's being played, what's in the sidebar, WHERE
in the sidebar, is it in the queue." Verdict: the brain is DUMB right now.

## The structural diagnosis (why every fix so far was a bandage)
Measured in the repo tonight: **10 hand-rolled owners + 15 compiled regexes**
in `brain/agent.py`. Each owner exists because:
1. **Capture flattens.** Every helper renders what it KNEW into prose and
   throws the structure away (the screen daemon knew every span's bbox and
   window; it shipped "text: a ; b ; c"). The phone channel is actually AHEAD:
   tracks, anchors, boxes exist — but ingest stores them as prose rows too.
2. **The store has no relations.** memory_links exists but carries only
   binder internals. "X is inside Y", "X is adjacent to Y", "X is the active
   surface" are not representable, so they are not queryable.
3. **Retrieval returns soup.** Similarity + token overlap over prose hands
   the reasoner an unordered pile; gemma at 12 words then echoes the question
   noun. Every new question family fails until a human writes owner #16.
   That is the definition of not-general.

## The direction (structure end-to-end; owners become gates, not answerers)
- **Observation contract v2 — container paths.** Every observation carries
  WHERE-IN-THE-WORLD-OF-SOURCES it sits: digital `display/window/tab(url)/
  region` (landed in the daemon tonight), physical `world/room/anchor/track`
  (P10 already provides this). Same shape, both pillars.
- **Relations become rows/links at ingest**: containment (span IN tab, object
  ON anchor), adjacency (same-frame co-visibility already exists in P12),
  activity state (front window, active tab = "the play").
- **Context slices at ask time.** Retrieval stops returning row soup and
  returns a SCENE TREE for the relevant time window: container hierarchy with
  content inside it, rendered structurally for the reasoner. One honest
  reasoner over a good slice replaces most bespoke owners; the deterministic
  layer shrinks to what must stay deterministic: honesty gates (S1, counts,
  refusal calibration) — the moat.
- **Question generality is the metric — FRAME-ANCHORED, not authored**
  (founder correction 2026-07-06: an authored battery biases — the author
  knows the day, the builder tunes to the question style; "a futile exercise").
  Protocol: during capture, one arbitrary frame per window (5min) SURVIVES
  deletion into evaluation/frame_gold/ (+ sidecar: t/app/url/windows;
  privacy-blocklist moments never sampled; local-only, gitignored, purgeable).
  At eval time questions are DERIVED FROM THE FRAME (what does the frame show
  playing/queued/where) blind to the store, posed to the brain about that
  moment, scored frame-vs-answer. The frame arbitrates BOTH capture loss and
  brain loss. Phone twin later via the W0 raw-buffer recorder (owner-consented
  sampling).

## Measured path (v1 lesson: never legislate ahead of measurement)
- **Stage A (pilot, screen channel):** ingest writes container/relation links
  from the daemon's structured provenance; a context-slice renderer replaces
  row soup for screen questions; WWH-screen battery authored (founder blind);
  measure slice+gemma vs tonight's owner on the SAME questions.
- **Stage B:** same slice renderer over the physical channel (anchors/tracks
  — the structure already exists; only the renderer is new).
- **Stage C:** retire every owner the slice beats; keep the honesty gates.
- Merge gate per stage: canonical battery CONFIDENT-WRONG=0 + WWH battery
  strictly improving + pytest green.

## Calibration (ordered by the founder, agreed)
The 75% claim was inflated — it counted pipeline plumbing as product. The
product promise is relational recall, and that is at v0.1. Honest stocktake:
substrate + honesty gates + capture pipeline + device loop ≈ real and strong;
context model (the differentiator) barely exists; 3-day proof not started.
**≈55%, and the remaining 45 is the hard part** — not single digits, but a
long way, exactly as stated.

## BRAINSTORM OUTCOME 2026-07-05 late (founder + chief, live chat — supersedes the
## "Direction" sketch above where they differ)

1. **One epistemology, two adapters.** Digital and physical capture are the SAME act:
   observing a world through a semantic layer the platform maintains (Mac: AX tree —
   the OS knows "tab" vs "heading"; phone: ARKit scene graph — planes classified
   table/floor/wall). Adapters differ; output is identical: entities, containers,
   states, relations, events. The worlds' real difference becomes a GRADE, not an
   architecture: P10's world>session>track>none generalizes — AX fact = authoritative,
   OCR span = inferred, ARKit plane = inferred-with-confidence. Answer badges inherit
   from the grades of the facts they walked.
2. **The re-derivability rule** (founder's "last-moment squeeze", decided): extract
   before frame deletion everything that CANNOT be re-derived (facts: AX, boxes,
   planes, OCR, fingerprints, opportunistic VLM crops — 24/7 under a thermal/battery
   governor, P11 law); maintain STATES live (playing/focused/held/moving — deltas,
   P12-live's true job); author THEORIES at sleep (relations, episodes, identity —
   derived, reconsiderable).
3. **Specialists are LEARNED, not written** (the "something huge" candidate): at sleep
   time a local model induces per-container extraction grammars from repeated
   structured snapshots ("in youtube.com, AXHeading under AXWebArea = playing title;
   right AXList = queue") — stored as DATA in the registry, jar-rule validated
   (consistent across days before trusted), reconsiderable, corrected by P42 review
   cards (the owner is a helper too). "Earned by starvation" becomes the SCHEDULER
   (WWH battery + per-container Leash pick the next container to induce). Hand-written
   specialists = flagship overrides only.
4. **Fable-window plan (2 days left, founder-informed):** Day 1 = AX adapter + graded
   schema + context-slice renderer + WWH battery harness (+ P-STAB verdict fold-in).
   Day 2 = bounded induction SPIKE on real browser captures (feasibility verdict, kill
   or keep) + ARKit scene-semantics adapter started + P22 to fleet. Everything lands
   as contracts + tests + batteries that outlive the model on shift.
5. **Status: HYPOTHESIS until measured** (founder call): P34 graduates to spec law
   only when the WWH battery shows slices beating the owner pile.

## Status
- KEPT from tonight (general, not bandage): daemon now captures with
  geometry + window attribution + region banding + active-tab URL — structure
  preserved AT SOURCE, whatever brain consumes it.
- STOPPED: extending the screen-activity owner with url/region special-casing
  (owner #16). The existing owner stays as a stopgap until Stage A beats it.
