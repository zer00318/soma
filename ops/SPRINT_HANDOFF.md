# MAJOR SPRINT HANDOFF — build the complete TRACE prototype
*Boot prompt for a fresh Chief instance. The design phase is DONE; this is EXECUTION. You are
authorized to use agent teams / sub-agents / Workflow orchestration to drive real growth toward the
complete prototype. Branch `chief/p0-honesty-sprint`, cwd `/Users/zer00/Documents/VLM`.*

---

## 0. READ FIRST (the locked understanding — do not re-derive, do not re-litigate)
1. `ops/PRODUCT_NORTH_STAR.md` — what the product IS and the architecture. THE authority.
2. `ops/ANTI_TUNNEL_LEASH.md` — run it every cycle; no "done" on one demo; no fake numbers.
3. `ops/AUTONOMOUS_CONTINUATION.md` — operating loop + key facts.
4. This file — the sprint plan.

The founder's words: "We now have a complete idea of what the product is and how to execute." Trust
that. Do NOT reopen the product definition. Build.

## 1. THE PRODUCT (one paragraph)
TRACE is **open-domain question answering over your own lived experience.** Pipeline:
**HELPERS extract (open-ended society) → INJECT binds them at capture into one provenance + confidence
scene/event graph (the binding brain) → LLM thinks over it and refuses honestly past the edge of
capture.** Capture is PRIMARY (the moment is irreversible); world-reach is the BACKSTOP. Privacy line:
**no raw MEDIA is ever stored or leaves the device; derived TEXT is free.** The moat is
**binds/reads-or-refuses** — it never makes things up. The real platform is the **phone** (native app,
fast on-device vision); the Mac is a weak proxy with no live vision.

## 2. WHERE WE ARE (honest, evidence-backed — 2026-06-24)
- **Demo: READY.** Cockpit at http://127.0.0.1:8799 (curated instant beats). Operational view at
  `/ops`, product reality at `/engine`.
- **The fair number is in.** Same 44 founder questions, two conditions:
  - FLOOR (live-helper on this Mac, **vision OFF** — no live VLM captions): **~17% correct.**
  - CEILING (same Qs vs **caption-rich memory, vision ON**): **45.5% correct, 4.8% hallucination**
    (`evaluation/ras/ceiling_run.json`, `ops/cockpit/eval_ceiling.json`).
  - **Verdict: the product is CAPABLE and the moat HOLDS** (walk clip had 0 hallucinations). The low
    floor was a *blindfold* (no live vision on this Mac), not a regression. The phone removes that.
- **The one real bug:** 3 hallucinations, ALL self/world **binding** errors — a name read on a sign
  became *"my name" (Nezam Pinias)*; a "Sup, Rhett?" snippet became *"Rhett at my table"*; a garbled
  read became *"lectures by Me"*. Evidence: `evaluation/ras/live44_day.jsonl`. This is the Stage-3
  attribution gap leaking (north star §5.2).
- **6-stage pipeline status:** 0 Frame/Sync `partial` · 1 Detect/Localize `partial` · 2 Track/Identify
  `not_built` · 3 Bind/INJECT `not_built` **(primary gap)** · 4 Enrich `partial` · 5 Reason/LLM `built`.
- **Official number: UNMEASURED** — the gate is n≥50 fresh held-out questions + human gold (needs the
  founder for a capture + gold).
- Already real + verified: consensus OCR recall; EXPAND hallucination-gate; PII scrub wired+tested.

## 3. THE SPRINT GOAL (definition of "complete prototype")
A pitch-ready prototype where: (a) the **native phone app** captures rich, BOUND context end-to-end at
usable latency; (b) the brain answers **honestly** (binds/reads-or-refuses) with hallucination
in the low single digits on a **real held-out** capture; (c) a **trustworthy number at n≥50 human gold**
clears a pitch-worthy bar (target ≥45% correct / <10% halluc, matching the ceiling); (d) the **3-min
demo stays flawless**; (e) **Stage-3 binding/INJECT is real**, not faked.

## 4. WORKSTREAMS (parallelizable — use agent teams; each has a VERIFICATION GATE)
Run these as agent-team workflows where parallel; keep load-bearing brain edits carefully verified by
you. Suggested order by leverage:

**WS1 — Honesty moat: the self/world binding guard. [HIGHEST PRIORITY, surgical]**
Observed external text must NEVER bind to the wearer/self ("my name", "I was…") or to a person at the
scene without strong, corroborated evidence. Fix in `scripts/ask_home.py` (the assembler / premise
gate / self-attribution path). GATE: re-run the day clip — the 3 binding hallucinations must become
REFUSALS, with NO regression on the walk (still 0 hallucinations) or the ceiling correct-rate. Use an
adversarial verifier agent-team to try to make it mis-bind again.

**WS2 — INJECT binding layer (Stage 3) for real. [the architecture's primary gap]**
Build the provenance + confidence scene/event substrate that binds helper outputs at capture (north
star §3). Start with what current data supports: temporal/co-occurrence binding + entity identity
across frames (spatial boxes don't exist yet — see WS3). Emit binding_confidence; never collapse
provenance; bind conservatively. GATE: a binding-precision number on a real memory + low-confidence
binds correctly abstain. Brief exists: `ops/CODEX_BRIEF_stage3_binding_probe.md`.

**WS3 — Close floor→ceiling on the REAL platform (the phone). [the complete-prototype core]**
The ceiling proves capability with vision; the floor shows live-capture-on-Mac is the bottleneck. Get
the native app (`trace-native-fastvlm`) capturing rich BOUND context (vision+detector+OCR+speech+
location → INJECT) end-to-end and answering via the brain. GATE: a real on-phone capture answers a
handful of live questions correctly, honestly. (Native deploy constraints: see memory
`ios26-xcode-deploy-constraint`.)

**WS4 — The trustworthy number (the pitch gate). [needs founder for gold]**
Build/finish the capture + human-gold pipeline for n≥50 fresh held-out. You can prep everything; the
founder provides the capture + gold. GATE: a scored n≥50 run with 95%-ish honesty, logged to `/engine`.

**WS5 — Demo + cockpit hygiene.** Keep the 3-min demo flawless; keep `/ops` + `/engine` truthful and
glanceable. Cockpit is `scripts/cockpit_ask_server.py` + `ops/cockpit/{agent_plan,engine}.json`;
**restart the server after any server-code edit** or new routes 404.

**WS6 — Dead-weight cleanup.** 293 dirty files; duplicate scripts; `data/` 5.5G; 10 cockpit variants.
Brief exists: `ops/CODEX_BRIEF_dead_weight_audit.md` (report-only). Run audit → review → discard the
high-confidence safe items. GATE: tests still green, cockpit still serves, demo still works.

## 5. EXECUTION RULES (hard-won — violate at your peril)
- **Use agent teams / Workflow** for parallel workstreams, adversarial honesty verification, and
  loop-until-dry discovery. The founder explicitly wants this for real growth. Keep brain-critical
  edits verified by YOU (agent self-tests ≠ proof).
- **Local LLMs MAJORLY** (ollama gemma3:12b-it-qat / 27b-it-qat), **Codex sparingly** (it was slow +
  opaque — 22 min for a dashboard; prefer it only for self-contained codegen, time-box it).
- **Use HARNESS-TRACKED background jobs** (`run_in_background`), NOT detached `nohup` — detached jobs
  do NOT notify you, so you go dark and the founder sees nothing happen (this burned 35 min). Tracked
  jobs ping you on completion. Always write incremental checkpoints so a death is resumable.
- **Honesty:** floor vs ceiling kept distinct; never present the blindfolded number as "the product",
  never inflate the ceiling. No raw media stored/leaves. personal_evidence vs world_context never merge.
  Self-reported LLM confidence is worthless — gate on geometry/corroboration (the ZLORPTECH lesson).
- **Keep the founder seeing progress:** update `ops/cockpit/agent_plan.json` (status / doing_now /
  next_action / plan / blocked_on_founder) every cycle; it renders live on `/ops`.
- **Run the anti-tunnel leash every cycle.** Every state manifest carries a `LEASH:` line.

## 6. KEY PATHS / COMMANDS
- Brain: `scripts/ask_home.py` (`ask`, `ask_with_understanding`). Memories: `data/walks/<clip>/memory/
  kf_memory.json` (caption+OCR = the ceiling source). Eval gold: `evaluation/ras/*.gold.json`
  (founder accept/reject cues). Scorer: `evaluation/auto_score.py`. Ceiling harness:
  `evaluation/run_ceiling.py`. Live-helper battery: `evaluation/run_live_replay_battery.py`.
- Cockpit: `http://127.0.0.1:8799/ops` (ops), `/engine` (product reality). Restart:
  `pkill -f cockpit_ask_server; PYTHONUNBUFFERED=1 nohup python3 scripts/cockpit_ask_server.py > ops/cockpit/cockpit_server.log 2>&1 & disown` then curl `/ops` for 200.
- Codex: `codex exec --sandbox workspace-write -c approval_policy=never - < brief.md` (no ollama/
  localhost in its sandbox). Local Python can reach ollama + localhost.
- ABANDONED — do not touch: the offline founder-gold `n=48` path (`run_founder_gold_brain.py`); keep
  its refusal-scoring fix only.

## 7. FIRST MOVE
Run the leash, then start **WS1 (the binding guard)** — it's surgical, protects the moat (the whole
pitch), and is verifiable today on the day clip. Spin up an adversarial verification agent-team for it.
Update `/ops` so the founder can watch. Then WS6 (cleanup) and WS2 (INJECT) in parallel.

---

## SPRINT UPDATE — 2026-06-27 (Store Spine / Fallback Proof)

### Built
- Added a new clean store package under `src/trace_memory/store/`:
  - `sqlite_store.py`: append-only node/edge store with APIs `write_observation()`, `link()`, `search()`, `neighbors()`, `read_observation()`, `get_abstractions()`.
  - `embeddings.py`: local sentence-transformer discovery against cached Hugging Face snapshots, plus deterministic lexical fallback.
  - `ingest.py`: two ingest paths:
    - `ingest_validated_shelf(...)` for the intended 25-frame raw shelf corpus.
    - `ingest_kf_memory(...)` for already-derived capture corpora, so existing `kf_memory.json` artifacts can be loaded into the same spine immediately.
  - `models.py` + package exports.
- Added `evaluation/annotate_live.py`:
  - append mode for `{question, answer, when}` annotations.
  - score mode against any store DB.
  - outputs answered-rate, correct-rate, and confident-wrong-rate.
- Patched `scripts/instance_perceive.py` to:
  - load cached `grounding-dino-tiny` snapshots directly instead of probing the network.
  - default GroundingDINO to CPU, matching the founder note that the Apple GPU path is unstable here.

### Verified
- Unit: `.venv/bin/pytest tests/unit/test_store.py -q` -> `1 passed`.
- Syntax/import check: `py_compile` passed for the new store files, eval harness, and `instance_perceive.py`.
- Retrieval proof on a real derived corpus:
  - Ingested `data/phone_captures/gt_desk/kf_memory.json` into `/private/tmp/gt_desk_store.sqlite3`.
  - Result: `2` observation nodes, `9` entity nodes, `10` links.
  - `search("Nutella jar")`, `search("Pringles")`, `search("Starbucks")`, `search("Adidas")` all returned the expected entity slice from the store.
- First scored number through the new harness:
  - Command: `.venv/bin/python evaluation/annotate_live.py --store /private/tmp/gt_desk_store.sqlite3 --annotations data/phone_captures/live/ground_truth.json --reasoner heuristic`
  - Result: answered rate `27.3%` (`3/11`), correct rate `0.0%` (`0/11`), confident-wrong rate `9.1%` (`1/11`).
  - Interpretation: the harness is working and the honesty floor stayed under the `10%` hard limit, but this fallback corpus is not aligned enough with the 11-question shelf GT to be a meaningful product number.
- Existing prior live number still on disk for reference:
  - `data/phone_captures/live/eval_results.json` = `45.5%` correct (`5/11`), `9.1%` hallucination (`1/11`).
  - This is NOT the new store number; it is the old brain-path reference baseline.

### Blocker
- Raw 25-frame shelf ingestion could not be completed from this Codex sandbox.
- Two concrete causes:
  - localhost calls to Ollama from `exec_command` are denied (`PermissionError: [Errno 1] Operation not permitted` on `http://127.0.0.1:11434`).
  - the raw-frame perception path aborts inside a native MLX/Metal dependency before usable output is produced (`NSRangeException` from `libmlx.dylib`) even after forcing GroundingDINO to CPU.
- Net: the clean store spine is built and verified on derived capture, but the intended raw-shelf proof must be run on the host by the founder/Overall Chief outside this sandbox.

### Next
- Run `ingest_validated_shelf(...)` on the host `.venv` where Ollama and the native perception stack are allowed, then score `evaluation/annotate_live.py` against `data/phone_captures/live/ground_truth.json`.
- Once that host run exists, keep the same store DB and move directly to:
  - sleep/link authoring on top of the store.
  - the agentic reasoner over `search / neighbors / get_abstractions / read_observation`.

---

## SPRINT UPDATE — 2026-06-27 (Truth Surface + Store Wiring)

### Built
- Extended the new `src/trace_memory/store/` spine instead of creating a second store:
  - retrieval now reports whether it is using the sentence-transformer path or the lexical fallback.
  - added public abstraction wrappers plus lightweight store counts for health surfaces.
- Added a first local agent loop under `src/trace_memory/brain/agent.py`:
  - returns `{answer, evidence_chain, confidence, refused, retrieval_mode}`.
  - starts with one cheap retrieval pass and only expands when the quick path cannot answer.
- Added a first conservative sleep pass under `src/trace_memory/store/sleep.py`:
  - only writes derived abstractions and same-entity links for exact repeated clusters.
  - never mutates observed rows.
- Wired `scripts/trace_brain_server.py` into the store:
  - every captured derived record now also writes a store observation into `<moment>/trace_store.sqlite3`.
  - instance-graph output now writes entity/summary observations plus graph links instead of staying sidecar-only.
- Extended the founder-facing truth surface:
  - `/ops.json` and `/engine.json` now expose service health, latest store snapshot, live eval artifact state, and store-proof artifact state.
  - `/ops` renders that truth surface, including brain/cockpit/eval-worker health and whether a real store exists yet.
- Added `evaluation/run_store_shelf_proof.py`:
  - one command ingests the shelf corpus into a store, runs proof queries, scores annotations, and writes `ops/cockpit/store_ingest.json`.
- Updated `evaluation/annotate_live.py` to publish its latest summary to `ops/cockpit/annotate_live.json`.
- Updated `scripts/trace_supervise.sh` so the supervisor targets the real founder cockpit on `:8799` instead of the legacy ops cockpit on `:8788`.

### Verified
- Focused test gate:
  - `.venv/bin/pytest tests/unit/test_store.py tests/unit/test_agent.py tests/unit/test_sleep.py tests/test_trace_brain_server.py tests/test_cockpit_rich.py`
  - Result: `9 passed`.
- Cockpit-specific rerun after the health-surface changes:
  - `.venv/bin/pytest tests/test_cockpit_rich.py`
  - Result: `3 passed`.
- Live founder surface payload served in-process:
  - `/ops.json` reports `brain=healthy`, `cockpit=healthy`, and includes `truth_surface.artifacts.latest_store`.
  - `/engine.json` exposes `runtime.truth_surface` and the live44 state for the same page.
- Capture -> store wiring test:
  - a `_capture(...)` call now produces a real `trace_store.sqlite3` with an observation row, not just `kf_memory.json`.

### Current Reality
- The cockpit code is fixed and the payload is correct, but keeping `cockpit_ask_server.py` alive as a detached background process from this tool environment is still flaky.
- In an attached session, `:8799` serves correctly and the new truth payload is present.
- The new supervisor target is in place so host-side restarts point at the correct cockpit path.

### Next
- Run `evaluation/run_store_shelf_proof.py` against the real 25-frame shelf corpus on the host-local stack so the cockpit can show the first real store-proof artifact.
- Then run `evaluation/annotate_live.py` on that store-backed shelf DB and surface the answered/confident-wrong numbers on `/ops`.
