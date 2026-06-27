# SERIAL EXECUTION LEDGER — 2026-06-27 (Commander-in-Chief)
*Pitch day: 2026-07-01 (4 days). Strictly serial: a task ships only when its gate test AND the full
suite are green. No padding the queue with not-yet-ready work — that was the metric-illusion we killed.*

## VERDICT THAT DROVE THIS (recap)
Dashboard claimed 44% / reasoner 80% / "near-zero hallucination." Reality: 44% = mean of gemma-
authored pillar guesses; 80% = hardcoded constant; the only real eval is RAS 9.1 / 30% halluc. The
greenfield store + digital capture are REAL (508 nodes). The store reasoner was a real grounded
reasoner crippled by a regex/hardcoded-brand fast-path AND unwired from the live /ask. True pitch-
readiness ≈ 15%.

## PHASE 1 — LIQUIDATION (enacted this session)
- **KILLED** the gemma-authored progress number. `agent_orchestrator._mechanical_overall` +
  `cockpit_updater._mechanical_progress` now compute overall_progress from REAL signals only
  (store nodes, daemons, eval artifact, wiring flag). The Planner agent can no longer inflate it.
- **KILLED** the hardcoded `reasoner_pct = 80`. Both writers now read `evaluation/ras/store_eval.json`
  or show **UNMEASURED**. The dashboard will read ~30% / UNMEASURED until a real eval exists.
- **KILLED** the regex/hardcoded-brand fast-path in the production reasoner
  (`brain/agent.py::_heuristic_answer` → returns None). Every question now flows to grounded
  retrieval + the evidence-only LLM contract. (test_agent.py rewritten to encode the new spec; green.)
- **LIQUIDATED** the autonomous_worker TASK_QUEUE (activity/specialist/instance-graph = rejected
  abstraction). The function-splice worker fits isolated stub-fills only; it is NOT the vehicle for
  the multi-function pitch work below.
- **PROTECTED**: committed the untracked greenfield spine (was one `git checkout` from oblivion).

## PHASE 1 — STILL TO LIQUIDATE (no further effort)
- FROZEN: `inject_*`, `activity_*`, `specialist_*`, `instance_*`, `world_binder/node_merge/
  spatial_relations` as PRODUCT paths. They may survive as offline tools; no new work on them.
- The eval's OWN rig: `annotate_live.py::_heuristic_answer` has the same hardcoded brands — the
  default `--reasoner heuristic` grades the rig with the rig. Fixed in T1 below.

## PHASE 2 — THE SERIAL LEDGER (linear; each validates before the next)
Two execution lanes:
- **CHIEF lane** — multi-function refactors + live-server wiring (the splice-worker can't do these).
- **MACHINE lane (24/7)** — long-running jobs the orchestrator runs unattended: (a) the REAL eval
  once unified, (b) more dense perception into the store. These are the genuine overnight grind.

---
### T1 — Unify + de-rig the eval onto the PRODUCTION agent  [CHIEF, next]
- **Input:** `evaluation/annotate_live.py` (delete `_heuristic_answer` + regex/brand constants;
  route `answer_question` through `trace_memory.brain.TraceMemoryAgent`), `brain/agent.py`.
- **Directive:** the eval MUST score the same agent the demo uses. `answer_question(store, q,
  reasoner, model, host)` constructs `TraceMemoryAgent(store, reasoner=...)` and returns its
  AgentAnswer as a dict. Default reasoner for a real number = `local-ollama` (or `frontier` with
  ANTHROPIC_API_KEY). Write the summary to `evaluation/ras/store_eval.json` with keys
  `answered_pct`, `halluc_pct`, `n` (the exact keys the honest cockpit reads).
- **Validation:** `tests/unit/test_eval_uses_production_agent.py` — (a) no hardcoded brand/flavour
  strings remain in source; (b) `answer_question(..., reasoner="heuristic")` returns refused=True
  (no fabrication, matches the honesty floor); (c) a run writes store_eval.json with the 3 keys.

### T2 — Wire the store reasoner into the LIVE /ask as PRIMARY  [CHIEF]
- **Input:** `scripts/trace_brain_server.py` (the answer cascade ~L1060–1230, currently eventlog +
  ask_home), `brain/agent.py`, the live store at `data/trace_store.sqlite3`.
- **Directive:** on `/ask`, FIRST call `TraceMemoryAgent(store, reasoner="frontier").answer(q)`.
  If grounded non-refusal → return it (source="store_agent", include evidence_chain). Else fall
  back to the existing cascade. On success, `touch ops/cockpit/reasoner_wired.flag` (the cockpit
  awards +25 only when this is real). Keep the self/world honesty guard.
- **Validation:** `tests/test_brain_store_wired.py` — seed the store with a known node, hit the
  answer fn, assert source=="store_agent" and the answer cites that node id; grep the import+call
  exist in the live path. Then a live curl proof: ask about something in the 508-node store → the
  answer cites a `mac_screen`/`phys_video` node, not kf_memory.

### T3 — The REAL number  [MACHINE lane, 24/7, gated on T1]
- **Input:** `evaluation/annotate_live.py` (unified), founder gold
  `data/phone_captures/live/ground_truth.json` (n=11, grow via `--append`), live store.
- **Directive:** orchestrator's Evaluator runs `annotate_live --reasoner frontier --repeats 3`
  nightly over ALL gold → `evaluation/ras/store_eval.json`. Founder adds gold as he lives
  (`--append --question ... --true-answer ...`). The number on the cockpit is THIS, or UNMEASURED.
- **Validation:** store_eval.json exists, n≥10, reproduces within ±1 on rerun; cockpit reasoner_pct
  reads it; **gate = answered ≥75% AND confident-wrong <10%** (the sacred floor). Below floor = red.

### T4 — Sleep-authored cross-links (the Obsidian web)  [CHIEF, after T2]
- **Input:** `src/trace_memory/store/sleep.py`, `sqlite_store.link()`, the live store.
- **Directive:** nightly pass authoring links — same-time, same-place, same-entity (semantic),
  succession — over the store; mark abstraction nodes derived. Conservative; weak links refused.
- **Validation:** `tests/unit/test_sleep_links.py` — over a seeded multi-frame fixture, the right
  links appear, no spurious cross-entity links, abstractions flagged derived. Then neighbors() of a
  hero node returns the lifecycle chain.

### T5 — Live-capture decision  [BLOCKED on founder]
- On-device live recorder is broken; the demo is locked "fully live." Either fix on-device capture
  (risky, ~1 day) OR lead the demo with the LIVE digital pillar (works) + the validated physical
  shelf. **This is the single biggest pitch risk and needs the founder's call before T-track work.**

## OPERATING RULES (this sprint)
- No number reaches the cockpit without a script that computes it. UNMEASURED is honest; 80 was not.
- Honesty floor <10% confident-wrong is sacred; coverage is the stretch.
- Chief does multi-function + server wiring; machines grind the eval + perception 24/7.
- Validate by running the artifact, not by an agent's say-so (the echo chamber we just broke).
