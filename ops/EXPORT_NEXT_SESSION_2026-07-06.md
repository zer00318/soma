# EXPORT — continue here (authored by Fable 5, 2026-07-06, final Fable day)

READ ORDER for the next session: this file → `ops/CANONICAL_SPEC.md` (v3, still law)
→ `ops/packets/INDEX.md` → `ops/packets/P34-context-model.md`. Memory index
(`~/.claude/projects/-Users-zer00-Documents-VLM/memory/MEMORY.md`) carries the same
truth compressed. Trust code+tests over any doc that disagrees.

## 0. THE DRAWING BOARD (founder re-founding, 2026-07-06 evening — supersedes P41-style
## surface work; this section is the assignment)

Founder verdict after using the real product: timeline BAD, and every fix so far
tunnel-visions into the surface last touched. VLM/OCR/ASR **are not the app — they are
sensors**. The re-founded architecture, in his words distilled:

1. **PROGRESSIVE DEEPENING (the stare economy).** When the camera stares at a static
   scene (founder working at his laptop), each frame must yield MORE information, not
   the same "laptop, person" again: accessories, identifying marks, eye colour, wear,
   text on objects — arbitrarily deep detail ("individual hair follicles" as the joke
   limit). Perception budget is an ATTENTION ECONOMY: novelty → breadth pass (what's
   here); stasis → depth pass (mine the least-mined entity one level deeper).
   Mechanism: a per-(scene, entity) MINING LEDGER — depth level, attributes already
   extracted, open questions — so each static frame CONTINUES where the last stopped.
   The VLM becomes a targeted tool ("describe the accessories on the person in this
   crop"), never a describe-everything loop. This kills the 2756-identical-rows
   pathology at the source.

2. **BRAIN-BEFORE-BRAIN (the Nodes system).** The LLM is the MOUTH, not the brain —
   token-limited, puny, for narrating answers only. The actual brain is the memory
   structure that feeds it: ENTITY-CENTRIC NODES (person/object/site/place with
   stable identity), each accumulating attributes (with provenance, grade, confidence,
   time), linked by relations (containment, adjacency, ownership, state), consolidated
   by sleep. Questions become graph traversals producing CONTEXT SLICES; the LLM only
   narrates the slice. Existing assets converge here — do NOT rebuild from zero:
   memory_nodes/memory_links (store), track/anchor identity (P10-12), containers.py,
   episodes/digests, slices.py are all Nodes-system organs already; what's missing is
   the ENTITY-CENTRIC layer: one node per THING that persists across observations,
   instead of row-per-observation with identity implicit.

3. **TWO APPS.** The current phone app = CAPTURE ONLY (sensor input; keep the engine
   room). A NEW companion app = the ask + show surface — what the eyewear product's
   real companion app looks like (chat with narration via /ask/stream, timeline v2
   fed by Nodes not raw episodes, review cards P42). Build it as a separate target
   (same project, new app target e.g. "Trace Companion") talking only to the hub.

Execution order (N1 LANDED same day — commit 7552597):
  N1. ✅ DONE: store/nodes.py NodesBuilder — entity_node rows (object/place/site/app),
      attribute accrual + open_questions (mining-ledger seed), located_at links,
      KNOWN THINGS block in the reasoner prompt, GET /nodes, nightly-wired.
      LIVE: 91 objects/6 places/4 sites/54 links; exposed 30+ fragmented person
      instances (P12 global-identity work, now measurable) + audinifer.com.
      6/6 synthetic-day contracts; battery held. Fragment AGGREGATES landed (4 live: person@RB19 = 27 fragments/3955 sightings as ONE honest card, distinct-count stated unresolved). NEXT OWNER: real identity merge (P32), site-node attribute accrual (titles watched), nodes-first retrieval.
  N2. ✅ MAC HALF DONE (same day): scripts/mining_ledger.py (pure: static-tick
      counter, least-mined-tile rotation, per-scene mined-set, budget cap, novelty
      reset) + daemon depth passes (rolling 1-frame buffer -> tile crop-zoom OCR ->
      ONLY novel text emits as SCREEN-DEEP rows w/ mining_depth provenance).
      LIVE PROOF: static Claude window yielded +12 new texts across 6 passes incl.
      small text breadth missed. REMAINING N2: the PHONE twin — EnrichmentScheduler
      .swift drives targeted VLM crops per track from node open_questions (fetch via
      GET /nodes; prompts like 'describe accessories of the person in this crop');
      attribute answers post as enrichment rows; NodesBuilder accrues them nightly.
  N3. Companion app skeleton (ask chat + nodes-browser instead of the bad timeline).
  N4. Frame-gold eval loop as the only judge (never authored batteries — LAW).

## 1. WHAT EXISTS AND WORKS (verified today, 2026-07-06)

- **Honesty moat**: canonical battery 96.7 / 100 / CONFIDENT-WRONG 0 / parity 100 —
  run after EVERY brain/store change (`evaluation/run_canonical_battery.py`, exit-1
  gate). 344 pytest green. The Leash (`evaluation/leash.py`): digital moved 0→THIN
  yesterday; motion/sound/temporal still STARVED.
- **P-STAB CLOSED**: 12h soak, zero crashes (July-4 MLX SIGABRT gone; CrashBlackBox.mm
  armed for life — any C++ terminate writes type+what() to app container
  Documents/crash_blackbox.log). All deaths were lock→reap lifecycle (capture stops on
  lock, iOS reaps ~3min later) — product handles via honest gaps; carry protocol needs
  foreground+unlocked. Soak rig: `scripts/soak_stability.py` (probe-error sentinel,
  auto-relaunch, evidence pull).
- **Capture, Mac (digital pillar)**: `scripts/mac_screen_daemon.py` running — OCR w/
  geometry → window attribution → region bands; AX SEMANTIC channel LIVE
  (`scripts/ax_adapter.py`, grade=authoritative, container_path
  display/app/tab(url)/role-path); active-tab URL via AppleScript; privacy blocklist
  (config/privacy_blocklist.json) enforced at capture + `scripts/purge_private.py`
  retroactive (25 rows purged on founder's plant-test). FRAME GOLD: 1 frame/5min
  survives to evaluation/frame_gold/ (8 so far) — THE eval substrate.
  `scripts/ax_corpus_collector.py` gathering raw AX trees (12 so far) for the
  grammar-induction spike (untested — next session may run or drop it; Nodes first).
- **Capture, phone**: app streams detector/VLM/OCR/ASR/depth to hub; P10 anchors,
  P11 fingerprints, P12 Mac-core identity live. ARKit scene semantics (plane
  classification) NOT yet extracted — that's the phone's semantic-first move (twin of
  AX), folds into N1/N2.
- **Sleep organs (nightly 03:30 via keepalive, ran clean unattended last night)**:
  SleepConsolidator → EpisodeBuilder (measured thresholds, honest gaps, container
  labels) → DigestBuilder (cited bullets, thin-day honesty) → battery gate.
  `scripts/nightly_sleep.py`.
- **Brain**: S1 grounding gate + ~10 deterministic owners (they stay ONLY as honesty
  gates; the Nodes system should absorb answering); pyramid router (digest answers
  "what happened yesterday" <2s); slices.py context scenes (era boundary: rows before
  2026-07-05 22:30 were flattened at birth — structure exists only after); ask-v2
  narration events + hub GET /ask/stream (SSE).
- **Hub** (`scripts/trace_hub.py`, :8765, keepalive `scripts/run_hub_keepalive.sh`):
  /capture/perception, /ask, /ask/stream, /episodes, /digest (16ms/3ms), /status,
  /health; Bonjour zero-config.
- **Synthetic-day harness** (`tests/unit/test_synthetic_day.py`): generates a day with
  known truth, runs FULL pipeline, 5 contracts; already caught+fixed one firm-wrong
  (unknown-cell simultaneity now hedges [1,2] — individuate.py liberal pass).

## 2. OPERATIONAL RECIPES (hard-won; do not re-derive)

- **Deploy**: xcodebuild -project trace-native-fastvlm/FastVLM.xcodeproj -scheme
  "FastVLM App" -destination 'platform=iOS,id=00008150-001460D83686401C'
  -allowProvisioningUpdates -configuration Debug -derivedDataPath build/dd build →
  devicectl install --device D3A506B2-8923-5313-B8A3-FF769ABBA228 → launch
  de.zer00.trace. **If install wedges at "Acquired usage assertion": kill the
  user-level CoreDeviceService (pgrep -fl CoreDeviceService) — respawns, install
  then takes ~60s.** Crash/hang reports pull WITHOUT founder:
  `devicectl device info files/copy from --domain-type systemCrashLogs` (works locked).
- **Hub restart**: kill `lsof -tiTCP:8765 -sTCP:LISTEN` PID (NEVER `pkill -f
  trace_hub` — kills the keepalive wrapper too); keepalive relaunches in ~10s.
- **Xcode project**: objectVersion 77 synchronized groups — new files in
  "FastVLM App/" auto-compile, no pbxproj edits. Debug binary = .debug.dylib.
- Background daemons run via nohup+disown; NEVER as harness background tasks (10min
  cap kills them). Soaks: infrastructure FROZEN for the duration.
- pytest = `.venv/bin/python -m pytest -q` (317→344 over this window; keep green).

## 3. FOUNDER LAWS (violations get called out — all learned the hard way)

- NO authored eval batteries — frame-gold only (frames are ground truth; questions
  derived from frames at eval time, blind to store).
- NO bandage fixes: if receipts contain the answer but the answer is wrong, the defect
  is REPRESENTATION, not the reasoner. Never add owner N+1 for a phrasing family.
- Thresholds are measured, not spec'd; firm claims WITNESSED, never inferred;
  ambiguity → honest RANGE; confident-wrong = 0 is the hard gate.
- Readiness math: never count plumbing as product. Current honest number: **~55%**,
  where the missing 45 = Nodes brain + progressive deepening + companion app +
  motion/sound channels + 3-day proof.
- Every close-out ends with NEXT (what I do) / YOU (founder's exact required actions);
  sweep stale background tasks before ending.
- Founder granted full Mac sovereignty (TCC, settings, computer-use OK — announce use).
- L1: frames die after perception (frame-gold sampling is the owner-consented
  exception); no frame/audio leaves the devices, ever.

## 4. RUNNING RIGHT NOW (survives this chat)

- hub keepalive (caffeinate; nightly 03:30) · mac_screen_daemon (OCR+AX+gold) ·
  ax_corpus_collector (45s) — all nohup, logs in /tmp/trace_*.log.
- Phone: timeline build installed+launched (timeline judged BAD — do not iterate it;
  the companion app replaces it).
- Done-bar unchanged: 3 real days + founder blind (frame-gold) battery ≥75% / 0
  confident-wrong.
