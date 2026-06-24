# HANDOFF — for the next Chief chat (resume here)
*Written 2026-06-24, end of cycle 12. Branch `chief/p0-honesty-sprint`, cwd `/Users/zer00/Documents/VLM`.
Read `ops/PRODUCT_NORTH_STAR.md` + `ops/ANTI_TUNNEL_LEASH.md` first, then this. The founder is Satoshi;
you are the Chief (autonomous). The founder is near the Claude usage limit — preserve YOUR tokens, run
LOCAL LLMs (ollama gemma3:12b/27b) majorly, Codex sparingly.*

## THE PRODUCT (don't re-derive)
TRACE = open-domain QA over lived experience. **HELPERS extract → INJECT binds at capture → LLM thinks
& refuses past the edge.** Capture PRIMARY (irreversible); world-reach BACKSTOP. Privacy: no raw MEDIA
stored/leaves, derived TEXT free. Moat = binds/reads-or-refuses, never makes things up. Real platform =
the phone; the Mac is a blindfolded proxy (no live vision).

## WHAT'S DONE + COMMITTED THIS CYCLE (verified)
1. **WS1 — self/world binding guard** (`scripts/self_world_guard.py`, wired into `ask_home.ask`, commit
   `29d3030`). External text never binds to the wearer-self or a named co-present person without
   `self_entity` corroboration. Killed all 3 day-clip hallucinations (60%→0%), 0 regressions. Verified 4
   ways (30-case unit, 88-answer replay, live gemma, full re-score). NOT a name blocklist — structural.
2. **WS2 — capture-time binder v0** (`scripts/inject_bind.py`, commit `40eebb9`). Deterministic
   temporal/identity binding: groups observations into persistent ENTITIES across frames; confidence
   from CORROBORATION (frequency/consensus), low-confidence ABSTAINS. Day clip: 328 obs → 51 confident
   entities vs 139 garbles correctly abstained. 6/6 unit checks. **Spatial binding NOT built — no capture
   has boxes; needs a fresh box-bearing founder capture.**
3. **Cockpit v3** (`ops/cockpit/cockpit_ops.html` + `agent_plan.json`; backend in
   `scripts/cockpit_ask_server.py`, commit `40eebb9`). Glance board: 🎯 distance-to-grail bar, the
   HELPERS→INJECT→LLM engine with per-stage + per-helper health bars (red when weak), crew, tasks, a live
   flight recorder (`ops/cockpit/activity.jsonl` via `scripts/clog.py`), honesty vitals. Machine-load
   REMOVED (founder reads CPU from Activity Monitor). Founder verdict: "correct direction finally."

## ███ RUNNING NOW (local-LLM job) ███
`evaluation/run_binding_audit.py` — detached, checkpointed, on local gemma3:12b. Measures **binding
precision**: of the 51+ CONFIDENT binds, what fraction are coherent real things vs OCR noise (replaces
an ESTIMATE with a MEASUREMENT — the founder is skeptical of estimated %s, rightly).
- Monitor: `ops/cockpit/binding_audit.json` (status/precision_pct per clip) + `tail /tmp/binding_audit.log`.
- It clogs progress to the cockpit flight recorder. When done it writes `overall.precision_pct`.
- Relaunch (to keep local LLMs grinding 24/7): `pkill -f run_binding_audit; PYTHONUNBUFFERED=1 nohup
  caffeinate -is .venv/bin/python evaluation/run_binding_audit.py > /tmp/binding_audit.log 2>&1 & disown`
- If the box gets sluggish, kill it (`pkill -f run_binding_audit`) to protect the machine.

## FOUNDER DIRECTIVES (latest, honor these)
- **Numbers must be MEASURED, not estimated.** Founder disputes the cockpit progress %s — they are my
  honest *estimates* of how-far-along (grail 50, HELPERS 50, INJECT 45, helper %s). The VITALS (0%
  halluc, 15.9% recall, 45.5% ceiling) ARE measured (guarded re-score). **Separate the two on the
  cockpit and replace estimates with measured signals wherever possible** (binding precision, real eval).
- **Cockpit: more info, more interactable, much more** ("improve later" — not this cycle, but it's where
  it's heading: clickable segments, drill-downs, live Q&A demo card, real measured numbers).
- **Run local LLMs ~24/7; preserve Claude tokens; the Chief should chill** between launches.
- **Actual progress**, not rambling. Glance-readable surfaces.

## WHERE WE'RE HEADING (next moves, in order)
1. **Read the binding-audit result** (when `binding_audit.json` status=done) → put the MEASURED binding
   precision on the cockpit, replacing the INJECT estimate. Spot-check a few verdicts by hand.
2. **Wire `inject_bind` into the brain** so "where did I see this before / what did I see repeatedly" is
   answered from BOUND entities (currently the binder is built but unwired). Re-measure honestly.
3. **The number is THE gate** (north star §8): n≥50 fresh held-out + human gold. BLOCKED on the founder
   (a fresh capture + gold). Prep everything so it's one founder session away.
4. **Spatial binding** (drink→person): BLOCKED on a fresh box-bearing capture. Either (a) founder captures
   with per-observation boxes persisted, or (b) build Stage-1 localization to emit boxes first.
5. **Cockpit v4**: interactivity + drill-downs + a live "see a place → know what it is" demo card; only
   MEASURED numbers.

## OPERATING RULES (hard-won)
- Local LLMs majorly; Codex sparingly + time-boxed; preserve Claude tokens.
- Harness-tracked background jobs for work you must track; detached+caffeinate ONLY for the founder's
  explicit "run 24/7" grind (this binding audit) — document monitoring so you don't go dark.
- No raw media stored/leaves; personal_evidence vs world_context never merge; LLM self-confidence is
  worthless — gate on geometry/corroboration (ZLORPTECH lesson).
- Run the leash every cycle; every `[STATE_MANIFEST]` carries a `LEASH:` line. One demo ≠ verified.
- Cockpit: restart `scripts/cockpit_ask_server.py` after SERVER-code edits (HTML/JSON are re-read live).
  `pkill -f cockpit_ask_server; PYTHONUNBUFFERED=1 nohup python3 scripts/cockpit_ask_server.py >
  ops/cockpit/cockpit_server.log 2>&1 & disown` then curl `/ops` for 200.

## KEY PATHS
- Brain: `scripts/ask_home.py` (`ask`, `ask_with_understanding`). Guard: `scripts/self_world_guard.py`.
  Binder: `scripts/inject_bind.py`. Self channel: `scripts/self_entity.py`.
- Cockpit: `http://127.0.0.1:8799/ops` (glance board) + `/engine` (product reality). Data:
  `ops/cockpit/{agent_plan,engine,activity,binding_audit}.json`. Logger: `scripts/clog.py`.
- Memories: `data/live_replay/{day_in_life_20260618,walk_outside_20260614}_live44/memory/` (blindfolded);
  `data/walks/{...}/memory/` (caption-rich = ceiling). Eval: `evaluation/run_live.py`,
  `evaluation/ras/live44_*_guarded.jsonl`.
- Resume anchors: `ops/SOVEREIGN_STATE.md` (newest [STATE_MANIFEST] at bottom), this file.
