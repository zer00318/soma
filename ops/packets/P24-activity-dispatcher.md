# P24 — Activity dispatcher v1 (context → specialist routing)
wave: W2 · tag: judgment · executor: Fable or Opus effort=high · depends: P02 + at least one of P20–P23 merged

## Context (self-contained)
The founder's specialist thesis: generalist VLM/LLMs are mediocre wherever life has formal
structure; the VLM's real job is recognizing WHICH structure is present and dispatching a
specialist (the way OCR is the text specialist; Stockfish-not-LLM was the founder's chess
example). This packet builds the ROUTER, not the specialists: a cheap always-on context
classification ("cooking", "at desk/coding", "in a store", "reading", "meeting") that
(a) becomes observations itself (activity context is memory!) and (b) triggers registered
dispatched-helpers per P02's registry `dispatch_hint`.

## Laws that bind you
L4, L5, L7: routing rules live in the REGISTRY (data), not in code branches; adding a new
specialist must require zero spine changes. L1 for anything phone-side.

## Do
1. Context classifier: fuse cheap existing signals — scene class (VLM caption head or a
   small classifier), motion state (P22), place, focused Mac app (P20), sound (P23) —
   into a rolling `activity_context` observation (`helper_id=activity_context`,
   emitted on change, with confidence).
2. Dispatch: when context matches a registry entry's dispatch_hint, invoke that helper on
   the current data (phone-side helpers get the live crop/frame path; Mac-side get the
   current window). Ship with exactly ONE toy dispatched specialist to prove the seam
   end-to-end (suggestion: a barcode/QR reader via Vision on the phone — tiny, real).
3. Budget: dispatched work obeys the look-again loop's budget (P13) when both exist;
   standalone throttle otherwise.

## Done when
Real capture shows correct activity_context trail ("coding" while coding with P20 on;
"walking" outside); the toy specialist fires only in its context and its observation
answers through /ask; adding a second dummy specialist = registry entry only (proven in a
test, no spine diff); pytest + battery hold. INDEX flipped.
