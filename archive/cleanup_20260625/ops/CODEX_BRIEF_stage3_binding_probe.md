# CODEX/LOCAL BRIEF — Stage-3 binding probe (the first real product measurement)

**Status: QUEUED — not yet launched.** This is the agreed first measurement toward deliverable #2
(the trustworthy number). Read `ops/PRODUCT_NORTH_STAR.md` §3 (HELPERS→INJECT→LLM) and §5
(failure modes) first. Stage 3 (BIND) is the primary unbuilt gap and its confidence governs
everything downstream, so we measure whether the spine holds BEFORE building the full thing.

## The question this probe answers
On a real captured observation log, can a first BIND pass group observations into entities and assert
relations with a **calibrated confidence**, such that **low-confidence binds correctly become
refusals** rather than confident wrong answers? One number (binding precision + abstention behaviour)
tells us if the architecture is worth building out.

## Step 0 — locate input (do this first, report what you find)
Find a captured observation log that carries, per observation, at least: a value (object/text/caption),
a timestamp, and ideally a 2D box / region. Candidates: the native app's Munich 2026-06-04 capture
(detector 29 / vision 102 / OCR), any `*_memory.json` under `/tmp` or the repo, the native capture
output dir. `/tmp/ocr_memory.json` is OCR-only (no boxes) — usable only for temporal binding, not
spatial. REPORT which log you'll use and what fields it actually has. If no box-bearing log exists,
say so — that itself is a finding (it means Stage 1 localization must come first).

## Step 1 — implement a minimal, DETERMINISTIC-first BIND pass (`scripts/inject_bind.py`)
- Input: a list of typed observations {modality, value, t, box?, conf}. Output: entities (grouped
  observations) + relations, each with a `binding_confidence` and `provenance` (which observations).
- Bind by GEOMETRY/TIME where possible: spatial overlap (IoU) × temporal proximity × detector conf →
  a binding confidence in [0,1]. Mark geometry-ambiguous binds `speculative`. NEVER collapse
  provenance. (This mirrors north-star §3 INJECT; conservative binding per §5.2.)
- Keep it dependency-light (pure Python over the log) so it runs without GPU/vision models.

## Step 2 — score honestly
- Hand-label a small gold set of true bindings on the chosen log (or have the founder do it — flag if
  human gold is needed; do NOT fabricate gold).
- Report: binding precision/recall at a confidence threshold; and the KEY honesty metric — of the
  binds below threshold, how many would (correctly) abstain vs. how many true binds are lost.
- Calibrate the threshold with a selective-prediction/conformal idea if n allows; otherwise report raw.

## HONESTY RULES
- Self-reported model confidence is worthless (the ZLORPTECH lesson) — confidence here must come from
  geometry/detector signals, not an LLM's say-so.
- A wrong bind is a confident lie; precision matters more than recall for the moat.
- If the input log lacks the fields to test spatial binding, report that limitation loudly rather than
  faking a result. n is tiny — treat any number as indicative, not proof.

## Verify
- `scripts/inject_bind.py` runs on the chosen log and prints the scored report.
- Unit test the geometry/confidence math (`evaluation/test_inject_bind.py`).
- Output: input used, what was built, the precision + abstention numbers, and an honest verdict on
  whether Stage-3 binding looks worth building out or needs a different approach.
