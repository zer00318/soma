# P04 — Ask-brain over-refusal fixes (three known defects, one owner each)
wave: W0 · tag: judgment · executor: Opus effort=high or Fable · depends: none

## Context (self-contained)
Three measured defects in `src/trace_memory/brain/agent.py` (the ask brain), found on the
REAL live store `data/trace_store.sqlite3` with gemma3:12b-it-qat via ollama:
1. **where-is over-refusal** (found 2026-07-03): "where is the laptop" → "I don't know"
   @0.15 refused, despite the evidence chain containing "laptop | silver, closed, on top
   of a gray surface" and tracker rows with positions. Repro:
   `TraceMemoryAgent(TraceMemoryStore("data/trace_store.sqlite3")).answer("where is the laptop")`.
   Location questions likely lack an owner path that trusts high-score raw location
   evidence when no authored current-location row exists.
2. **channel-question over-refusal** (queued from M7): "what did anyone say" style
   questions refuse even when ASR rows exist.
3. **compound questions** (queued from M7): "how many mugs and how many drills" answers
   only the first clause.

## Laws that bind you
L2 above all: the grounding gate stays BEFORE every fastpath; fixing over-refusal must not
create confident-wrong. L4: one owner per question type — extend the existing owner, never
add a parallel answering path. L5: no content lexicons.

## Do
For each defect: write the failing-question regression test FIRST (against a fixture
store), then the smallest structural fix in the existing owner, then verify on the REAL
store. Where-is: when the grounding gate passes and raw location-bearing evidence ranks
top, the reasoner prompt/owner must be allowed to answer from raw sightings with hedged
confidence (last-seen semantics: "last seen on the table at 08:12"), refusing only when
evidence is genuinely absent.

## Done when
`pytest -q` green · canonical battery holds CORRECT-ON-PRESENT ≥96.7 and CONFIDENT-WRONG=0 ·
real-store spot check: "where is the laptop" answers with last-seen + hedge; "how many
unicorns" still refuses; "what did anyone say about <topic present in ASR>" answers;
compound count question answers both clauses or honestly says it answers one at a time.
INDEX flipped with the three before/after answers pasted.
