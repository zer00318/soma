# SERIAL EXECUTION LEDGER — 2026-06-28 (Commander-in-Chief)
*Pitch day: 2026-07-01. One sanctioned queue only. One task only at a time. One validation gate per
task. No worker starts the next item until the current item is proven. This file overrides dashboard
percentages, stale handoffs, and any side queue that optimizes motion over readiness.*

## VERDICT THAT DRIVES THIS
- `44%` was planner math, not product readiness.
- `80%` was ops telemetry, not answer quality.
- `90%` was checklist theater, not prototype truth.
- The only founder-safe metrics are measured artifacts:
  - `evaluation/ras/store_eval.json`
  - `evaluation/ras/live44_summary.json`
- Real readiness remains about **18%** until the live path and the measured store score move.

## PHASE 1 — IMMEDIATE TASK LIQUIDATION & PRUNING

### KILLED as founder-facing readiness signals
- `ops/cockpit/project_plan.json` percentages
- `ops/cockpit/pitch_progress.json` percent headline
- `ops/cockpit/agent_plan.json` grail / helper / pipeline percentages
- `overall_progress` as a founder-facing product-completion claim

These may survive as ops telemetry only. They are no longer authorized to answer “how ready are we?”.

### FROZEN as active product work
- `scripts/inject_*`
- `scripts/activity_*`
- `scripts/specialist_*`
- `scripts/instance_*`
- `scripts/world_binder.py`
- `scripts/node_merge.py`
- `scripts/spatial_relations.py`
- fixture-only `evaluation/results/scene_eval_latest.json` optimization
- cockpit cosmetics that do not improve truth, live-path proof, or the real number

Rationale: these families created local wins and visual activity, but they are not the bottleneck
between us and a pitch-safe prototype.

### ALTERED
- `scripts/ask_home.py` is now fallback territory, not the success criterion.
- `src/trace_memory/brain/agent.py` plus the unified store is the judged answer path.
- `ops/codex_queue/pending/13_kf_memory_persistence.md` is FROZEN and moved to
  `ops/codex_queue/frozen/13_kf_memory_persistence.md`.

## PHASE 2 — THE 24/7 SERIAL EXECUTION LEDGER
No parallel feature hunts. No “while I’m here” edits. No worker decides its own adjacent task.

### T1 — Truth Surface Demotion  [Chief -> Codex]
- **Input Context:**
  `ops/cockpit/founder_dash.html`, `scripts/cockpit_ask_server.py`, `scripts/cockpit_updater.py`,
  `scripts/agent_orchestrator.py`, `ops/cockpit/project_plan.json`, `ops/cockpit/pitch_progress.json`,
  `evaluation/ras/store_eval.json`, `evaluation/ras/live44_summary.json`
- **Exact Prompt / Directive:**
  Use `ops/serial_queue/01_truth_surface_demotion.md`.
- **Validation Metric:**
  Founder-facing dashboard no longer presents fake readiness percentages as product completeness;
  cockpit tests stay green; measured sources are explicit.

### T2 — Store Agent Primary Path Proof  [Chief -> Codex]
- **Input Context:**
  `scripts/trace_brain_server.py`, `src/trace_memory/brain/agent.py`,
  `evaluation/annotate_live.py`, `tests/test_store_agent_wired.py`,
  `tests/test_trace_brain_server.py`, `tests/unit/test_eval_uses_production_agent.py`
- **Exact Prompt / Directive:**
  Use `ops/serial_queue/02_store_agent_primary.md`.
- **Validation Metric:**
  Focused store/live-path tests pass; successful live answers explicitly report `source=store_agent`;
  no new hardcoded heuristics are introduced.

### T3 — The Real Number Runtime  [Machine lane, overnight]
- **Input Context:**
  `evaluation/annotate_live.py`, `evaluation/ras/store_eval.json`,
  `data/phone_captures/live/ground_truth.json`, `data/trace_store.sqlite3`,
  `scripts/cockpit_ask_server.py`
- **Exact Prompt / Directive:**
  Use `ops/serial_queue/03_real_number_runtime.md`.
- **Validation Metric:**
  `store_eval.json` exists with `answered_pct`, `halluc_pct`, and `n`; reruns are stable; cockpit
  reads this artifact instead of planner math.

### T4 — Failure Concentration Pass  [Chief]
- **Input Context:**
  Latest `store_eval.json`, `evaluation/ras/live44_summary.json`, the founder ground truth rows that
  failed, `scripts/trace_brain_server.py`, `src/trace_memory/brain/agent.py`
- **Exact Prompt / Directive:**
  Patch only the dominant failure class after T3. Classify failures as:
  `capture missing`, `retrieval miss`, `binding/self-attribution`, or `reasoner overreach`.
  Do not open any new feature family before one class is materially improved.
- **Validation Metric:**
  The next measured run improves the dominant class without increasing hallucination.

### T5 — Live Capture Go / No-Go  [Blocked on founder]
- **Input Context:**
  Native app reality, current recorder state, founder demo constraints
- **Exact Prompt / Directive:**
  Choose one pitch mode explicitly:
  1. controlled curated demo
  2. live prototype demo
  No hybrid lie. Once chosen, every remaining task must serve that mode only.
- **Validation Metric:**
  The chosen mode is written into the active handoff and cockpit wording, and all non-serving work
  stays frozen.

## STANDBY COMMAND — FIRST BATCH
Use the sanctioned dispatcher:

```bash
./scripts/run_phase1_serial.sh list
./scripts/run_phase1_serial.sh 01
./scripts/run_phase1_serial.sh 02
./scripts/run_phase1_serial.sh 03
```

Rules:
- Do not run `02` before `01` validates.
- Do not run `03` before `02` validates.
- After `03`, stop and read the number before assigning anything else.

## OPERATING RULES
- No number reaches the founder without a script-produced artifact.
- No fixture-only result may be called product readiness.
- No queue item outside this ledger is authorized.
- No new feature family opens until the truthful surface, live path, and real number are in line.
- Validate by running the artifact, never by trusting narration.

---

## JUDGMENT — 2026-06-28 08:0x (Supreme Judge pass, fresh Chief)
RE-AUDITED against raw artifacts. The ledger's ~18% was generous on the axis that matters.
- MEASURED TRUTH (`store_eval.json`): answered 18% / **hallucination 45.5%** / 2 correct of 11 /
  5 confident-wrong / gate FAILED. The honesty moat is INVERTED (lies > truths when it answers).
- DEMO BRAIN UNTESTED: eval defaults to `--reasoner frontier` but NO `ANTHROPIC_API_KEY` is loaded →
  silently scored on LOCAL gemma. The frontier config we will demo on has NEVER been measured.
- STORE POLLUTED: nodes dominated by `mac_screen` capture of YouTube + the Claude/Codex apps
  (us building the product) ingested as "lived experience." Band-aided via `restrict_sources` at
  retrieval instead of fixed at capture.
- LINKS ~5%: 101 links / 1401 nodes, only `succession`+`same_place`. No semantic / same-entity web.
- BRIGHT SPOT: `src/trace_memory/brain/agent.py` is genuinely de-schematized (regex fast-path
  deleted, precise retrieval + multi-hop + evidence-only contract + frontier/local backends).
- ECHO CHAMBER: 359 synthetic unit tests GREEN while the one real-data number says 45.5% halluc.
- HONEST READINESS toward a jaw-dropping pitch: ~15% (architecture real; experience net-negative).

### CORRECTIONS (ordered, pitch 2026-07-01)
C2 first: load `.secrets/frontier.env`, run `store_eval` on `--reasoner frontier` — measure the real
demo brain TODAY. → C1: retrieval-confidence REFUSAL gate, crush halluc <10% even at coverage cost. →
C3: clean demo store (purge mac_screen dev/YouTube at CAPTURE). → re-measure. → C4 (parallel): cockpit
headline reads store_eval.json only; kill 44/90. → C5: grow ground truth n≥30. → C6: specialists stay
FROZEN + off the cockpit; build semantic/same-entity links AFTER C1. → C7: NO live demo until C1 is
measured green on frontier.

====================================================================================
# ACTIVE COMMAND — 2026-06-28 morning (Commander-in-Chief, execution mode)
# New bedroom recording (capture_1782627772.mov, 08:22) + 21 founder ground-truth Qs.
# Pitch: 2026-07-01. ROOT CAUSE found: store is 79% self-homework pollution (mac_screen:
# YouTube/Claude/Codex), drowning the real phone_camera recording in retrieval.
====================================================================================

## PHASE 1 — LIQUIDATION (effective immediately)

### KILLED (off the board, not founder-facing, not worked)
- Cockpit `pitch_progress.json` 90% headline + the 44% founder-dash number — dead, replaced by the
  measured artifact only.
- The dead autopilot daemon (pid 29394, armed 07:42 then died) — restarted clean.
- Old shelf ground-truth (rings/pringles, n=11) — replaced by the 21 bedroom Qs.

### FROZEN (do NOT touch, do NOT extend, off the critical path)
- scripts/specialist_* (chess/cooking/reading), scripts/activity_*, scripts/instance_*,
  scripts/world_binder.py, node_merge.py, spatial_relations.py — local wins, zero effect on the number.
- scripts/ask_home.py — fallback only; src/trace_memory/brain/agent.py is the judged path.

### ALTERED
- Capture pollution stops at the SOURCE: screen_capture_daemon must skip dev/entertainment apps.
- The judged answer path runs on a CLEAN demo store, frontier reasoner, source-scoped.

## PHASE 2 — THE NEW SERIAL QUEUE (one at a time; validate before next)

- **S1 / 04_store_hygiene** — build clean demo store (phone_camera + intentional only; denylist
  Claude/Codex/YouTube/Brave...); stop ongoing pollution. GATE: denylist residue 0, phone signal intact.
- **S2 / real number** — annotate_live --reasoner frontier on the demo store vs 21 Qs, repeats 3.
  GATE: store_eval.json n=21, stable across repeats. (FIRST cut already running on phone_camera scope.)
- **S3 / 05_refusal_gate** — pre-LLM confidence/coverage/conflict gate. GATE: halluc <10% AND correct>0.
- **S4 / failure concentration** — patch ONLY the dominant miss class. GATE: dominant class up, halluc <10%.
- **S5 / truth surface** — cockpit headline = store_eval.json (21Q frontier); specialists off the board.

SERIAL LAW: S1 -> S2 -> S3 -> re-S2 -> S4 -> re-S2 -> S5. No parallel feature hunts. No "while I'm here".

## STANDBY — FIRST EXECUTABLE BATCH
```bash
# S1 (workforce: Codex/local executor on ops/serial_queue/04_store_hygiene.md)
.venv/bin/python scripts/build_demo_store.py            # to be written per task 04
# S2 real number (frontier, clean store, 21Q)
set -a; source .secrets/frontier.env; set +a
TRACE_RESTRICT_SOURCES=phone_camera .venv/bin/python evaluation/annotate_live.py \
  --store data/trace_store_demo.sqlite3 --reasoner frontier --repeats 3
cat evaluation/ras/store_eval.json
```

====================================================================================
# MEASURED VERDICT — 2026-06-28 (Commander-in-Chief, on the NEW bedroom recording + 21 Qs)
====================================================================================
## THE REAL NUMBER (frontier brain, clean store, pollution excluded, n=21)
- answered 17/21, **correct 0, confident-wrong 16, halluc 76.2%, gate FAILED.**
- store_eval (old polluted shelf, local): 18%/45.5%. Cleaning + frontier did NOT save it.

## DIAGNOSIS = (A) CAPTURE FAILURE, quantified
- The recording is 105s / 3053 frames @ 29fps. WE PERCEIVED 8 FRAMES (0.26%).
- Truths NOT in the store: diary colour, fan mode 0/1/2, laptop app (Codex), battery %, pillow count.
- Truths captured but GARBLED: pesto/nutella labels = OCR soup; per-frame count says 3 (truth 5).
- Brain/store/retrieval WORK — they faithfully surface absent/garbled perception. Perception is the wall.

## WHAT I DID THIS PASS (executed, not planned)
- S1 build_demo_store.py: clean demo store 413 nodes (was 1839), 0 mac_screen residue, phone signal 295/295 intact.
- S2 measured the real number above (frontier, scoped).
- S-top reperceive_recording.py: DENSE re-perception (2fps, blur-gated) of the recording into the
  demo store — RUNNING now (frame 406 first kept; 0-405 blur-dropped). Log /tmp/reperceive.log.

## CORRECTED SERIAL QUEUE (capture is the lever, not the brain)
- S-top / reperceive  : dense re-perception -> demo store. GATE: >=120 sharp frames perceived, diary/
  fan/pesto/laptop facts now PRESENT in node text (probe by keyword).
- S-next / re-measure  : annotate_live --reasoner frontier on demo store vs 21Q. GATE: correct rises.
- S3 / refusal gate    : 05_refusal_gate.md — convert remaining confident-wrong -> honest refusal.
  GATE: halluc <10% AND correct>0.
- S4 / counting        : unfreeze geometric count (world_binder) ONLY for count Qs (3->5 nutella).
- S5 / truth surface   : cockpit headline = store_eval.json (21Q frontier). Kill 44/90.

## FOUNDER DECISION REQUIRED (the planning-session tension, now measured)
Some facts (fan dial, battery %, Codex app, diary colour) are only answerable if the camera actually
DWELLED on them. A single passive 105s pan may not contain them clearly. Honest pitch options:
  (a) Accept partial honest coverage on this recording (never-lies + nails-what-it-saw), OR
  (b) Re-record demo footage that deliberately pans slow/close over the objects you'll be asked about
      (richer capture, still passive in spirit, but framed to CONTAIN the answers). Higher coverage.
