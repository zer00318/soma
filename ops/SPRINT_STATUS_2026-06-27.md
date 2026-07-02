# SPRINT STATUS — 2026-06-27 (evening) — Chief executing
*Real, verified state. Deadline Wed 2026-07-01. Goal = WOW investor demo (both digital + physical pillars).*

## ✅ BUILT + VERIFIED THIS SESSION — the DIGITAL-LIFE pillar (the demo unlock)
**`scripts/screen_capture_daemon.py`** — Mac screen-record → Apple Vision OCR → store → delete image.
- Proven end-to-end: captured the real Mac screen, OCR read it VERBATIM (Brave URL, YouTube title +
  cast, comments, menu bar, date/time). Agentic reasoner then answered:
  - "What browser do I use mainly?" → **Brave Browser** ✓
  - "What was playing on YouTube?" → **"Mammootty Latest Suspense Thriller Movie | Derick Abraham |
    Anson Paul | Kaniha | Tarushi"** ✓ (verbatim)
  - "Was there a dog on my screen?" → honest refusal ✓
- Running 24/7 (detached, pid logged to `/tmp/trace_screen.log`), store `data/trace_store.sqlite3`.
- Privacy: raw screenshot deleted immediately after OCR; only derived TEXT persists (moat holds).

## THE DECISIVE EXPERIMENT (founder's real capture + 15 questions)
Founder captured his room (~few min) and asked 15 Qs. Findings (honest):
1. **No video recorded** — the full-video feature produced NO file (broken, 2nd time).
2. **Catastrophic sparsity** — only ~5 frames saved from a multi-minute session.
3. **Camera-films-screen CANNOT read screens** — proven: enlarged the laptop screens, YouTube
   title / chat messages / read receipts are below the resolution+focus floor. The info is not in
   the pixels. → the entire digital-life question class is UNRECOVERABLE by camera.
4. Physical objects ARE recoverable from the clean frames (rings worn ✓, orange paprika Pringles on
   the bed ✓, black bag ✓, ~2 suitcases ✓, nutella+pesto ✓) — live model mislabeled them
   ("Walkman","scallops") but the pixels are clean → strong re-perception recovers them.
- Scorecard: ~5/15 answerable even with a perfect reader; EVERY digital-life Q failed via camera.
- **Conclusion → the digital pillar MUST be screen-record, not camera. Built it (above).**

## REASONER + STORE — VERIFIED GOOD (not the bottleneck)
- gemma RAG reasoner over the store: ~80% correct on matched presence/refusal GT, near-zero true
  hallucination ("pringles?"✓ "pesto→Barilla"✓ honest refusals on bicycle/dog/banana✓).
- Store: sqlite + sentence-transformer retrieval + graph links. Works.
- Known weaknesses: JSON output truncation (tighten contract), no count path yet, occasional ramble.

## DECISIONS LOCKED (founder, this session)
- BOTH pillars: screen-recording (digital) + physical objects. BOTH capture fixes: dense frames +
  fix video, in parallel. Demo fully-live in founder's own space; investors ask anything; honest
  floor <10% wrong.

## NEXT (priority order)
1. **Unify the store**: ingest physical capture (re-perceived strong) into `data/trace_store.sqlite3`
   alongside screen obs → one memory the reasoner answers across (digital + physical).
2. **Reasoner hardening**: strict short-answer JSON contract; count path via world-binder; port the
   gemma reasoner into `brain/agent.py` as the single runtime path.
3. **Capture fixes (iOS, parallel)**: dense frames (2-5/s reliable) + debug the broken video upload.
4. **Cockpit overhaul** on the real numbers (digital pillar live, screen-obs count, the 15-Q
   scorecard, reasoner %).
5. **Frontier-text runtime** wired as the demo reasoner (gemma is the dev/eval fallback).

## SERVICES RUNNING
- Brain server :8765 (pid was 17592). Screen daemon (pid 48291). Ollama gemma 12b/27b + bge-m3.

---

## MILESTONE — 2026-06-27 night (Chief, local-LLM-driven session)
Founder directive: "delegate to local LLMs, make one thing do the cockpit, see what's wrong with
capture then put local LLMs to fix that too, chill as much as you can." Done:

### ✅ PHYSICAL-PILLAR CAPTURE FIX (offline dense perception) — `scripts/video_perceive.py`
- Root cause of sparsity (diagnosed in code): the live path perceives only the LATEST streamed
  frame per moment and DROPS the backlog (brain `trace_brain_server.py:254-256`), gated by gemma
  throughput → ~0.44fps → ~5 frames per multi-minute session. Real-time drop is by design for live.
- Fix (founder's foundation-up order): perceive a SAVED video OFFLINE at any density, free of the
  real-time drop. gemma3:12b-vision does all perception (`mac_vision_perceive.perceive_frame_b64`).
- **MOAT-CLEAN by construction:** frames decoded + JPEG-encoded + base64'd IN MEMORY, never written
  to disk; only derived TEXT persists into the unified `data/trace_store.sqlite3` (source=`phys_video`).
- **VERIFIED on real footage** (`data/walks/IMG_4045.MOV`): writes timestamped physical observations
  (reads laptop screens, counts items, blur-gated via in-memory Laplacian var). ~13s/frame.
- This is the template the phone .mov will feed once on-device save is fixed. Delivers NEXT #1
  (unified store: physical + digital in one memory the reasoner answers across).

### ✅ COCKPIT OVERHAUL (one 24/7 local job owns the truth) — delivers NEXT #4
- `scripts/cockpit_updater.py`: runs 24/7 (`nohup caffeinate`), recomputes REAL numbers each cycle
  (store counts by source, daemon liveness from the process table, pillar status, build-order
  progress), gemma writes one honest status line (fail-soft, never blocks the GPU). Writes
  `ops/cockpit/cockpit_state.json`.
- `ops/cockpit/cockpit_true.html`: glanceable true story (two pillars, build-order foundation-up
  progress, honest reasoner %, verified-vs-not, daemon lights). Served by the live cockpit server at
  **`/true`** + `/true.json` (added routes in `cockpit_ask_server.py`). No hand-editing.

### 🔬 iOS CAPTURE DIAGNOSIS (for the next coder — Swift fix not built this session)
- **"No video file, twice" root cause:** `VideoRecorder` only FINALIZES on `scenePhase==.background`
  (`FastVLM App/FastVLMApp.swift:24-27`); `finishWriting` is async inside a background task. If the
  app is killed (swipe-up) or not cleanly backgrounded, the writer never finalizes →
  `trace_capture.mov` stays an unreadable stub. **Empirical proof: the Mac has NEVER received a
  `trace_capture.mov`** (only old June-11 walk fixtures exist). The frame TAP is correct
  (`Video/CameraController.swift:254` feeds every sample buffer).
- **Fix spec:** (1) add an explicit record START/STOP tied to UI that finalizes on STOP, not only on
  background; (2) periodically flush segments (e.g. every 10–30s, `AVAssetWriter` segment files or a
  re-open loop) so an app-kill loses at most one segment, not the whole session; (3) make
  `finishAndUpload` await `finishWriting` completion within the background task before ending it.
- **Phone-screen capture (NEXT):** mirror the Mac screen daemon for the phone's digital life
  (ReplayKit / broadcast upload extension → OCR → store → delete), same moat discipline.

### SERVICES NOW RUNNING (this session)
- `cockpit_updater.py` (24/7, pid logged `/tmp/trace_cockpit_updater.log`).
- `cockpit_ask_server.py` relaunched with `/true` route (`/tmp/trace_cockpit_server.log`).
- `video_perceive.py` one-shot backfilling ~25 phys obs from a real walk into the live store.
- Cockpit true status: **http://127.0.0.1:8799/true** (LAN-reachable for the founder's phone too).

---

## MILESTONE — 2026-06-27 late (founder cockpit + local-LLM AGENT TEAM)
Founder: "cockpit is shit — I want live numbers, moving progress, see whether the local LLMs are
working + what they're working on, subfeature decomposition, plans/todos/ETAs, trackers. Create
local-LLM agent teams, delegate, shatter the bar." Built + VERIFIED:

### ✅ LOCAL-LLM AGENT TEAM — `scripts/agent_orchestrator.py` (24/7)
Five named agents the founder can watch work. M2 OOMs on concurrent gemma → GPU agents share a
mutex (most-overdue-first scheduler so the fast Perceiver never starves the others); the no-GPU
Metrics agent runs truly in parallel, so there is always real concurrent activity.
- **Metrics** (no GPU): live store counts, obs/min rate, daemon lights — every 5s.
- **Perceiver** (gemma3:12b-VL): continuously backfills PHYSICAL obs from the walk videos (the bar
  literally moves — phys_video climbed 12→37+ live). In-memory, 0 frames to disk.
- **Evaluator** (gemma3:12b): asks the reasoner sample Qs over the store → answerability (verified:
  "What laptop did I use? → MacBook", correct from real obs).
- **Planner** (gemma3:27b): nudges `project_plan.json` progress from real store signals each cycle.
- **Scribe** (gemma3:12b): writes one honest narration sentence from the real numbers.
Outputs: `agents_live.json` (per-agent status+heartbeat+task+done-count), `agent_activity.jsonl`
(live feed), `cockpit_state.json` (numbers), `project_plan.json` (decomposition, Planner-refreshed).

### ✅ FOUNDER DASHBOARD — `ops/cockpit/founder_dash.html` @ **/dash** (+ /dash.json merged)
Glanceable, auto-refresh (3s), lots of motion: count-up numbers (nodes, capture rate/min, reasoner
%, pitch-day countdown), animated sheen progress bars (overall + per-pillar), the agent-team panel
with pulsing heartbeat lights + each agent's current task + done-count + staleness, a streaming
live-activity feed, and the full build decomposition tree (pillars → features → tasks with
status chips / plan / owner / ETA). Served by `cockpit_ask_server.py` (new `/dash`, `/dash.json`).
**Open: http://127.0.0.1:8799/dash**

### SERVICES RUNNING (24/7)
- `agent_orchestrator.py` (the team) — `/tmp/trace_orchestrator.log`.
- `cockpit_ask_server.py` (serves /dash, /true) — `/tmp/trace_cockpit_server.log`.
- `screen_capture_daemon.py` (digital pillar), `trace_brain_server.py` (brain).
- Standalone `cockpit_updater.py` RETIRED (subsumed by the orchestrator's Metrics agent).

### STILL NEEDS A CODER (gemma can't write Swift/complex features reliably)
iOS on-device video save (root cause found), phone-screen capture, inject-layer wiring over the new
store, strict reasoner answer contract + count path, frontier-text demo reasoner. These are the
"Coder"-owned tasks in the decomposition.

---

## MILESTONE — 2026-06-27 night+ (Coder-owned tasks)
Founder: "do the Coder-owned tasks now, least tokens." Triaged by demo-leverage × verifiability.

### ✅ #4 Reasoner: strict terse contract + count path — VERIFIED on live store
`src/trace_memory/brain/agent.py`. Shared `_contract_prompt` (<=12-word grounded answer, honest
refusal, stand-ground on false premise, strict JSON) used by every backend. Root-cause fix: the
count/exists/attribute heuristics only scanned `entity` nodes, but the new store has only
`observation` nodes -> they always refused. Now exists/attribute fall back to observations; count
stays entity-only (true individuation) and FALLS THROUGH to the LLM instead of refusing when no
entities exist. Verified: "how many laptops" -> "two laptops" (grounded); "is there a backpack" ->
Yes; "unicorn?" -> no hallucination (honesty floor held). test_agent.py green.

### ✅ #5 Frontier-text demo reasoner — VERIFIED (plumbing + graceful fallback)
`reasoner="frontier"` (or wire via runtime) -> Anthropic Messages API over the SAME evidence +
contract. Reads `ANTHROPIC_API_KEY` + `TRACE_FRONTIER_MODEL` (default claude-sonnet-4-6) at call
time; no key -> falls back to local gemma, never crashes. Demo day = set the key + flip the mode.
Verified: no-key path falls back cleanly to "MacBook". (Live API not exercised — conserves tokens.)

### ✅ #1 iOS on-device video save — WRITTEN, ⚠️ NEEDS DEVICE BUILD TO VERIFY
`trace-native-fastvlm/Video/VideoRecorder.swift` rewritten to SEGMENT-ROTATE: a timer finalizes +
uploads a complete ~20s .mov every 20s and starts a fresh one, instead of one finalize-on-background
that in practice NEVER delivered a file. App-kill now loses at most one segment. Moat: each segment
deleted locally after upload. Wired in `FastVLMApp.swift` (configure on .active, final flush on
.background). Mac `/debug/video` already saves each upload uniquely -> `video_perceive.py` consumes
them (loop closed in design). CANNOT verify without an Xcode build on the iPhone 17.

### ⏸ DEFERRED (honest — heaviest + unverifiable here, lowest marginal demo value)
- #2 Phone-screen capture (ReplayKit broadcast extension): a whole new iOS target; can't verify
  without device; Mac screen daemon already covers digital life. Build when on the iOS track.
- #3 Inject layer over the new store: real refactor; the reasoner already answers ~80% directly,
  so marginal for the demo. Do after the demo or if answer quality stalls.
