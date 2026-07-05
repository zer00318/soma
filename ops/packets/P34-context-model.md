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
- **Question generality is the metric**: the WWH battery — for each captured
  scene, the questions that COULD be asked (what playing / what queued /
  where was X relative to Y / which site / what changed) — founder-authored,
  measured like the canonical battery. No claiming "fixed" per-question.

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

## Status
- KEPT from tonight (general, not bandage): daemon now captures with
  geometry + window attribution + region banding + active-tab URL — structure
  preserved AT SOURCE, whatever brain consumes it.
- STOPPED: extending the screen-activity owner with url/region special-casing
  (owner #16). The existing owner stays as a stopgap until Stage A beats it.
