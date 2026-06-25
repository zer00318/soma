# Chief Decision - Reading First, No Kernel Rewrite

Date: 2026-06-23

## Decision

Do not build a new Context Kernel v0 now.

The immediate product is:

> a memory for everything the user can READ.

The current gate is:

> bigger text-rich capture + founder gold, about 50 reading questions, measured
> through cross-frame OCR consensus with lies near zero.

The broad context-engine blueprint remains useful as post-trust architecture,
but it is not the active build plan. The active build plan is the reading metric.

## Why

The repo already has the spine I proposed rebuilding:

- `src/trace_memory/domain/observation.py` already defines the typed
  `Observation` contract with confidence, provenance, spatial anchor, and
  refutation cue.
- `src/trace_memory/adapters/sqlite_eventlog.py` already defines an append-only
  SQLite event log.
- `src/trace_memory/adapters/legacy_ask_home.py` already cuts the compatibility
  adapter around `ask_home`.
- Unit tests already exist for domain, event log, encrypted text, egress guard,
  and legacy recall.

More importantly, the repo already has the one proven product mechanism:

- `scripts/consensus_recall.py` is the deployable cross-frame OCR consensus core.
- `ask_home.ask(..., anchor=)` is already wired to run consensus before the
  assembler for anchored reading/screen questions.
- The measured result on founder-gold reading subset moved from 47% correct /
  42% hallucination to about 60-67% correct with hallucination around 9-18%.

The actual risk is not whether a fictional observation contract can compose fake
helper outputs. The actual risk is whether real capture and OCR consensus can
earn a trustworthy number on a larger founder-gold reading set.

## What Is Frozen

Until the reading number is trusted, do not expand into:

- broad scene QA,
- spatial "what is left of me",
- duplicate object reasoning,
- usual order / commerce behavior,
- speaker identity,
- general context OS demos,
- synthetic helper-output pitch fixtures.

Those are post-trust context-engine workstreams. They do not move the active
metric today.

## Active Work Order

1. Finish the Munich text-rich capture evaluation.
2. Founder confirms/fixes gold for about 50 reading questions in
   `gold_clip.html`.
3. Run `evaluation/ocr_recall.py` against `ocr_memory.json` plus founder gold
   and per-question anchors.
4. Report:
   - correct rate,
   - wrong/hallucination rate,
   - refusal rate,
   - refusal correctness split,
   - examples of each failure class.
5. Verify the live "read what I am looking at now" loop through
   `ask_home.ask(..., anchor=)` and `consensus_recall`.
6. Only after the number is trusted, fold `consensus_recall` outputs into the
   existing `src/trace_memory` event log as `Observation`s.

## Bounded Architecture Task, Later

After the n≈50 reading gate lands, do the smallest spine-growing task:

> make `consensus_recall` emit grounded read observations into the existing
> `SqliteEventLog`.

This grows the existing spine from the proven helper. It does not invent a new
kernel, and it does not use fabricated evidence.

## Rule

If a task does not move the reading metric or integrate the proven consensus
helper into the existing spine, it is deferred.
