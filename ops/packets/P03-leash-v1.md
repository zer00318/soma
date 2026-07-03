# P03 — The Leash v1 (objective anti-tunnel evaluator)
wave: W0 · tag: guided · executor: Opus effort=medium · depends: P02 (helper_id tagging)

## Context (self-contained)
The founder mandated an objective evaluator that catches stagnation — the team once spent
weeks inside one perception channel while others starved. The canonical battery
(`evaluation/run_canonical_battery.py`, fixture worlds, 4 numbers, exit-1 on any
confident-wrong) stays THE merge gate. The Leash is the separate PROGRESS instrument:
it scores real captured days per life domain and makes starvation visible.

## Laws that bind you
L2 (report honestly), L6. The Leash reads the store; it never mutates it.

## Do
1. `evaluation/leash.py`: given a store + a day (or --all), compute per-domain rows:
   domains = physical-objects · text-in-world · speech/people · digital/screen ·
   motion/place · sound-events · temporal. For each: observation volume (rows by
   helper_id class), answerability sample (N fixed template questions per domain against
   the real store via the REAL agent), refusal honesty on absent-probes, and a coverage
   verdict STARVED|THIN|FED (thresholds in one constants block, documented).
2. Append one JSON line per run to `evaluation/leash_history.jsonl`
   (`{ts, store, day, domain_scores, packets_since_last_move}`).
3. `--report` prints the trend table + THE YANK: if the last 5 merged packets (read
   `ops/packets/INDEX.md` MERGED lines) moved no domain number, print
   `LEASH: STOP — reassess with founder` and exit 2.
4. Tests: synthetic mini-stores proving a starved domain is flagged and the yank fires.

## Forbidden
Do not tune the canonical battery. Do not make leash numbers a merge gate (it's a
progress instrument; §7's gate stays the battery). No content lexicons in templates —
domain templates are structural (helper_id classes), not room-specific nouns.

## Done when
One command produces the per-domain report on `data/trace_store.sqlite3`, history file
grows, yank logic unit-tested, pytest green. INDEX flipped.
