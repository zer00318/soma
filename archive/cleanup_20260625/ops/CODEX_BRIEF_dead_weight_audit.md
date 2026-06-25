# CODEX BRIEF — Dead-weight audit (REPORT ONLY — delete nothing)

The founder: "there are many many dead weight elements throughout our entire project files, things that
should be discarded but are still affecting." Produce a precise, categorized, confidence-rated audit so
the Chief can discard safely. **DELETE NOTHING. Write only the report.** Honesty: if unsure, mark KEEP.

Output: `ops/DEAD_WEIGHT_AUDIT.md`.

## Scan and categorize
1. **Unreferenced Python modules** in `scripts/` (79 files) and `evaluation/` (22 files): a module is a
   candidate if NO other tracked file imports it AND it is not an entrypoint (no `__main__`, not invoked
   by a Makefile/brief/cockpit). Grep imports + string references to confirm. List path + size + the
   grep evidence.
2. **Duplicate / superseded scripts:** multiple files doing the same job (e.g. several cockpit servers,
   several eval runners, several "ask_*"). Identify the ONE that is live (referenced by the running
   cockpit / current briefs / AUTONOMOUS_CONTINUATION.md) vs the stale siblings.
3. **Stale large data** under `data/` (5.5 GB) and `archive/` (11 MB): raw clips, old capture/replay
   trees, memories NOT referenced by the current eval (`run_live_replay_battery.py`, the live44 paths)
   or the cockpit. Flag big items with their size. NOTE: raw `.mp4/.MOV` source clips under data/walks
   are eval INPUTS — mark KEEP unless clearly duplicated.
4. **Superseded ops docs/briefs:** `ops/*.md` made obsolete by `ops/PRODUCT_NORTH_STAR.md`,
   `ops/ANTI_TUNNEL_LEASH.md`, `ops/AUTONOMOUS_CONTINUATION.md`. List the obsolete ones; do NOT include
   those three or the CODEX_BRIEF_* that are still queued.
5. **"Still affecting" items (highest value):** anything imported-but-dead, name-shadowing on
   `sys.path`, duplicate module names, or stale config that the running code still loads. These are the
   ones the founder most wants gone — call them out explicitly in their own section.

## For each candidate report
`path | size | category | why it's dead | STILL AFFECTING? (does live code load it) | confidence (high/med/low) | recommendation (DISCARD / KEEP / REVIEW)`

Then a short summary: total reclaimable size, count by confidence, and the top 10 "discard first"
(high-confidence, safe) items. Add a "DO NOT TOUCH" list of load-bearing files you nearly flagged.

Do not run `git rm` or delete anything. The Chief reviews the report and discards the safe items.
