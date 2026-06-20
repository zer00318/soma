# HANDOFF — 2026-06-19 (cockpit revamp DONE + entity-capture product sprint IN FLIGHT)

Read this top-to-bottom, then jump to **"NEXT STEPS"**. Two things happened this session:
(1) the founder's cockpit was properly revamped and PROVEN; (2) a product sprint to cut
cold-clip hallucination is RUNNING in the background right now (local gemma + Codex + GPU).

---

## PART 1 — COCKPIT REVAMP (complete, proven, no action needed)

Symptom: cockpit stuck on "Connecting…". Root causes (all fixed):
- **No supervisor** → server died and nothing restarted it.
- **Fake heartbeat** → liveness was the mtime of nightly files → always "QUIET".
- **localhost trap** → dark from the founder's phone.
- **macOS TCC** → a launchd LaunchAgent CANNOT read `~/Documents` (`Operation not
  permitted`). This is why the "proper" launchd path silently failed.

Fix shipped:
- Supervisor = **userland keepalive** (`scripts/cockpit_keepalive.sh` via
  `scripts/cockpit_supervise.sh`), runs in the authorized session, NO Full Disk Access
  needed. Self-heals in ~3s; survives crash/sleep/session-end. NOT full reboot (needs the
  optional FDA grant + `scripts/install_cockpit_agent.sh` + `ops/com.trace.cockpit.plist`).
- Honest 2-light liveness: SERVER (live HTTP reply w/ `server_ts`) + CHIEF (read from
  `ops/cockpit/heartbeat.json` via `scripts/cockpit_beat.py`; states working/idle/stopped/
  no-data vs the Chief's own `expected_next_s`). Wired into `evaluation/run_live.py`
  (`_write_status`) and `scripts/claude_supervisor_loop.py` (`update_state`).
- Never-dark client (`scripts/cockpit_client.html`): AbortController 4s + self-scheduling
  poll + last-known-good + phone LAN URL.
- PROOF = `scripts/verify_cockpit.sh` (kills server, asserts self-heal to a NEW pid). PASSED.
- The non-functional launchd plist was REMOVED from `~/Library/LaunchAgents/` so it won't
  flap at login. Repo template stays at `ops/com.trace.cockpit.plist`.
- Memory written: `memory/cockpit-supervision-and-tcc.md` (+ MEMORY.md index line).

The cockpit is UP now (keepalive pid was 27275, server respawns). Verify anytime:
`curl -s http://localhost:8788/api/state` and `scripts/verify_cockpit.sh`.

---

## PART 2 — PRODUCT SPRINT: kill cold-clip hallucination (RUNNING — this is the real work)

### The honest problem
Cold clip `day_in_life_20260618`: the brain FABRICATES grounded-looking answers
("bag **zip=closed** at t=30.5s" — there is no zip sensor; "Röntgen" name carried onto the
WRONG poster). Diagnosis: **12 of 16 misses are (B) brain, only 3 (A) missing channel.**

### KEY FINDING (proven offline this session — do not re-litigate)
The hallucination is **MIS-BINDING, not missing tokens.** Proof: a blunt corpus-grounding
gate ("G4") tested offline against all 25 cold drafts caught **0** extra fabrications and
**killed 4 correct answers** (RAS 57.1→40.0, halluc 21.4%→30%). Reason: the missed
fabrications ("zip closed", "train", chat name) have their tokens PRESENT in the corpus —
they're bound to the wrong entity/time. A presence-check is structurally incapable of
catching that. **G4 is DISABLED in `scripts/ask_home.py` (`ASSEMBLER_G4_FLOOR = False`),
documented, kept (not deleted) so it isn't re-tried.** The real fix = entity-centric binding.

### What's DONE + verified
- **Codex wired entity-capture into the brain** (`scripts/ask_home.py`): `gather_evidence`
  now loads sibling `entity_capture.json` (NDJSON) as `channels["entity_capture"]`;
  `build_evidence_dossier` emits an ENTITY CAPTURE section (PERSON/OBJECT/SELF-VIEW lines,
  logo bound to its object) + a conservative "attribute-not-recorded → refuse" NOTE.
  Test: `tests/test_entity_capture_wiring.py` (PASSES, run via
  `.venv/bin/python tests/test_entity_capture_wiring.py` — pytest not installed).
  VERIFIED: compiles; existing gate unchanged (still 4-caught/2-killed offline); degrades
  safely when `entity_capture.json` is absent. Result file:
  `ops/CODEX_BRIEF_entity_wiring_RESULT.md`. Brief: `ops/CODEX_BRIEF_entity_wiring.md`.

### What's RUNNING right now (background)
- **Baseline re-score** (local gemma): nohup, was pid **28025**, checkpoint
  `/tmp/cold_rescore.jsonl`, status `ops/cockpit/eval_live.json`, log `/tmp/cold_rescore.log`.
  ~8/25 when last checked. NOTE eval_live.json earlier showed 60% halluc (19q) but
  scoreboard.jsonl (25q, with gate) showed 21% — THIS re-score resolves which is true NOW.
- **Chained GPU job** (harness bg id **b5mro0d3i**, script `/tmp/sprint_stageAB.sh`): waits
  for the re-score to finish → snapshots baseline to `/tmp/cold_baseline_eval.json` → runs
  the entity-capture GPU build:
  `.venv/bin/python scripts/build_entity_capture.py --frames-dir
  data/walks/day_in_life_20260618/work/run_frames --out
  data/walks/day_in_life_20260618/memory/entity_capture.json` (Qwen2.5-VL, cap 120 keyframes).
  Log `/tmp/entity_build.log`. Output (new chat will be notified when it completes):
  `.../tasks/b5mro0d3i.output`.

### Constraint
ONE heavy GPU job at a time (M2). gemma re-score and Qwen-VL capture must NOT run together —
that's why the build is chained AFTER the re-score.

---

## NEXT STEPS (for the new chat — in order)
1. Check the chained job: is `data/walks/day_in_life_20260618/memory/entity_capture.json`
   written? `wc -l` it; spot-check 2-3 rows have `persons`/`text_objects` with bound
   attributes and `parse_ok:true`. Check `/tmp/entity_build.log` for errors. Verify, don't trust.
2. Read the baseline number: `cat /tmp/cold_baseline_eval.json` (or eval_live.json if not
   yet snapshotted).
3. Run the FINAL re-score WITH binding wired in (GPU must be free — re-score + build done):
   ```
   rm -f /tmp/cold_withentity.jsonl
   .venv/bin/python evaluation/run_live.py \
     --questions evaluation/ras/day_in_life_20260618.txt \
     --gold evaluation/ras/day_in_life_20260618.gold.json \
     --memory data/walks/day_in_life_20260618/memory/world_memory.json \
     --model gemma3:12b-it-qat \
     --checkpoint /tmp/cold_withentity.jsonl \
     --status ops/cockpit/eval_live.json
   ```
   (Same `--memory` dir so `gather_evidence` finds `entity_capture.json` beside it.)
4. Compare BEFORE (`/tmp/cold_baseline_eval.json`) vs AFTER (final eval_live.json):
   `halluc_pct`, `hard_ras`, correct/wrong/miss. Report honest before→after.
5. Per-question diff: did Q9/Q10 (poster binding), Q17/Q18 (bag attrs), Q18-mate-logo improve?
   The 3 mis-binding fabrications to watch: **Q17 zip, Q20 train, Q22 chat**. For each
   remaining miss, label (A) missing channel vs (B) brain. Update `ops/cockpit/diagnosis_dil.json`.
6. Update `ops/cockpit/status.json` honestly with the measured number (don't claim).
   Guard the founder's "no per-clip bandage" rule: any gate/capture change must hold on BOTH
   clips (also re-score the WALK clip `walk_outside_20260614` before trusting a win).

## State / hygiene
- NOTHING is committed. Uncommitted: cockpit files (ops_cockpit.py, cockpit_client.html,
  cockpit_beat.py, cockpit_keepalive.sh, cockpit_supervise.sh, install_cockpit_agent.sh,
  verify_cockpit.sh, com.trace.cockpit.plist), `scripts/ask_home.py` (G4 + entity wiring),
  `evaluation/run_live.py` + `scripts/claude_supervisor_loop.py` (heartbeat), the test, and
  status/asks json. Commit only if the founder asks.
- Canonical plan = `ops/ROADMAP.md`. Prime directive: lossless context → answerable at
  near-zero hallucination. Honesty over inflated numbers; real tests over gauging.
- Local models via `/Applications/Ollama.app/Contents/Resources/ollama` (gemma3:12b-it-qat,
  gemma3:27b-it-qat). Codex via `/Applications/Codex.app/Contents/Resources/codex exec
  --full-auto -s workspace-write` (or `scripts/run_codex_brief.sh <brief.md>`). venv =
  `.venv/bin/python` (transformers 4.49 pinned, torch 2.8 MPS).
