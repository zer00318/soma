# SOMA supervisor handover — respawn protocol

> Maintained continuously per user directive (2026-06-10). When a session
> hits its limit, a fresh chat resumes from THIS file + the auto-memory at
> `~/.claude/projects/-Users-zer00-Documents-VLM/memory/`. Update this doc
> at every meaningful state change, BEFORE the limit hits.

## ★ LATEST 2026-06-14 eve — THINKING ASSEMBLER + OBJECTIVE GOLD SCORING (read first) ★

MODE: orchestrate via background Workflows; local LLMs do the LABOR (qwen drafts code,
Qwen-VL/gemma/whisper do inference); agents integrate; loop toward the prototype (see
memory feedback-delegate-local-llms, UPDATED). Loops die at the usage limit — CODE
survives on disk; commit at every state change.

SCOREBOARD UNBLOCKED (efd4265): assembler was 91s/question because answer_assembler ran
a redundant 2nd verify_grounded pass over the whole dossier (+ cold model load) — cut it
(ASSEMBLER_GROUNDING_GATE=False; leash is in the prompt). Now ~5s warm. evaluation/run_live.py
= RESUMABLE eval (per-question JSONL checkpoint + live status), so a kill never loses a run:
just re-run the same command to resume. Use it (not run_ras) for the objective number.
IN FLIGHT: workflow wrfym41js building attributes-catcher (build_attributes.py -> attributes.json:
bag colour/zip, cable state) + sleep-binder (build_sleep_bind.py -> bound_memory.json: cross-link
Meißner iceberg mural, consolidate ~5 posters), integrate into the assembler dossier, then run_live.

OUTDOOR-WALK NUMBER arc (engine=ask_home, gemma3:12b, SAME 25 blind Qs):
-8 (lossy baseline) -> -12 (leaky keep-words) -> 0 (provenance leash) -> +4 (grounding
gate) -> committed specialists landed agent-judged ~+32 (OPTIMISTIC, unverified). The
honest objective number is being recomputed NOW (see SCORING below) — do not quote +32.

ARCHITECTURE NOW (all committed, scripts/ask_home.py self-test PASS):
- **Thinking assembler** (answer_assembler, the founder's "congregation of all channels"):
  gathers EVERY channel's text into one dossier and REASONS over it, cited, keeping the
  provenance leash. PRIMARY answerer; legacy per-intent routes are fallback.
- Channels feeding it: semantic_index.py (bge-m3 multilingual embeddings — fixed
  molecule<->Molekül<->molecular), counting_specialist.py (distinct murals, not lossy
  dedup), temporal_specialist.py (gap-tolerant time-in-view, hedged), screen_reader.py
  (full-res re-OCR of laptop screen -> screen_memory.json), audio_events.py +
  build_audio_events.py (sound-event LOG from the wave, NO transcription, NO raw-wav at
  answer time), build_micro_details.py (per-region close reads -> micro_details.json).
- Earlier gates still in place: audio gate, spatial refusal, reading leash, grounding gate.

OBJECTIVE SCORING (no more lead hand-judging — this was the bottleneck):
- evaluation/ras/walk_outside_20260614.gold.json = FROZEN, FOUNDER-CONFIRMED key.
  Surprises baked in: Q18 bag=BLUE (not white), Q9/Q10 other-poster=Meißner ICEBERG
  mural, Q16 ~5 posters, Q17 zip OPEN, Q19 iPhone NOT cabled, Q22 chat='Audio
  transcription and video critique', Q23 badge=yellow, Q24 there WAS an unsent draft.
  Q8 & Q11 unanswerable (no head-pose) -> correct ONLY if engine refuses.
- evaluation/auto_score.py: gemma judge over the key -> hard_ras (non-pending),
  hallucination, full_ras. RUN: `python3 evaluation/auto_score.py --gold
  evaluation/ras/walk_outside_20260614.gold.json --answers <run.json>`.

RE-SCORE recipe (objective): run_ras.py ask --engine ask_home --questions
evaluation/ras/walk_outside_20260614.txt --memory
data/walks/walk_outside_20260614/memory/world_memory.json --out /tmp/x.json ;
then auto_score.py --gold ...gold.json --answers /tmp/x.json.

NEXT after the objective number lands: fix whatever it exposes; then the founder's
LAPTOP/SCREEN-CAPTURE video as the next eval substrate (most controlled; lead can be the
ceiling oracle). REAL audio-event proof needs an audio-rich walk (this one is near-silent).

## Respawn instructions (read first in a new chat)

1. Read this file fully, then `ops/enrichment_scheduler_design.md`.
2. Working repo: `/Users/zer00/Documents/VLM` (branch `main`, commit directly).
   An agent worktree may exist under `.claude/worktrees/` — IGNORE it, work in
   the main checkout. Shell cwd resets between calls; always `cd` explicitly.
3. Run `python3 -m unittest discover -s tests -p "test_*.py"` (expect all pass)
   and `python3 evaluation/run_north_star.py` (expect 1.00) before changing code.
4. Check TaskList for open tasks; current priorities are below.
5. User = project creator (Garching), is the physical tester. One compact
   physical test at a time. He prefers empirical verification over claims —
   run it, measure it, show the numbers (see memory: feedback_system2).

## ★ COMMITTED PLAN 2026-06-13 ~22:30 — THE ONLY THING THAT MATTERS NOW (read first; supersedes all object-map/3D/CLIP work below) ★

Founder reframed hard: SOMA = no-raw-storage perception-to-text INPUT layer. GOAL = record a session, ASK questions later, ANSWER the founder's real 25-question blind battery (evaluation/ras/walk1.txt). Prev = RAS -8. ROOT CAUSE of -8: frames were reduced to GENERIC object labels via known_object_labels ("text surface", "machine") and pixels discarded → could never read a poster/form/screen. See memory: project_feasibility_verdict (CORRECTED).

COMMITTED ARCHITECTURE (no more model-hopping; NO 3D, NO MobileCLIP/YOLO/FastVLM object-naming, NO audio for this battery): retrieval-augmented VLM over KEYFRAMES. video(+pose/GPS) → sharp keyframes → per-frame TEXT = {dense attribute-bearing caption || verbatim OCR} → store as graph_messages rows (media_kind='keyframe', JPEG path, NEVER via known_object_labels) → retrieve (existing context_bundle/search_messages_all grep, widened AND→OR for keyframe rows) → answer-time model reads retrieved text + actual JPEG pixels, refusal-default kept → run_ras.py scores SAME 25 Qs.

COMMITTED MODEL STACK:
- keyframes: scripts/walk_select_sharp_frames.py (+ target_fps 3→5, force-keep ≥12-OCR-char frames, motion-burst on sink/mirror/door). NOTE old walk_office_jun11.mov has NO pose sidecar → needs sharpness-only sampler.
- OCR: Apple Vision .accurate via ocrmac — INSTALLED + smoke-tested working 22:30 (py3.9 .venv). 1600px downscale, subprocess restart every ~200 frames (leak).
- caption: Qwen2.5-VL-7B-Instruct-4bit via mlx-vlm (mlx-vlm installed; WEIGHTS were NOT cached → downloading 22:30, /tmp/qwenvl_download.log). gemma3:12b (ollama, already local) = fallback.
- retrieval: reuse soma_hub graph_messages grep; NO embedder/vector-DB (overkill at 15-min scale).
- answer-time: LOCAL VLM default (Qwen2.5-VL / gemma3) — free/offline, honors "chill"; Claude-vision = optional CEILING test. (Workflow draft said Gemini 3 Pro — OVERRIDDEN, wrong for this setup/no key.)
- scorer: evaluation/run_ras.py UNCHANGED; SAME walk1.txt 25 Qs (apples-to-apples vs -8).

HONEST CEILING: ~+20 to +35, NOT the +60 pitch gate. EgoTextVQA tops ~33% frontier on egocentric scene-text; we win mostly on LARGE text. Tiny text (10th citation, tissue brand, form sigs) mostly misses; temporal/self-view (~5 Qs: washed hands, hesitated, headphones) a chest cam physically can't see → accept as neutral MISSES (firewall = 0 not -2). DO NOT overclaim +60.

BUILD PLAN (owner tags): 0[lead/local] re-score EXISTING walk_office_jun11.mov on new pipeline = clean software-only delta vs -8 (founder records nothing). 1[founder] optional better-framed proof capture in parallel. 2[local-llm qwen] ocr_pass.py. 3[local-llm qwen] caption_pass.py (Qwen2.5-VL, attribute-bearing, ≤128 tok, checkpointed). 4[lead] ingest_keyframes.py (text='caption||OCR' → graph_messages, media_kind='keyframe', NOT known_object_labels; widen retrieval OR). 5[lead] swap recall.py _llm_generate to read frames+text, KEEP refusal-default + citation gate (guard with test_grounded_recall/test_recall_provenance). 6[founder] run 25 Qs → verdict → score; ALSO text-only run to size the no-storage wall.

KEY RISKS: caption hallucination = the 'text surface' failure reborn (mitigate: keep verbatim OCR separate, prefer it for "what did it say", citation gate). Retrieval picking wrong frame (silent). Night-shift throughput on M2 Pro unmeasured (benchmark Qwen-VL sec/img before fixing frame density). Repo still full of old CLIP/3D path — keyframe content must NEVER route through known_object_labels or -8 returns in disguise.

EXEC STATE 23:10: COMPONENTS VALIDATED, CAPTURE IS THE WALL.
- ✅ Apple Vision OCR (ocrmac) binds+runs. ✅ Qwen2.5-VL-7B-4bit captions WORK and are accurate with attribute prose + ZERO hallucinated text (mlx-vlm 0.1.15 needs FIX: transformers defaults to fast Qwen2VL image processor → "Only PyTorch tensors supported"; fix = keep load()'s processor but set processor.image_processor=AutoImageProcessor.from_pretrained(MP,use_fast=False)). SPEED ~15s/frame at 1080x1920 full-res → MUST downscale / set max_pixels for throughput (a full day is infeasible at 15s/frame).
- ❌ DECISIVE FINDING: walk_office_jun11.mov is UNUSABLE. Sequential decode: 4.7min/1080x1920; back half (t≥142s) is BLACK (median sharp=1, 514/528 frames <5). The 50 SHARPEST frames have 0/50 with readable OCR text. Looked at them: the sharpest frames are the CARPET FLOOR, a radiator, and the founder's own shoes/knees. The chest-mounted phone was AIMED AT THE FLOOR; the posters/screens/forms/Julian/bikes were never in frame. -8 was overwhelmingly a CAPTURE-AIM failure, not a model failure. (This is why the eventual product is glasses = point-where-you-look; chest-mount points down.)
- PATH (flood-fill recompute): decouple "can software answer" (prove NOW with deliberately-AIMED stills) from "can a chest-cam capture while walking" (form-factor wall, later). Founder asked to capture 5-6 deliberately-aimed STILLS (poster/screen/form/labeled-object/person/bikes, steady, ~50cm) into data/walks/proof_stills/ + write 5-6 Qs. Then run OCR+caption+answer loop → first real cited answers.
- NEXT: (1) await founder aimed stills; (2) delegate ocr_pass.py + caption_pass.py (with the use_fast=False fix + downscale baked in) + ingest_keyframes.py to qwen; (3) run loop on stills → number; (4) THEN deliberately-aimed walk; (5) only later, the no-storage + walking-capture walls.

---

## SPRINT RESULTS (2026-06-13 ~01:30) — FIRST GROUND-TRUTH NUMBERS EXIST

THE NUMBER (evaluation/home_eval_20260612.md, commit a068e72): founder
deliberately cluttered his home, scanned 5 min, supplied 9 photos.
Device-world-only scoring: **precision 0.417, recall 0.244** (24 home
objects, 41 photo-truth objects). Correct anatomy captured: bed, blinds,
fan, laptop+stand, radiator, shelf, window, wallet. 14 phantom suspects
(NOTE: gemma photo lists aren't exhaustive — founder eye or the
on-device judge must confirm; judge had ~zero runtime at scoring).
31 missed, dominated by soft/deformable (clothes, blanket, towel,
socks) and containers (box, bag, suitcase) — CAPTURE side (saliency
proposals + dwell), vocab mostly covers them.

Sprint shipped (all committed): Codex brief 8 = phantom judge on-device
+ space data (w/h/support_plane/verified) through post→spatial_pose→
/api/world + "where is X" recall (live-verified: mouse answers with
coords+citation, d829fa3). qwen3-coder:30b first outing = world3d
SPACE renderer (extent boxes, resting snap, floor stems) + the photo
eval harness, 2/2 first-attempt (one list-vs-dict bug lead-fixed —
massive upgrade over qwen2.5's 4-7/file). Office world archived
(data/world_archive/), home mapped fresh, hub URL on home IP, legacy
garbage entities archived in DB (5 rows).

CONTAMINATION CAVEAT for next eval: /api/world merges live snapshot
with DB spatial_pose rows — office objects pollute home scoring. Score
against the DEVICE spatial_world.json until per-place frames exist
(schema bake list). Eval script default still hits /api/world.

NEXT LEVERS (in expected-yield order):
1. RECALL (0.24 → ?): more/better region proposals (saliency cap, grid
   density), longer scans, dwell guidance in the founder runbook.
   Codex brief 9 candidate.
2. PRECISION (0.42 → ?): leave phone scanning hours → phantom judge
   accumulates verdicts; then re-pull device world and re-score (free).
3. Per-place coordinate frames (office vs home) — unblocks clean evals
   and re-entry events per place.
4. Founder confirms/denies the 14 phantom suspects (2 min) → separates
   judge work from gemma's photo blindness.

Watchdogs: none armed at session end (sprint complete). Phone left
scanning at home on the stand.

## SPRINT RUNNING (fired 2026-06-12 ~22:30) — LEAD IS HIBERNATING

Founder directive: exponential sprint; lead preserves tokens (0% used at
start), wakes ONLY on watchdog reports; Codex budgeted; local LLMs +
founder do labor; HAIKU WATCHDOG AGENTS now AUTHORIZED by founder for
monitoring (update to the no-subagents law: cheap watchdogs yes, labor
agents still no).

In flight right now:
- CODEX: ops/CODEX_BRIEF_8_phantom_judge.md (P0 phantom judge per
  founder design — FastVLM 3-strikes-distinct-crops marks phantom,
  rehabilitation on success, never delete; P1 w/h/support_plane/
  verified through post→spatial_pose→/api/world; P2 "where is X"
  extractive recall intent). Result lands at
  ops/CODEX_BRIEF_8_phantom_judge_RESULT.md. Lead installs builds.
- NIGHT SHIFT (model upgraded qwen2.5→qwen3-coder:30b, line 44):
  S1 world3d v2 = render SPACE (extent boxes for desk/whiteboard-class,
  resting snap via support_plane/footprint, vertical stems to floor
  grid, phantom filter, verified underline) → S3 eval_room_photos.py
  (gemma vision vs /api/world → precision/recall + phantom_suspects)
  → S5 founder photos to data/gt_photos/ + phone re-arm. Gates
  NON-BLOCKING this run (Codex edits Python concurrently — lead judges
  suite on wake).
- WATCHDOG: haiku agent polls every 5 min (codex log/process, shift
  state, founder reply, pipeline freshness); returns = lead's wake-up.
- Phone relaunched into Spatial 22:29 (autoOpenSpatial).

WAKE CHECKLIST for lead (in order): read watchdog report → review
Codex commits (suite + north-star MUST be green before accepting P1/P2;
run them yourself) → review night-shift commits (qwen3's first outing —
judge quality, it replaced a 4-bugs/file model) → build+install Swift →
founder acceptance: world3d looks like SPACE, phantoms gone after a few
judge cycles, "where is the keyboard" answers on live DB → if photos
present: run scripts/eval_room_photos.py = the capture-precision
NUMBER → update gates_status.json, this doc, commit.

## FOUNDER VERDICT ON /world3d (2026-06-12 ~17:45) — NEXT SESSION'S WORK ORDER

Founder looked at the live world. His findings, verbatim spirit, in
priority order for the successor:

1. **PHANTOM OBJECTS are the #1 problem.** "It invented an iron board
   in my office. And many many more objects that are not there."
   MobileCLIP's low floors create objects that don't exist. Founder's
   own proposed fix = extend tier-2: FastVLM should JUDGE the predictor
   — not just relabel, but mark/retire phantoms. This needs a carve-out
   from the never-delete law: an object FastVLM repeatedly cannot see
   at its position (e.g., 3 strikes across distinct crops) gets status
   'phantom' — excluded from /world render and posts, NOT deleted
   (provenance stays, founder can audit). Wire counts into diag.
2. **GROUND-TRUTH IMAGES COMING:** founder will supply room photos next
   session. Build the eval: photos vs /api/world object list →
   precision/recall per word (gemma vision can do the cross-check;
   scripts/review_ground_truth.py is prior art). This becomes the
   capture-precision number on his progress scale.
3. **The world must BUILD SPACE, not just float words.** The desk word
   should LOOK like a desk — an extent-sized surface that keyboard/
   mouse/monitor/laptop/fan words REST ON (support relations).
   We HAVE w/h extent fields and supportPlaneID on device objects;
   render extent as translucent planes in world3d, snap supported
   objects onto their plane. (Founder's original 'ASCII world' vision —
   see SPATIAL DIRECTION section.)
4. **Vertical axis not legible:** view reads as x-y only — "which one
   is at the top and which at the bottom" is invisible. Make height
   obvious (y-axis grid lines, floor shadow lines, or slight camera
   pitch default).
5. **Orientation is GOOD** — founder anchored the window mentally and
   the relative layout matched reality. Keep the genesis-frame
   approach; don't churn it.

Session shutdown state (~17:45): all lead monitors stopped;
qwen3-coder:30b pull INTERRUPTED partway (ollama resumes on next
`ollama pull qwen3-coder:30b` — finish + eval before promoting).
Capture stack (hub :8765, dashboard :8777 incl. /world3d, cockpit
:8788, cable-sync 120s) LEFT RUNNING with phone scanning on the stand;
`pkill -f soma` quiets the Mac if founder wants. Suite was 123/123 +
north-star 1.00 at session start; Swift work since is device-verified
(relabels live), Python untouched after the dashboard route.

## BLOCKER RESOLVED 17:30 — TIER-2 CONFIRMED CORRECTING NAMES LIVE

- The 17:12+17:18 relaunches took: device diag (post-truncation, pulls
  reliable again) shows the hardened verifier RELABELING CORRECTLY at
  15:13Z: desk→keyboard ("image shows a desk with a keyboard...") and
  power strip→cable x2 ("main solid object is a black cord" → cord →
  canonical cable). Vocab-gated prose extraction + canonicalization
  working as designed. 59 verification lines on device.
- So: scanning LIVE, verifier LIVE, dedupe build LIVE. Successor's
  verify step: /api/world fresh snapshot with dups=NONE garbage=NONE,
  then /world3d is the founder demo. Founder notified (desktop push +
  channel stand-down).
- The section below records the (now-resolved) diagnosis trail — keep
  for the devicectl gotchas, ignore the blocker itself.

## LIVE BLOCKER AT SESSION END (17:25) — read before anything else (RESOLVED, see above)

- Spatial scanning STOPPED at 17:05 local (last spool packet 15:05:19Z)
  and devicectl relaunches do NOT reopen Spatial mode despite
  autoOpenSpatial=true. Strong suspect: a blocking on-screen state after
  the container reset (dialog or FastVLM model re-download — weights
  live in the container that the install wiped). devicectl cannot
  screenshot; FOUNDER SCREEN-CHECK requested (his channel + cockpit).
  His reply lands in /tmp/soma_founder_reply.txt.
- The stuck 265-packet spool was hand-replayed (clean) and cable-sync
  restarted. /world still shows the 14:53Z snapshot even though 15:05Z
  spatial packets replayed — check api_world's latest-snapshot pick
  (ordering or empty spatial_words in late packets); minor, founder
  sees a populated world either way.
- A monitor is dying with this session; first job after founder reply:
  relaunch → confirm fresh snapshot on /api/world with dups=NONE and
  garbage=NONE (dedupe + vocab gate proof), then /world3d is the demo.

## RESPAWN TURN 3 (2026-06-12 ~17:15, FINAL — successor starts HERE)

Founder mandate this turn: progress 15%→30% TODAY, aggressive local-LLM
delegation, lead = decisions not plumbing. What landed:

- **TIER-2 NAMING IS PROVEN.** Hub-side measurement (/api/world,
  pre-hardened build): 12 verified objects, 6 correct (monitor, window,
  table/desk, floor, wall, hat) and 6 garbage ("background itself",
  "black rectangle", "area"...) — and the garbage class is exactly what
  the 16:55 vocab-gate build kills. The architecture works; trust the
  measurement loop, not the diag file (see gotcha below).
- **Load-time dup collapse SHIPPED (99413a2, installed 17:12):** twins
  <=1.0m merge, ghost satellites (<10% of max, <30 sightings, <=3.5m)
  absorb into the dominant; wrong absorbs self-heal. Expect keyboard
  x3 -> x1 etc. on next /world snapshots; diag decision=load_dedupe.
- **/world3d LIVE: navigable three.js word-world** (drag-orbit, zoom,
  click word -> sightings) served by trace_demo_dashboard at :8777.
  qwen wrote it (6 bugs lead-fixed — Math.clamp doesn't exist;
  canvas-resize resets font; white-on-white labels). THE demo surface.
- **Fleet upgrade: `ollama pull qwen3-coder:30b` was IN FLIGHT** when
  this session ended — check `ollama list`. If present, eval it on ONE
  bounded task vs qwen2.5-coder (same single-file+self-test protocol)
  and promote if it beats 4-bugs-per-file. Codex still limit-blocked;
  re-fire brief 7 remainder when founder says.
- **DEVICE GOTCHAS discovered (read or you'll burn a day):**
  (1) The 16:55 devicectl install apparently RESET the SOMA dir —
  spatial_diag.ndjson, vocab_misses.ndjson, spatial_world.arexperience
  all vanished (dir-level pull confirmed; single-file pulls of missing
  files leave a LYING 0-byte local file). spatial_world.json survived
  only because lead re-pushes it around every install
  (install -> push world -> launch; script /tmp/repair_world_labels.py).
  ARWorldMap loss = relocalization starts fresh; acceptable at desk.
  (2) Diag pulls also TRUNCATE silently on large files (socket error
  7000 class) — never trust a quiet diag; cross-check via hub-side
  /api/world measurements (verified flags, label sets, captured_at).
  (3) Diag-write liveness post-install is UNVERIFIED — if diag stays
  empty while world grows, instrument on-screen counters instead.
- Founder-visible state: /world3d pointer posted to his channel; phone
  scanning on desk stand (aimed), hardened+dedup build live.
- **Honest progress math (founder scale):** desk demo was ~40% this
  morning -> naming verified + dedupe + navigable world = call it ~55%
  pending founder's eyes; wearable vision 15% -> ~22-25%. The 30% claim
  is the founder's morning verdict on /world3d + clean names, not mine
  to award.
- NEXT LEAD MOVES (priority order): (1) confirm dedupe + vocab-gate on
  live /api/world (garbage labels gone, dup counts =1); (2) wire
  spatial recall intents ("where is X") from spatial_pose rows —
  cross-module, lead work; (3) qwen3-coder eval; (4) re-fire Codex
  (brief 7 P1 renderer on-phone + P2); (5) missing/moved re-entry
  events = the permanence payoff demo (G2).

## RESPAWN TURN 2 (2026-06-12 ~16:58) — VERIFICATION HARDENED, EVIDENCE LOOP ARMED

- Turn-1 fix was necessary but insufficient. Fresh device data (22,188
  diag lines) showed: meta-word guard WORKS (raw "name" → rejected), but
  (a) two parser escapes relabeled real objects to "background itself"
  (1,417 sightings!) and "area" from prose describing EMPTY crops;
  (b) one object retried the same stale crop every ~5s, 30+ FastVLM
  calls, starving all others; (c) crops are dark/noisy — the camera on
  the desk stand stares at a featureless area, and sensor noise defeats
  the uniform-crop spread gate (0 skips fired).
- **Hardening committed 21a3902, installed + relaunched 16:55:** prose-
  extracted labels must be MobileCLIP vocab words (open vocabulary ONLY
  via the obeyed words-only direct answer); every finished verification
  discards its crop (retries use fresh pixels); per-object backoff
  60s*attempts, hard stop at 6/session (diag: verification_exhausted).
  garbageCropTells broadened (any "background"/"gradient"/"grayscale"
  mention rejects — missed verification < wrong relabel).
- Device world repaired AGAIN in the install gap (install kills app →
  pull → repair → push → launch): "background itself"→trackpad,
  "area"→spotlight, both verified=false. Repair script:
  /tmp/repair_world_labels.py (id-keyed + meta-word sweep).
- **Founder request posted** (cockpit YOUR ACTION): aim the desk-stand
  phone at actual desk objects — every crop till now was "solid black
  background"; no aim = no evidence, regardless of code quality.
- Evidence monitor armed: polls device diag every 4 min, fires on first
  verified/relabeled/verification_exhausted after 14:55Z. Judge the
  hardened build on: zero non-vocab relabels, no >6 attempts/object,
  and ideally the first REAL 'verified' events once the founder aims.
- Build-stamp note: installed stamp lags one commit (build started
  before the commit); next rebuild aligns. Identity-check via diag
  behavior (verification_exhausted lines exist only in 21a3902+).

## RESPAWN TURN 1 (2026-06-12 ~16:40, Fable 5 respawn) — TWO-TIER VERDICT

- Booted per protocol; verified green: 123/123, north-star 1.00, hub/
  world/cockpit 200, cable-sync replaying, ollama up, Codex still
  limit-blocked (re-fire brief 7 remainder when founder says the window
  reset: `./scripts/run_codex_brief.sh ops/CODEX_BRIEF_7_naming_quality_and_renderer.md`).
- **Two-tier verdict from first device run (19,227 diag lines): the
  ARCHITECTURE works, the implementation didn't.** 42 verifications
  fired, 40 rejected — but the rejected FastVLM prose CONTAINED the
  correct names ("the main solid object is the keyboard" on an object
  MobileCLIP called "desk"). Failures: (1) parser demanded a bare word,
  rejected all prose; (2) the one accepted answer was the meta-word
  "name" → relabeled a 110-sighting object to "name"; (3) several crops
  were uniform black ("solid black background" descriptions).
- **Fix committed 5c144b2** (lead-surgical, Codex blocked): prose
  extraction with high-precision patterns only (wrong relabel is worse
  than a missed verification), meta-word blocklist, uniform-crop gate
  (CIAreaMinMax spread >= 24) that drops the crop for re-cache.
  Diag decisions to watch: verified / relabeled / verification_rejected /
  verification_skipped(reason=uniform_crop).
- Build installed + relaunched 16:32; the mislabeled "name" object was
  repaired on-device (label restored to its MobileCLIP hypothesis
  'chocolate milk', verified=false → re-verifies through fixed path;
  push sequenced install→copy→launch so the dead app couldn't overwrite).
- **Cockpit v2 DEPLOYED** (scripts/ops_cockpit.py, :8788): ALERT banner,
  YOUR ACTION box, gate bars (ops/gates_status.json), workers, phone
  pull stats. qwen's draft had 7 bugs (codex log path, cable-sync parse
  crash, /tmp/ops gates path, inverted progress, dirname on pull marker,
  dict-only world JSON, no staleness) — all fixed, page verified 200
  with all sections.
- Known still-open (next lead turns): dup objects (keyboard x3, fan x3,
  desk x3 in 66-object world — founder's moved-furniture finding means
  identity needs anchor/plane association, not pure distance);
  margin-floor tuning from 3.1MB vocab_misses; brief 7 P1 renderer
  status unknown until Codex resumes.

## SUCCESSOR ENTRY POINT (written at 91% limit, 2026-06-12 ~16:25) — START HERE

You are the new lead (Fable 5 respawn or successor model). Mandates:
(1) best achievable prototype by Jun 22; (2) preserve YOUR tokens — fire
Codex and local LLMs for labor, you do judgment + device verification.

### The orchestration loop (all working, lead-fired)
- Codex: `./scripts/run_codex_brief.sh ops/CODEX_BRIEF_X.md` (background).
  CRITICAL: stdin must stay closed or codex exec hangs. Codex HIT ITS
  USAGE LIMIT ~16:15 mid-brief-7; retry when its window resets (founder
  can say when). Its partial work is COMMITTED as WIP (see below).
- Local LLMs: ollama qwen2.5-coder:14b via 127.0.0.1:11434/api/generate
  (temp 0) for single-file code (budget a debug pass — it averages 4 bugs
  per file); gemma3:12b for gates. LM Studio :1234 optional
  (start_local_worker_stack.sh) — do NOT run while anything heavy runs
  (two reboots today from memory pressure; ONE heavy job at a time).
- Founder channel: /tmp/soma_founder_request.txt → he replies in
  /tmp/soma_founder_reply.txt. He watches http://localhost:8788 cockpit.
- Cable-sync: scripts/cable_sync_spool.sh 120 (nohup) replays the phone
  spool over USB every 2 min — THE data path (office Wi-Fi has client
  isolation; phone can never reach the hub there). Restart after reboot
  along with run_trace_stack.sh and ops_cockpit.py.
- Remote scans: push autoOpenSpatial=true pref + relaunch app via
  devicectl → Spatial mode self-starts (phone lives cabled on desk stand).

### State right now
- Installed build = Codex's brief-7 WIP (two-tier naming: MobileCLIP
  hypothesis + FastVLM async verify/relabel; position_spread fields;
  build stamp = WIP commit SHA). Suite 123/123 + north-star 1.00 pass,
  build SUCCEEDED, app relaunched 16:25 — but two-tier behavior is
  UNVERIFIED on device. FIRST JOB: pull spatial_diag + spatial_world
  (scripts/collect_spatial_artifacts.sh), check for relabel/verified
  events, /world rendering, founder-visible map quality. If FastVLM
  verification works, cupboard→refrigerator class misnames should fix
  themselves within sightings>=3.
- Brief 7 P1 (navigable orbit/pan renderer, never hide words) status
  unknown — check SpatialWorld.swift diff in the WIP commit; founder's #1
  UX complaint is the cluttered map ("showing 4/46" hid words).
- qwen is generating cockpit v2 → /tmp/ops_cockpit_v2.py (founder wants
  ALERT banner + "YOUR ACTION" box + gate progress bars; spec:
  ops/LOCAL_TASK_cockpit_v2.md). Debug it, deploy to scripts/, restart.
  Update ops/gates_status.json as gates move.
- LiDAR: founder keeps offering to buy. Standing answer: standalone LiDAR
  units cannot feed ARKit (no sensor fusion API); only an iPhone Pro
  helps, and a mid-sprint device swap costs more than depth precision is
  worth. Re-decide after Jun 22.
- Founder temperature: frustrated with pace, wants chief-level ownership,
  honest assessments (desk demo ~40%, wearable vision ~15%), aggressive
  delegation, and that you NOT do menial labor yourself.

### Verification laws (unchanged)
Suite + north-star after any soma_hub change; daemons restart after
graph.py changes; never trust "installed" without build stamp on the
status line; device artifacts (files!) over claims; one compact founder
test at a time.

## LEAD TURN 8 (2026-06-12 ~16:15, Fable 5) — COCKPIT + CODEX RUNNING

- Founder cockpit LIVE: http://localhost:8788 (scripts/ops_cockpit.py,
  nohup; restart after reboot). Shows stack health, LIVE codex exec log,
  local LLM models, cable-sync, git, ops/*_RESULT.md files. qwen wrote it
  (4 bugs lead-fixed: str/bytes, missing socket import, eval misuse,
  headers=None — typical qwen quality, budget a debug pass).
- Codex CLI now on PATH (homebrew). scripts/run_codex_brief.sh fixed:
  stdin must be closed (</dev/null) or codex exec hangs forever at
  "Reading additional input from stdin" — that was the founder's "Codex
  frozen". Sandbox: danger-full-access (builds/devicectl need it; founder
  consented). Codex RUNNING brief 7 since ~16:02, log via cockpit.
- LiDAR purchase: lead says NO for this sprint — device swap costs setup
  days; the walls are naming accuracy + renderer, not depth. Revisit
  after Jun 22.
- LM Studio model unloaded by the reboot; left DOWN deliberately while
  Codex runs (one-heavy-job law). ollama serves qwen/gemma on demand.

## LEAD TURN 7 (2026-06-12 ~16:00, Fable 5) — ORCHESTRATION LIVE + ARCHITECTURE CALL — READ FIRST

- **Codex can be fired BY THE LEAD now**: `/Applications/Codex.app/Contents/
  Resources/codex exec` works non-interactively. Wrapper:
  `scripts/run_codex_brief.sh <brief.md>` (logs /tmp/codex_run_*.log).
  Codex IS RUNNING on brief 7 right now, lead-fired. The founder no longer
  starts Codex by hand. Loop: lead writes brief → fires codex exec in
  background → notification on completion → lead verifies on device
  artifacts → next brief. Lead sleeps (no tokens) while Codex works.
- **Codex shipped 8397cf3 (LVIS vocab 740 words embedded) + 8baa5c7
  (declutter UI), installed as build 8baa5c7.** Founder verdict: map
  unreadable, cupboard→refrigerator misnaming, positions wrong, words
  "vanish". Lead diagnosis: device memory FINE (59 objects persisted);
  "showing 4/46" declutter HIDES words — renderer bug, not memory loss.
- **ARCHITECTURE DECISION (lead): two-tier naming** — MobileCLIP stays as
  fast hypothesis tier; FastVLM (already in app) asynchronously VERIFIES
  stable objects (sightings>=3) from cached crops with a words-only prompt
  and relabels on disagreement. CLIP cosine at 0.22-0.31/margin 0.01 is
  guessing among neighbors (cupboard/refrigerator) — vocab scaling makes
  margins worse; only open-ended VLM naming breaks that ceiling.
  Full spec: ops/CODEX_BRIEF_7_naming_quality_and_renderer.md (P0 two-tier,
  P1 navigable orbit/pan renderer that never hides objects, P2 position-
  spread diagnosis vs genesis).
- Lead honest position (told founder): desk-scale demo ~40% done after
  today's plumbing fixes; wearable building-walk vision ~15%. The two
  walls are naming accuracy (brief 7 P0) and spatial coherence/legibility
  (P1+P2). Jun 22 cut-line demo remains reachable if two-tier naming
  proves out this week.

## LEAD TURN 6 (2026-06-12 ~15:40, Fable 5) — HUB INGEST FIXED, PIPELINE FULLY LIVE — READ FIRST

- **Codex continuation — Brief 6 P1 mega-vocab prepared:** LM Studio local
  worker returned compute errors, so Codex switched to the running Ollama
  `gemma3:12b-it-qat` worker and filtered LVIS locally. Result:
  `ops/spatial_vocab.txt` is 740 words, bundled MobileCLIP embeddings are
  740x512, and `MobileCLIPNamer` now defaults the margin floor to 0.008 with
  UserDefaults overrides (`mobileclipScoreFloor`, `mobileclipMarginFloor`).
  Added `scripts/build_spatial_vocab_from_lvis.py` so the LVIS filter is
  reproducible/resumable. Gates before commit: script py_compile OK, Python
  suite 123/123 OK, north-star 1.00.
- **Second Mac hang/reboot ~15:15.** No Codex running; almost certainly
  memory pressure from CONCURRENT heavy jobs (LM Studio 9GB model + 1700-
  packet replay + enricher + earlier xcodebuild). LAW: one heavy job at a
  time on this machine. The LVIS local-LLM filter died with it; it is now
  Codex's to rerun SERIALIZED (brief 6 update).
- **Hub ingest bug fixed (commit c23abe5):** _touch_spatial_entity renamed
  entities unconditionally → UNIQUE(kind,label_norm) collision killed
  1591/1592 spatial packet ingests. Now renames only when the label is
  free within the entity's own kind. Gates: 123/123 tests, north-star
  1.00, 1497/1497 spooled packets replay clean. Daemons RESTARTED after
  the change (law).
- Cable-sync hardened (522f34f): device spool is truncated ONLY when zero
  "ingest failed" lines — replay exits 0 even when packets fail, which
  silently destroyed ~1850 device packets earlier today. Loop running
  (120s); /tmp/cable_sync_loop.log.
- /world NOW LIVE from device via USB: 19 objects incl. new-vocab words
  (e-reader, power strip, phone case, trackpad, backpack, belt, mirror).
  Known blemishes for Codex/P4: device dups (fan x2, keyboard x2),
  placeholder 'text surface' leaked as a word, founder's power bank still
  unnamed (suspect 'phone case' is it — check after mega-vocab).
- Pipeline status end-to-end: scan (auto, no human) → NaN-proof post →
  spool (isolated Wi-Fi) → USB cable-sync → fixed ingest → /world. Every
  stage verified today. Remaining founder-visible gap = naming quality
  (mega-vocab + margin floors, Codex brief 6 P1).

## LEAD TURN 5 (2026-06-12 ~15:10, Fable 5) — SPATIAL POSTS FIXED, CABLE-SYNC LIVE — READ FIRST

- **P0 ROOT CAUSE FOUND AND FIXED (lead, commit 391aac8):** spatial posts
  died in `JSONSerialization.isValidJSONObject` — ONE non-finite (NaN/inf)
  coordinate or extent in any word (estimated planes produce them) makes
  the whole payload invalid → silent `return`, no counter, no spool, no
  trace. Fix: sanitize floats, log EVERY post outcome to spatial_diag
  (`__post__` lines: post_ok/post_spooled/post_failed+reason). Verified on
  device: spooled_total climbs within seconds of scanning.
- **Second finding: the office Wi-Fi (10.168.8.x) has CLIENT ISOLATION** —
  phone and Mac on the same network cannot talk. Home network (192.168.50.x)
  works. So live posts spool at the office by design. Countermeasure:
  `scripts/cable_sync_spool.sh [interval]` — pulls the device spool over
  USB, replays via replay_perception_spool.py (timestamps preserved),
  truncates the device spool. Running as nohup (restart after reboot;
  see /tmp/cable_sync_loop.log). Founder alternative for live demo away
  from cable: phone hotspot, Mac joins it.
- **Remote scan capability (autoOpenSpatial):** lead can now run a full
  desk scan with NO human: push `autoOpenSpatial=true` into prefs via
  devicectl, relaunch app → Spatial mode opens itself (phone lives on a
  desk stand, plugged in). Build 391aac8 installed + relaunched this way.
- Local worker stack UP (soma-local-worker on :1234; gemma/qwen in ollama).
  LVIS 1203-class list fetched (/tmp/lvis.yaml from ultralytics); local LLM
  filtering it for indoor relevance → /tmp/lvis_indoor_keep.json (input to
  brief 6 P1 mega-vocab).
- Mac reboot cause per founder: something HUNG during a Codex run and the
  Mac auto-rebooted. Watch for runaway Codex processes; both agents have
  full system access (founder's caution).

## LEAD TURN 4 (2026-06-12 ~15:10, Fable 5) — MAC REBOOT + DEAD SPATIAL POSTS — READ FIRST

- "No progress visible" root cause: the MAC REBOOTED at ~14:17, killing hub
  + enricher (+ wiping /tmp incl. logs/pulls). Phone Wi-Fi was FINE. Lead
  restarted the stack 14:47 (hub/world 200 on 10.168.8.187). A launchd
  LaunchAgent (~/Library/LaunchAgents/de.zer00.soma.stack.plist) is loaded
  but TCC-blocks on Documents ("Operation not permitted") — reboot survival
  is Codex brief 6 P2; until then run scripts/run_trace_stack.sh after any
  reboot.
- REGRESSION FOUND: spatial posts NEVER fire — founder scan 14:35-14:38
  (12 words, hub down) produced hub ok:0 spooled:0 and the pulled spool
  has 58 native_vision packets but ZERO mobileclip_spatial_word lines.
  Main capture path spools fine; spatial path is dead silent. → Codex
  brief 6 P0 (with required spatial_post diag lines).
- Vocab 196 (build 29cc439) verified live on device via founder screenshot
  ("MobileCLIP S0 ready" + build stamp working as designed). Brief 6 P1 =
  mega-vocab (LVIS+OpenImages ~1000 words, local-LLM filtered) + margin
  floor recalibration from diag data + UserDefaults-overridable floors.
- Founder asked for iPhone remote management: devicectl has NO screenshot;
  lead already automates install/launch/terminate/file-pull/prefs-push.
  The only physically founder-bound act is pointing the camera. Standing
  request: leave the phone on a stand at the desk, plugged in + unlocked —
  lead can then run scan cycles by launching the app remotely.

## LEAD TURN 3 (2026-06-12 ~15:00, Fable 5) — VOCAB 196 INSTALLED — READ FIRST

- Founder complaint: "no visible change; can't name power bank or mouse."
  Root causes: (1) vocab was still 82 words — "power bank" not in it, so it
  could NEVER be said; (2) brief 5 was invisible-by-design plumbing; (3) hub
  /world still shows the 11:54 recovery snapshot because the phone is STILL
  not on the Mac's 10.168.8.x Wi-Fi — nothing posted live since. Device data
  shows mouse WAS captured (15 sightings, lastSeen 12:23Z) — the on-phone map
  has it; /world is just stale.
- VOCAB EXPANDED 82→196 words (commit 29cc439): ultracode-curated additions
  (power bank, mouse pad, monitor arm, docking station, radiator, sofa,
  kitchen/bath, carry items, tools...). Embeddings rebuilt (196 in bundle),
  iPhone Release build SUCCEEDED, installed + relaunched ~14:55. Status line
  should read "MobileCLIP S0 ready (196 words)".
- WATCH: more vocab = more cosine competitors = margins drop. Misses margin
  p50 was already 0.008 vs 0.02 floor. After the next scan, pull artifacts
  and check vocab_misses: if correct words now rejected on margin, lower
  margin floor to 0.01 (single constant in MobileCLIPNamer.swift).
- BLOCKED ON FOUNDER (cannot be done remotely): phone Settings → WLAN →
  join the Mac's network. Until then every live post fails (now spooled,
  thanks to brief 5 — replay with scripts/replay_perception_spool.py).

## LEAD TURN 2 (2026-06-12 ~14:10, Fable 5) — G1 ANALYSIS — READ FIRST

- **Desk scan on build `1b7e50d` RAN 13:51–13:54 and capture-side PASSED
  the G1 object bar**: 11 distinct objects persisted on device with real
  coords/extents/plane anchors (laptop, keyboard, webcam, mouse, monitor,
  speaker, fan, desk, chair, router, whiteboard — vs bar of ≥6 in 60s).
  Merging healthy: 139 merges, dup-distance p50 0.049m. Namer p50 104ms,
  peak 81 words/min. Pull at /tmp/spatial_pull/lead_check_1402.
- **BUG FOUND (silent-loss class): hub got ZERO spatial posts from the
  scan.** Phone never joined the Mac's new 10.168.8.x Wi-Fi (Settings→WLAN
  gotcha again), and `postSpatialSnapshotIfNeeded()` is fire-and-forget —
  no completion handler, no spool, and lastPostedSignature updates before
  the outcome. → **ops/CODEX_BRIEF_5_spatial_post_reliability.md** (P0
  spool fallback + P1 hub ok/spooled counters in status line). Blocks P4.
- **Codex brief 5 landed and installed.** Spatial snapshots now use a
  completion handler; failed/non-2xx posts append the exact payload to
  `Application Support/SOMA/perception_spool.ndjson`, and Spatial status shows
  `hub ok:N spooled:N`. `lastPostedSignature`/`lastPostAt` update only after
  a 2xx or successful spool append. The old stale June-11 spool was archived
  at `/tmp/spatial_pull/brief5_prebuild_check/perception_spool.ndjson` and
  cleared on device before relaunch so acceptance can see new spool growth.
  Tests: Python suite 123/123, north-star 1.00, iPhone Release build green.
- **Recovery shipped**: `scripts/ingest_spatial_world.py` posts a pulled
  spatial_world.json to the hub in the app's exact payload shape. Ran it;
  /world now shows all 11 objects (has_spatial=true). Use after any scan
  where the phone was offline.
- **Threshold verdict: DO NOT TUNE yet.** vocab_misses margin p50 is 0.009
  (floor 0.02) and top rejected words are correct desk objects — but the
  same words still got accepted within seconds (webcam 87 merges). The
  margin gate throttles repeat acceptance, it does not block discovery.
  Revisit only if founder correctness check shows wrong/missing names.
- **G1 status: PARTIAL — awaiting founder steps** (Wi-Fi rejoin, name
  correctness X/11, re-show no-dup, swipe-kill reload). Request live at
  /tmp/soma_founder_request.txt; reply lands in /tmp/soma_founder_reply.txt.
- Old device spool (/tmp/spool_check.ndjson, 129 packets) is stale June-11
  native_vision traffic from before the spatial redirect — do not replay
  into the real DB without time-scoping; low value, ignore.
- Stray untracked `yolo11n.mlpackage/` at repo root = export leftover;
  do not add to git.

## GRAND PLAN SESSION (2026-06-12 ~01:40, Fable 5 architect)

- **Codex continuation 2026-06-12 afternoon — P3 installed + pre-Fable
  handoff ready.** iPhone `D3A506B2-8923-5313-B8A3-FF769ABBA228` has build
  `1b7e50d` installed/relaunched (`Expand spatial region proposals`).
  Spatial state was intentionally reset: device `spatial_world.json` is `[]`,
  `spatial_diag.ndjson` and `vocab_misses.ndjson` are empty, hub spatial rows
  are cleared, and `/world` shows an empty reset map. Mac stack is up:
  hub :8765, dashboard :8777, enricher running; `/world` GET returns 200.
  Current Mac Wi-Fi IP is `10.168.8.187`; phone prefs were updated to
  `somaHubURL = http://10.168.8.187:8765` and app relaunched. If the network
  changes, update this preference before testing.
- P3 change now feeds MobileCLIP more regions: saliency plus 3x3/center tile
  fallback when saliency returns too little, cap 5 accepted regions/scan, keep
  scan budget, status shows scan ms + namer p50/p95 + words/min, and rejected
  best words go to `Application Support/SOMA/vocab_misses.ndjson`.
- Added `scripts/collect_spatial_artifacts.sh`: one command pulls
  `spatial_world.json`, `spatial_diag.ndjson`, `vocab_misses.ndjson`,
  `spatial_world.arexperience`, and dashboard `/api/world`, then runs
  `scripts/analyze_spatial_diag.py`. Verified before scan at
  `/tmp/spatial_pull/post_url_fix_check`; files are empty as expected because
  the world was reset. Analyzer self-test passes; fixed analyzer per-word mean.
- Local worker stack is available: `scripts/start_local_worker_stack.sh`
  loaded LM Studio model `soma-local-worker` on `127.0.0.1:1234`. The harness
  supports `--timeout` for slower local responses. Use local workers only for
  bounded scout/critic summaries; they do not replace device/founder judgment.
- Subagent P4 map (read-only): implement re-entry events mostly in
  `SpatialWorld.swift` with transient session-start snapshots after loaded
  world map; track 10s continuous normal tracking, frustum exposure ~3s,
  re-seen/moved checks before EMA mutation, missing after 90s, and post
  `EVENT | object missing | ...` / `object moved` perception packets with
  metadata `capture_mode=spatial_reentry_check`. Hub dedup should key on
  `reentry_session_id + reentry_object_id + event_type`; dashboard should show
  recent re-entry events. Do NOT start P4 until P3/G1 desk evidence is pulled.
- Next human/Fable action: run the IRL desk scan on build `1b7e50d`. Pass bar:
  at least 6 distinct correct desk objects within 60s for P3, no duplicate on
  re-show, survive swipe-kill/reopen, and `/world` non-empty. After the scan:
  `scripts/collect_spatial_artifacts.sh /tmp/spatial_pull/<name>` and inspect
  merge rate, scatter distances, namer p50/p95, and vocab misses.

- **ops/GRAND_PLAN_2026-06-12.md is the governing schedule to June 22**:
  day-by-day owners, gates G1–G4, lead turn budget (~12), cut-line,
  succession protocol. This section only records what was VERIFIED tonight.
- **CRITICAL FINDING — stale build:** the founder's failed desk test
  (brief-1 acceptance, ~23:12 posts) ran an OLD build: hub rows carry
  `word_source: native_vision_classifier`, a string that exists NOWHERE in
  current code (repo posts `mobileclip_zero_shot`). Device pulls confirmed
  NO spatial_diag.ndjson / spatial_world.json on the phone — the brief-3
  build had never been installed. The MobileCLIP path was never actually
  device-tested before tonight.
- **"Device build blocked" was FALSE.** The documented recipe works
  (verified 01:20): `xcodebuild -project FastVLM.xcodeproj -scheme
  "FastVLM App" -configuration Release -sdk iphoneos26.5
  ASSETCATALOG_EXEC=/tmp/actool_wrapper/actool build` → BUILD SUCCEEDED.
  Destination-based builds are what fail. Bundle verified to contain
  mobileclip_s0_image.mlmodelc + vocab_embeddings.json (82 words).
  **Installed on iPhone 01:28** via devicectl (app path in DerivedData
  FastVLM-hgpowjcsgrivjgftwcetohnqmdug).
- Verified green tonight: 122/122 tests, north-star 1.00, hub :8765
  /health ok, dashboard :8777 /world 200 (renders LATEST snapshot only —
  durable-world gap is Codex brief 4 P1).
- **ops/CODEX_BRIEF_4_durable_world.md supersedes brief 2**: P0 build
  stamp (git SHA in status line + packet metadata — the stale-build class
  of failure must die), P1 durable world in graph (spatial_pose +
  /world from DB), P2 extent, P3 region-proposal grid fallback +
  vocab_misses.ndjson, P4 re-entry events.
- **Night shift restarted 01:35** with ops/night_shift_queue.json:
  N1 qwen analyzer (scripts/analyze_spatial_diag.py), N2 suite gate,
  N3 founder desk test 2 (ops/FOUNDER_DESK_TEST_2.md — morning, ~6 min,
  identity check first), N4 diag pull gate. State:
  ops/night_shift_state.json, log /tmp/soma_night_shift.log.
- **G1 = founder desk acceptance** (≥4 desk objects named+pinned, no
  dupes on re-show, survive swipe-kill, /world shows them). Next lead
  turn: analyze /tmp/spatial_pull/spatial_diag.ndjson, tune score floor
  (0.22)/margin (0.02)/merge radius (2.0m)/promote distance (0.8m) from
  data, deliver G1 verdict, prep walk 2.

## Mission state (2026-06-10 late)

**V1 (relationship memory from comms): COMPLETE and validated on real data.**
- Full WhatsApp archive imported: iOS ChatStorage at
  `"/Users/zer00/Desktop/Claude not code/1.sqlite"` → 209 contacts, graph at
  `data/soma_hub.sqlite3` (backup: `data/soma_hub.sqlite3.bak-20260610`).
- Recall is STRICTLY EXTRACTIVE (no generation in answers — gemma synthesis
  hallucinated people; removed, user-confirmed direction). Citations carry
  message-time provenance + confidence.
- Commitment pipeline (all behaviors locked by eval canaries):
  regex candidates (incl. elided-subject "but will come…") → gemma banter
  gate (temp 0, stable) → 7d short-horizon lapse rule (deterministic) →
  explicit-completion check (deterministic phrase+overlap). LLM fulfilment
  judging REJECTED by measurement: gemma verdicts inverted under prompt
  rephrasing (real + canary case, 2026-06-10). `_llm_commitment_resolved`
  kept unused.
- Demo/audit: `python3 scripts/demo_felt_moment.py --db data/soma_hub.sqlite3
  --person "Name" [--facts]`
- Eval: `python3 evaluation/run_north_star.py` — labeled fixtures through the
  real importer; canaries: banter, direction, fulfilled, lapsed, elided-subject.

**V2 (camera/perception): IN PROGRESS — current focus.**
- `soma_perception/scheduler.py`: salience + token-bucket budget engine with
  PROGRESSIVE ENRICHMENT LADDER (user-confirmed core idea: attention depth =
  knowledge depth). Levels overview/attributes/minutiae at 8s/24s/72s dwell,
  one token each, cap 3; dwell_progress measured vs NEXT level requirement
  (replaces the earlier repeat discount, which wrongly suppressed deepening).
  `salience = dwell_progress * (0.6*novelty + 0.4*stability)`. Decisions
  carry level + detail_focus; VLM consumer must prompt for DELTA facts.
  13 contract tests in `tests/test_enrichment_scheduler.py` = Swift port spec.
- Wired into `soma_perception/worker.py` behind `--enrich-budget N` (per
  hour). Emits `enrichment_request` JSON lines. Run via
  `./scripts/run_perception_worker.sh --enrich-budget 60 --frame-stride 4`
  (uses `.venv/bin/python` — system python3 lacks cv2).
- Camera: agent shell has NO macOS camera permission ("Claude" not listable);
  USER runs the worker in his Terminal, piping to a /tmp file the agent reads.
- MAC LIVE VERIFICATION DONE (2026-06-10 21:24 UTC, /tmp/soma_live.json):
  644 ticks; exactly ONE enrichment_request at 4.9s dwell (salience 0.453);
  29 below-threshold holds before; 365 ticks of silence after (repeat
  discount working); 0 denied/evicted. Analyzer:
  `python3 scripts/analyze_budget_run.py <log>`.
- ENRICHMENT CONSUMER LIVE (soma_perception/enricher.py): worker saves
  winning-track crops + sidecars to /tmp/soma_enrich; enricher daemon runs
  level-appropriate gemma3 VISION passes (delta-prompted with what the graph
  knows), writes vlm_overview/attributes/minutiae attributes, deletes crops
  (no media retention). E2E-verified on synthetic object incl. minutiae
  ("faint scratch near M") landing on the SAME entity.
- 24/7 stack: user runs in HIS Terminal (camera permission):
  `nohup ./scripts/run_trace_camera.sh 12 > /dev/null 2>&1 &`
  stop: `pkill -f soma_perception`; analyze:
  `python3 scripts/analyze_budget_run.py /tmp/soma_budget_run.json` +
  /tmp/soma_enricher.log. THEN: Swift port of scheduler into FastVLM app
  (contract = tests/test_enrichment_scheduler.py); iPhone connected.
- Product name: TRACE (pitch brief 2026-06-10, "SOMA is a sedative") —
  task #9 staged rename; X-SOMA-Token + soma_hub.sqlite3 are load-bearing,
  rename with shims only.
- iPhone is connected to the Mac and available (FastVLM app:
  `soma-native-fastvlm/`, bundle `de.zer00.soma`, scheme "FastVLM App";
  `/tmp/actool_wrapper/actool` must be recreated after reboot, chmod +x).

## THESIS LOCKED 2026-06-11 (founder strategy session) — overrides earlier framing

- Product thesis: CAPTURE PRECEDES INTENT. The system perceives the world
  BEFORE any prompt exists, so arbitrary questions are answerable
  retroactively. (Claude vision mode = look after task; this = look first.)
- V1 comms graph = the SPINE real-world context attaches to, not the product.
  Digital-only context is commoditized (Pixel/Recall); founder rejects
  privacy/local-first as differentiator — it is the load-bearing wall that
  makes EU vision capture lawful, not the brand. Differentiator = the new
  sensory domain (eyes/ears) no competitor's LLM has.
- Canonical demos: fusion ("what went wrong on the Sophia date" = comms +
  encounter on same person/date) and retroactive world-text ("dates on the
  robotics-week flyer in U-Garching" = OCR + place + time).
- North-star metric: Retroactive Answerability Score (RAS) — post-capture-day
  battery of arbitrary questions; correct-with-citation %, hallucination
  negative, honest miss neutral.
- Rig: iPhone chest-mounted (live pipeline). NO raspberry-pi/custom hardware.
- LLM: never pretrain; LoRA only for narrow extractors when evals prove the
  harness can't close the gap. Scheduler = attention prior = core IP.
- Grounded-RAG recall: COMMITTED (d76cd99) — sealed retrieval
  (graph.context_bundle) + constrained generation (recall._grounded_answer,
  gemma temp 0, refusal default, NOT-IN-MEMORY → helpful honest miss).
  118/118 tests, north-star 1.00, 0/12 dead-ends. Daemons RESTARTED after
  the graph.py change (hub + enricher running new code, phone posting OK).
- RAS HARNESS LIVE: evaluation/run_ras.py (ask → founder fills verdicts →
  score). Smoke-tested on live DB (4q, harness works; real RAS needs a
  blind battery after a capture day). Protocol: founder writes ~25
  questions BLIND the evening after wearing the rig. RAS=(correct-wrong)/
  total; halluc rate gate <5%; pitch gate RAS>=60 stranger-authored.
- FOUNDER STATE: chest mount READY ("born ready"); commit go-ahead given;
  blind-question protocol agreed; lawyer email when we draft it. Execution
  delegated ("you're the CEO") with usage-limit care + lossless respawn
  directive (this doc = the contract).
- MILESTONE LADDER (pitch path): M0 done (desk rig + sealed RAG).
  M1 = worn-POV Garching walk → first RAS number. Offline blocker SOLVED:
  app spools undeliverable packets to Application Support/SOMA/
  perception_spool.ndjson (error, non-2xx, AND bad-URL guard — comma-bug
  class); replay via scripts/replay_perception_spool.py (timestamps
  preserved — verified on temp DB). Spool-enabled build INSTALLED on
  iPhone 2026-06-11. Founder runbook: ops/M1_WALK_RUNBOOK.md.
  60s OFFLINE TEST PASSED (2026-06-11 15:46): 86 packets spooled on
  device (GPS hints + OCR attempts included), pulled via devicectl —
  path is "Library/Application Support/SOMA/perception_spool.ndjson"
  (SOMA/ subdir!) — replayed 86/86 into temp DB then real DB with
  capture timestamps intact; 1 place row (no phantom explosion); device
  spool truncated after replay (push empty file — devicectl has no rm).
  WiFi GOTCHA: Control Center toggle doesn't rejoin — desk capture keeps
  spooling until founder re-enables via Settings → WLAN.
  M1 DONE (15min walk, founder chose shorter): RAS BASELINE = -8.0
  (1 correct / 3 wrong / 21 miss, founder-verdicted; committed in
  evaluation/ras/walk1.*). Battery 2%/15min ≈ 8%/hr. Founder verdict:
  "disaster... needs an overhaul" — correct. Failure taxonomy:
  (a) ALL 3 hallucinations = stale/mislabeled evidence as current →
  FIXED same day: time-scoped retrieval, [observed DATE] tags on visual
  facts, person-kind-only name matching, distance intent (370m/187
  fixes now answers), enricher must qualify material guesses, phone
  material user-corrected to glass. RESIDUAL: same-day episode
  separation (walk vs desk) needs episode layer → task #6.
  (b) 21 misses = CAPTURE-side: walking OCR garbage despite founder
  dwelling on poster (stream-buffer OCR suspect → full-res still pass,
  task #5), coarse scene classes (no bikes/scale/door → real detector,
  task #5), no behavioral events (#6), Julian not enriched (#5),
  geocode place names wrong (#7). NOTE: desk-screen OCR DID capture
  ChatGPT/Fujitsu internship/10-citations content — close+stable text
  works; retrieval under-served it.
  WALK 2 PROTOCOL (founder-approved): capture app records ground-truth
  video+audio of same frames (self-data only); Claude reviews video vs
  graph afterward → capture-precision report → tune. Tasks #5/#6/#7 =
  the overhaul; #5 first.

## SPATIAL DIRECTION (founder, 2026-06-11 end of session)

- Founder proposal, endorsed: PERSISTENT SPATIAL SCENE GRAPH — objects
  with x,y,z in a per-place coordinate frame; attributes anchored to
  object-local regions ("dirt on left-rear corner of the white desk");
  containment/support relations (headphones ON desk) with metric
  offsets. Text/structured representation, no meshes — stays
  journal-not-camera. This generalizes old task #10 (ARKit VIO+LiDAR).
- Engineering shape: ARKit world tracking gives the geometry nearly
  free (HW VIO); LiDAR depth + detection bbox → 3D object position;
  ARWorldMap relocalization = persistent per-place frames (office,
  home). Reasoning stays in graph+LLM. Chest-mount tracking quality and
  battery must be measured, scheduler-gated. Outdoors/transient scenes:
  relative relations only (drift).
- FOUNDER REFINEMENT (end of session): the "ASCII world" — same graph,
  rendered spatially: words ARE the objects, placed at their real x,y,z
  with orientation and extent (Vision-Pro-style zoom: desk-word contains
  headphones-word at its position, attributes + web-identified model on
  inspection). Decision: graph stays the STORE (relational queries,
  encryption, decay, provenance, LLM-consumable); the 3D world is a
  RENDERER over it — buildable later (three.js/RealityKit) iff the
  schema carries geometry. SCHEMA BAKE LIST for app v2 + graph: per-place
  coordinate frames (ARWorldMap anchor id), object pose (position,
  orientation, extent) per entity per place, observation camera pose,
  attribute-local offsets ("dirt @ left-rear of desk plane"), support/
  containment relations with offsets. Web-lookup object ID = optional
  enrichment tier (text descriptors only leave device) — later.
  Functional payoff before any renderer: re-entering a place loads its
  graph slice = expected-objects set → presence/absence/moved events.
- SEQUENCING: capture app v2 (task #5) must POSE-STAMP every detection
  (camera pose + depth → estimated 3D position in session frame) from
  day one — cheap insurance that makes the spatial graph buildable
  later without re-instrumenting. Full per-place world maps + object-
  local attribute anchoring AFTER OCR/detector basics prove out.

## Capture v2 state (2026-06-12 session)

- CAPTURE V2 BUILT + INSTALLED on iPhone (commit: "capture app v2").
  Pieces: ObjectDetectorV2 (yolo11n.mlpackage in app, VNCoreML per tick,
  conf>=0.40, person excluded — person path unchanged); dwell OCR stills
  (stable + lastAcceptedOcrCount>=2 + 20s cooldown → captureStill() →
  accurateOCR en+de → commitMemoryRecord source=ocr_still); GT recorder
  (toolbar record button, UserDefaults key gtRecordingEnabled, writes
  Documents/walk_gt_<ts>.mov, pull via devicectl); PoseStamper (attitude
  quaternion + battery_pct in every packet's metadata).
- Smoke test PENDING: founder launches app at desk 60s pointing at book +
  screen; verify graph delta past observation watermark 296: expect
  coreml-detected object records + ocr_still commit + pose in observation
  metadata. THEN walk 2 (GT toggle ON) + blind battery.
- Model export recipe: .venv/bin/python ultralytics export format=coreml
  nms=True → yolo11n.mlpackage → copy into "FastVLM App/" (synced group).
- Respawn verification (2026-06-11 17:35 CEST): visual-only wipe is already
  applied and backed up (`data/soma_hub.sqlite3.bak-prewipe-202606111723`);
  current DB keeps 22,949 WhatsApp messages but has 0 visual observations and
  0 visual relations. Python tests pass (122), north-star remains 1.00.
  Genesis-frame Spatial mode now builds: iPhone Release build passes with
  `ASSETCATALOG_EXEC=/tmp/actool_wrapper/actool` as an xcodebuild setting,
  and Mac Debug build also passes after guarding ARKit/CoreMotion/fullScreenCover
  to iOS with harmless Mac stubs. Signed build installed on paired iPhone
  (`de.zer00.soma`) at 2026-06-11 17:37 CEST. NEXT: 60s desk smoke test
  above.
- Founder correction (2026-06-11 17:48 CEST): do NOT frame Spatial mode as
  answering questions or emitting an indented textual tree. Desired behavior:
  a live visual word map showing recorded object/plane words (`desk`,
  `headphones`, `scale`, `monitor`, etc.) placed where they sit relative to
  each other. Implemented first pass: Spatial screen now renders labels on a
  top-down x/z canvas; floor detection accepts ARKit floor, lowest horizontal
  surface, or estimated horizontal raycast probe; OCR, full-res OCR stills,
  image-level classifications, and person VLM enrichment are disabled for now.
  Signed build installed on paired iPhone at 2026-06-11 17:47 CEST.
- Founder correction (2026-06-11 18:00 CEST): do NOT use YOLO/detector for
  spatial word naming; this must be FastVLM. Implemented: Spatial mode asks
  FastVLM for short solid-object/plane words plus rough screen zones, raycasts
  those zones into the ARKit genesis frame, renders them on the phone word map,
  and posts `fastvlm_spatial_word` snapshots with `metadata.spatial_words`
  to the hub. Local detector/CoreML object memory paths are disabled. `/world`
  now renders only real posted spatial words; no random/fake placement. Current
  visual state after install: dashboard is open/running on `http://localhost:8777/world`,
  but API reports `has_spatial=false`, `observations=0` until founder opens
  Spatial mode and pans the phone. Signed build installed on paired iPhone at
  2026-06-11 17:59 CEST; app launched and hub URL verified as
  `http://192.168.50.145:8765`.

## Capture v2 ARMED (2026-06-11 evening, this session)

- A parallel session BUILT v2 (commits 0e90ac1, 69df669): CaptureV2.swift
  (ObjectDetectorV2/yolo11n, accurateOCR, PoseStamper, GroundTruthRecorder),
  CameraController.captureStill(), GT record button (UI line ~498), pose+
  battery stamped into packets (~2291). BUT everything was DISARMED:
  ENABLE_OCR_STILL_PASS=false and objectHits hard-coded [] (ContentView
  ~1318). Walk-1 device log: 0 ocr_still events — confirmed never fired.
- THIS session armed it: ENABLE_OCR_STILL_PASS=true; objectHits =
  ObjectDetectorV2.shared.detect(frame, minConf moving 0.50 / else 0.40).
  Verified: walk-1 had 129 'stable' phases (trigger reachable);
  lastAcceptedOcrCount updates in always-on path (line 1337); project
  uses PBXFileSystemSynchronizedRootGroup (6) so yolo11n.mlpackage (5.2M)
  auto-bundles; CameraController preset hd1920x1080 (the .vga640x480
  comment at ContentView:163 is stale).
- FOUNDER WORKFLOW RULE (memory: feedback-delegate-local-llms): never
  spawn Claude subagents — delegate to local LLMs (qwen single-file,
  gemma gates); Claude = lead/integrator only; preserve usage limits.
- Walk-2 protocol: founder taps the red record button (GT video), walks,
  blind battery again. Compare RAS vs -8.0 baseline.

## FOUNDER REDIRECT (2026-06-11 late) — OVERRIDES PRIORITIES BELOW

- ONLY priority now (task #8): IMMEDIATE object naming + fixed
  dimensions/coordinates in space + PERMANENT memory. Attributes, chat,
  OCR, episodes = secondary until this works. Founder rates overall
  progress SINGLE DIGITS — calibrate against the spatial vision.
- No YOLO (closed 80 classes useless: cpu/fan/keyboard/mouse). FastVLM
  naming too slow + rambles ("words not prose"). The middle path:
  MobileCLIP zero-shot CoreML naming over LiDAR/depth-protrusion region
  proposals; raycast → genesis-frame coords (SpatialWorld.swift engine,
  Codex-built); upsert by label+position cell, sightings count, never
  decay; persist via hub; ARWorldMap relocalization for permanence.
  Full design: memory project_redirect_spatial_first.md.
- Progress surface = http://localhost:8777/world (Codex's spatial view).
  Codex is ALSO working in this repo (git user Codex) — coordinate via
  commits, don't clobber SpatialWorld.swift blindly.

## BRIEF 1 ACCEPTANCE: FAILED (2026-06-12 ~01:00) — BRIEF 3 ISSUED

- Founder desk test failed all three points: duplicates on re-showing
  same objects; everything gone after swipe-kill; :8777 dead.
- LEAD-VERIFIED ROOT CAUSES: (1) spatial_world.json NEVER created on
  device — save only in stop(), which SIGKILL never calls (lifecycle
  bug); (2) no spatial diagnostics at all — failures unmeasurable;
  (3) dashboard process simply wasn't running (lead restarted hub +
  dashboard; / and /world = 200 now); (4) duplicates: merge radius vs
  raycast scatter — needs diag data, two-sighting confirmation, nearest-
  same-word merge; (5) cross-session dupes guaranteed until world map
  actually saves.
- ops/CODEX_BRIEF_3_permanence_bugfix.md = the fix list IN ORDER,
  blocks brief 2. Re-acceptance is measurable (spatial_diag.ndjson).
- Lesson recorded: Codex delivers uncommitted + untested-on-lifecycle;
  lead must verify device-side artifacts (files exist!) not just builds.

## BRIEF 3 PERMANENCE BUGFIX LANDED (2026-06-12 ~01:10)

- `SpatialWorld.swift`: persistence no longer depends on `stop()`. Object
  JSON saves synchronously 2s after permanent upserts, every 30s, and on
  scene/app inactive/background/terminate. Lifecycle saves wrap ARWorldMap
  save in a UIKit background task; JSON save runs first and does not depend
  on world-map success.
- Duplicate fix: same-word permanent nearest merge up to 2.0m (EMA 0.8/0.2,
  sightings++). New words become pending only; second same-word sighting
  within 0.8m promotes to permanent. Pending one-offs expire after 30s.
- Cross-session gate: when an ARWorldMap loads, new upserts are rejected
  until tracking reaches `.normal`; after 20s it logs `relocalization_timeout`
  and allows upserts with loaded objects.
- Diagnostics: every naming/upsert decision appends to
  `Application Support/SOMA/spatial_diag.ndjson` with ts, word, score, ms,
  pos, decision, matched_id, dist_to_nearest_same_word, and extra reason/
  sightings fields. This is the file to pull after the desk test.
- Added `scripts/run_trace_stack.sh`: idempotent startup for hub (:8765),
  dashboard/world (:8777), and enricher. Verified output now returns
  `/health` 200 with `X-SOMA-Token: dev-token`, `/` 200, `/world` 200.
- Validation: focused iOS type-check of `MobileCLIPNamer.swift` +
  `SpatialWorld.swift` passes (only known standalone CVImageBuffer Sendable
  warning); Mac Debug Xcode build passes; Python unittest suite 122/122 and
  north-star 1.00 pass. Device build/install still blocked by local Xcode:
  `devicectl` sees the phone connected, but Xcode marks iOS destination
  ineligible ("iOS 26.5 is not installed") and target-level iphoneos build
  still fails in SwiftPM Jinja resolving OrderedCollections before app code.

## CODEX BRIEF 1 DELIVERED + VERIFIED (2026-06-11 ~21:30)

- Codex shipped the MobileCLIP core (left uncommitted; lead committed
  it after verification): MobileCLIPNamer.swift, mobileclip_s0_image
  .mlpackage (22MB), Resources/vocab_embeddings.json (82 words, 512-d,
  prompt 'a photo of a/an {word}'), SpatialWorld persistence
  (spatial_world.json + ARWorldMap save/load, Codable SpatialObject),
  scripts/build_vocab_embeddings.py. BUILD SUCCEEDED (iphoneos).
- INSTALL PENDING: phone unreachable at install time — founder must
  plug in + unlock, then: xcrun devicectl device install app --device
  D3A506B2-8923-5313-B8A3-FF769ABBA228 "<DerivedData>/Release-iphoneos/
  FastVLM App.app". Then DESK ACCEPTANCE: cpu/fan/keyboard/mouse named
  + pinned (words at positions), restart app -> map reloads, /world on
  :8777 shows it.
- BRIEF 2 ISSUED: ops/CODEX_BRIEF_2_dimensions_permanence.md — extent
  via edge raycasts, spatial_pose attribute in graph (upsert by
  entity+key), /world renders from DB, re-entry missing/moved events,
  perf budget + vocab_misses.ndjson feedback loop. Python suite stays
  the gate after any soma_hub change.

## CODEX DELEGATION (2026-06-11 ~20:30)

- Spatial core handed to Codex: ops/CODEX_BRIEF_spatial_core.md is the
  full implementation contract (MobileCLIP-S0 image encoder CoreML +
  offline vocab embeddings, saliency region proposals, raycast pinning
  WITHOUT LiDAR — founder's iPhone 17 base has none — JSON + ARWorldMap
  permanence, acceptance = cpu/fan/keyboard/mouse named+pinned+persist).
  Vocabulary: ops/spatial_vocab.txt (~80 words, founder-editable).
- LiDAR purchase: NOT needed now (estimated-plane raycast suffices);
  if ever, the meaningful buy is an iPhone Pro, not a sensor — defer.
- NIGHT SHIFT: stopped itself after T1-episodes failed 4 attempts
  (qwen; tree left green, file reverted). Founder: ignore episodes.
  Harness + cockpit (localhost:8788) remain for future queues.

## NIGHT SHIFT RUNNING (started 2026-06-11 19:50)

- Capture v2 ARMED BUILD INSTALLED on iPhone (OCR stills + yolo11n live;
  SpatialWorld access-level errors fixed). Parallel session's
  SpatialWorld.swift = genesis-frame ARKit world engine (founder's
  spatial vision) — already in the app.
- scripts/soma_night_shift.py is executing ops/night_shift_queue.json
  unattended: T1 episodes module (qwen+self-test) -> T2 suite gate ->
  T3 GT-video review tool -> T4 founder desk check -> T5 ocr_still
  device gate -> T6 founder walk 2 (record button + blind battery) ->
  T7 spool replay + episodes + RAS ask -> T8 founder verdicts.
- State: ops/night_shift_state.json; log /tmp/soma_night_shift.log;
  founder channel /tmp/soma_founder_request.txt -> reply via
  'echo done > /tmp/soma_founder_reply.txt'. Stop: pkill -f soma_night_shift.
- NEXT CLAUDE SESSION: read state+log FIRST; qwen work is committed as
  'night-shift:' commits — REVIEW EVERY ONE (qwen passes self-tests it
  wrote to my spec, not judgment); then walk-2 postmortem vs RAS -8.0;
  then integrate episodes into recall time-scoping (_question_since ->
  episode window — cross-module, Claude-only work).

## NEXT SESSION ENTRY POINT

1. Read this file fully + auto-memory (thesis-capture-before-intent).
2. Verify: tests green (122), north-star 1.00, hub+enricher daemons up
   (restart per Respawn instructions if not), TaskList #5/#6/#7 open.
3. START: task #5 capture app v2 — CoreML detector, dwell→full-res
   still→accurate OCR, ground-truth video toggle, pose-stamped
   observations, spool (exists), battery readout. Build/install recipe
   in "Demo + iOS state" section. Founder tests with walk 2 + blind
   battery (runbook), RAS curve continues from -8.0.
  FOUNDER REMARK: "maybe we need to rework the entire app" — agreed in
  principle (FastVLM demo UI → dedicated capture-first app: big start/
  pause, spool/battery status, no chat UI). Decide AFTER M1/M2 walk data
  shows what capture actually needs. Not now.
  M2 = the mines: 8h on-device budget/thermal proof, OCR high-value trigger
  (flyer test = acceptance), place clustering, hallucination-rate eval.
  M3 = fusion demo (comms graph + camera encounter, same person/date —
  Sophia-class question). M4 = pitch package (RAS curve + cost-of-a-
  remembered-day + legal one-pager). Strategy rationale: memory file
  thesis-capture-before-intent + chat 2026-06-11.
- PARKED: vision person re-id descriptor clusters (task #2) — pending use
  case + legal memo. LLM strategy: never pretrain; LoRA only for narrow
  extractors when evals prove harness can't close the gap.

## Direction set 2026-06-11 (user design session)

- Goal restated by user: simulate the real world to text/context maximally.
  Senses map: sight (running), hearing (ASR task #11, transcribe-then-discard,
  user's own voice first), touch proxy (hand-object interaction, feasible),
  taste proxy (meal recognition), smell (no sensor, honest no). Physio layer
  (Watch HR/HRV → emotional valence on events) endorsed as sleeper feature.
- SPATIAL: user proposed gyro-based direction tracking → production form is
  ARKit world tracking (6DOF VIO) + LiDAR in the Swift port (task #10) —
  Continuity Camera does NOT expose iPhone IMU to mac. Interim: in-frame
  pairwise relations from bboxes. Room tour produced 4 object entities but
  only frame-relative positions — gap confirmed empirically.
- 24/7 stack RUNNING on user's desk via Continuity Camera (iPhone): teddy
  bear/cell phone/remote/bottle entities, 11 vision facts, bottle climbed
  full ladder (scratches/discoloration in vlm_minutiae). Budget honored.
- Consolidation job = task #12 (episodes/dedup/decay/distill, nightly).
- Legal posture: maximal design is a thought experiment; bystander ASR and
  biometric identity keys stay out until lawyer clears; own-data expansions
  (screen OCR, location, consolidation) are clean.

## Demo + iOS state (2026-06-11)

- VISUAL DEMO LIVE: `python3 scripts/trace_demo_dashboard.py` →
  http://localhost:8777 — interactive force-graph of the live DB (click
  nodes → facts w/ provenance) + Ask-TRACE chat with citation chips.
  User directive: ALL demo surfaces visual, never terminal. Known gap:
  only ~24 entity-entity edges (relations sparse until task #10 spatial).
- iOS BUILD SUCCEEDED (Release-iphoneos) with the Swift scheduler in:
  build needs `-sdk iphoneos26.5` (bypasses destination check; iPhone is
  on iOS 27.0 vs Xcode 26.5) AND ASSETCATALOG_EXEC=/tmp/actool_wrapper/actool
  (recreate after reboot — wrapper strips actool's false "No available
  simulator runtimes" error; outputs are produced fine). Swift port has
  11/11 contract parity (harness: /tmp/main.swift pattern).
  App at DerivedData/FastVLM-*/Build/Products/Release-iphoneos/FastVLM App.app
  NEXT: `xcrun devicectl device install app --device D3A506B2-8923-5313-B8A3-FF769ABBA228 <app path>`
  (user unlocks phone), then live ladder test on device.

## User acceptance findings (2026-06-11, dashboard session) — THE BAR

User's product bar, verbatim spirit: "without the visual, everything should
be described as accurately as possible" — the graph is a TEXT SIMULATION of
reality, reconstructable without media. Three acceptance failures, all
"abstraction stored instead of experience":
1. "What photo did I send to Ziwei Zhang on Feb 14" → no answer. Importer
   skips media messages entirely (ZMESSAGETYPE != 0); no dated message
   events; no date-scoped recall intent. It was a Valentine's cake photo.
   → task #13. Future media must be VLM-described at capture time.
2. "What color are the eyeglasses" → legacy MemoryStore dump. No graph
   object-attribute intent; also the eyeglasses entity came from the iOS
   app and mac YOLO can't see that class → never enriched. → task #14.
   On-device scheduler app INSTALLED on iPhone (de.zer00.soma) closes capture.
3. Phantom GPS places while sitting in one room. GPS demoted to coarse
   anchor; precise position = visual-inertial dead reckoning (user's pan-
   tracking insight = ARKit VIO). → task #10 sharpened + place clustering.

## Message corpus live (2026-06-11 late)

- graph_messages: 22,949 encrypted messages incl. 1,915 media events
  ("[photo] caption") across 209 contacts. message_search recall intent:
  person + direction + terms + dates + longest. User's three failed
  questions now answer (Good Friday message found verbatim; "what photo
  did I send Feb 14" → two [photo] events with dates — content unknown,
  needs WhatsApp media folder one-time pass OR capture-time description).
- Policy note: EXTRACTION_REQUEST_WORDS still blocks "verbatim/exact
  transcript" phrasings — owner-access policy question, revisit.
- Hub running on 192.168.50.145:8765; iPhone app INSTALLED + running but
  ZERO posts received yet — app hub URL likely stale (old eduroam IP).
  User must set http://192.168.50.145:8765 in app.
- iPhone app has Swift scheduler gating person enrichment (installed
  2026-06-11); awaiting on-device verification via hub arrivals.

## Acceptance round 2 fixes (2026-06-11 midday) — ALL LANDED

- ROOT-CAUSE FOUND: camera ingest (_mark_inactive_entities_stale) staled
  EVERY entity not in camera view incl. all imported contacts — recall
  degraded as the day progressed ("dumber than before"). Fix: vision
  liveness scoped to vision entities (relationship_source exempt); rows
  repaired via SQL; RESTART DAEMONS AFTER GRAPH.PY CHANGES (old code in
  long-running hub/enricher re-corroded once — watch for this).
- resolve_person: digits + difflib fuzzy ("Amirhossain"→hit). New intents:
  "last conversation with X"→message_search; "topics with X"→who_is.
  Graph-intent misses → honest "I don't have that in my memory yet"
  (legacy observation dump suppressed for those intents).
- Dashboard UI: flex min-height fixes; chips drop ?/0.00 noise.
- iPhone CONFIRMED POSTING: app hub URL was already right; blocker was hub
  not running on mac. Hub must be up: python3 -m soma_hub.api --host
  0.0.0.0 --port 8765 (mac IP 192.168.50.145, phone 192.168.50.69).
- Pull/push app prefs without user: xcrun devicectl device copy from/to
  --domain-type appDataContainer --domain-identifier de.zer00.soma
  --source Library/Preferences/de.zer00.soma.plist

## Spatial object permanence core (2026-06-12)

- Priority #8 implemented in the main checkout: `SpatialWorld.swift` now uses
  Vision objectness saliency (max 3 regions/frame) → MobileCLIP-S0 image
  embedding → cosine match against bundled `Resources/vocab_embeddings.json`.
  FastVLM remains in the app but is no longer in the spatial naming loop.
- Added `MobileCLIPNamer.swift`: loads `mobileclip_s0_image.mlmodelc`, reads
  82 normalized vocab vectors, accepts only score >=0.22 and margin >=0.02.
  Status line reports scan ms and words/min. Current starter vocab is
  `ops/spatial_vocab.txt`; offline builder is
  `scripts/build_vocab_embeddings.py`.
- Added the local Core ML image package at
  `soma-native-fastvlm/FastVLM App/mobileclip_s0_image.mlpackage` (22 MB) and
  vocab JSON (916 KB). NOTE: the builder downloads a hidden Hugging Face
  `.cache/` if run with image-model fetch; delete that cache before building
  because Xcode synchronized groups try to compile it.
- Permanence landed: spatial objects persist to
  `Application Support/SOMA/spatial_world.json`; ARWorldMap persists to
  `Application Support/SOMA/spatial_world.arexperience`; start reloads both,
  stop saves both. Upsert identity = same word within 0.4 m; sightings
  increments; position EMA = 0.8 old + 0.2 new; no cap/no decay/no deletion.
- Validation: Mac Debug build succeeds with
  `ASSETCATALOG_EXEC=/tmp/actool_wrapper/actool`. Device install was NOT
  verified: `devicectl` lists the iPhone as unavailable, and explicit
  destination build cannot see it. Forced iphoneos target build enters iOS
  toolchain but fails before app compilation in SwiftPM (`Jinja` cannot
  resolve `OrderedCollections`), likely an environment/package build issue,
  not from the new spatial files. Next session should reconnect/unlock phone
  and run the normal signed device build/install.
- Founder device finding 2026-06-12 after P2 install (`215cd25`): build stamp
  verified and spatial map works, but moved furniture exposed a permanence
  gap. A laptop re-seen after repositioning merged as the same laptop, while a
  suitcase/blanket behind the laptop's old position could duplicate or pin in
  the old room-frame context. This is not fixed by 3D rendering alone; next
  spatial identity work needs movable-object handling (stored object pose
  orientation/extent confidence, anchor/plane association, and "moved" vs
  "second object" decisions) rather than pure same-word distance.

## Open tasks (TaskList mirrors this)

- #5 IN PROGRESS — enrichment scheduler: mac live verification → 8h budget
  proof run (log enrichments/hour + facts-novel rate) → Swift port.
- #6 closed-set relationship classifier at import (evidence-gated; fine-tune
  ONLY if eval shows gemma classification insufficient).
- #7 group-chat enrichment (39 groups skipped; ZWAGROUPMEMBER.ZMEMBERJID joins
  senders; enrich EXISTING contacts only, no new entities, no commitments).
  User example to verify: Jascha in shared group.
- #8 WeChat import: screenshots at `"/Users/zer00/Desktop/Claude not code/Wechat/"`
  (PNGs → OCR); check `~/Downloads/Claude_analysis/files/WECHAT_FULL_TRANSCRIPT.md`
  first as a cheap path.
- Spawned chip (separate session): importer writes graph_attributes PLAINTEXT
  vs encrypted elsewhere — privacy audit.

## Standing decisions / constraints

- LLM use: import-time closed-set gates ONLY, temp 0; never generation in
  answers; never an unstable judge gating deletion of user data.
- Local workers: gemma3:12b-it-qat (gates), qwen2.5-coder:14b (bounded
  single-file transforms ONLY — proved incompetent at cross-module work).
  Don't run two ollama models concurrently with imports (GPU swap thrash).
- Auth header `X-SOMA-Token`; DB `soma_hub.sqlite3`; `with self._connect()`;
  no Flask; never Apple ID/password. Hub = test harness only (no server in
  product; phone is in-process library).
- SOMA_USER_NAME env for text-export imports (default "pranav");
  SOMA_COMMITMENT_WINDOW_DAYS (default 60).
- Re-import is idempotent (upsert by entity+key; same-JID zombies archived).
- Commit style: short imperative subject + measured rationale body.

## Cheap-execution playbook

- Tests + eval are the gates; run before and after every change.
- Probe real data empirically before theorizing (sqlite3 against 1.sqlite).
- One compact physical test at a time via the user; pipe outputs to /tmp
  files the agent can read.
- Background long imports (`run_in_background`), ~10 min each archive pass.

## ULTRACODE MARATHON (2026-06-13 ~06:45, Opus lead) — PIVOT VALIDATED ON HW

- **Capture pivot WORKS on hardware:** new capture_20260613_041423 = 12min
  4K, 21589 frames, 7197 ARKit poses, battery 80%->80% (ZERO drain),
  thermal nominal throughout. The phone-as-dumb-recorder is proven; the
  realtime build's thermal/"hub ok:38 stuck" wall is gone.
- **Offline pipeline (Mac understands) committed + fixed (80a965e):**
  Codex brief 11 fusion (walk_fuse_world.py + ingest_walk_world.py) +
  MPS labeler bug fixed (tokenizer.to(device)). Suite 124, north-star 1.00.
- **Office-walk evidence already in hand:** CLIP inventory 426 distinct /
  6796 instances (vs 24 on-device = ~18x density), BUT cross-checked vs
  gemma's 280-frame independent describe: 152 substring-agreed,
  274 CLIP-only (hallucination suspects: bedpan/razorblade/cloak in an
  office = forced-choice cosine garbage), 29 gemma-only (real vocab gaps:
  carpet/server/corkboard/cabinet). Buckets: /tmp/reconcile_buckets.json.
- **TWO ENGINES RUNNING (lead chilling):**
  1. GPU megascript /tmp/home_pipeline.sh (nohup, owns GPU serially):
     pull->extract->FastSAM->CLIP->inventory->fuse-with-poses->ingest->
     gemma cross-check. Log /tmp/home_pipeline.log. Outputs
     /tmp/home_inventory.json + /tmp/home_world.json. Watchdog armed.
  2. Workflow wf_6f383b1b-1a7 (offline-perception-audit, 8 agents, CPU
     only, no GPU contention): adjudicates 274 CLIP-only suspects real vs
     hallucination, writes /tmp/pivot_report.md (honest density+precision),
     reviews fusion code, drafts ops/CODEX_BRIEF_12_DRAFT.md.
- ONE-HEAVY-JOB LAW respected: only the megascript touches GPU; workflow
  agents read JSON/text only.
- NEXT WAKE: read /tmp/pivot_report.md + home_inventory; pick brief 12 P0
  (likely: gemma/VLM as primary namer, CLIP as prefilter — CLIP precision
  ~half); the honest trusted-object count is the founder deliverable.

## MARATHON CONT'D (07:00) — home world live + blur finding + brief 12 firing

- HOME WORLD LIVE: 408 pose-positioned objects ingested to graph + /world3d
  (179 distinct CLIP labels). Founder can navigate it NOW — but it's
  CLIP-contaminated (~50% hallucination, same as office).
- **CAPTURE-QUALITY FINDING (important):** the 12-min handheld walk is
  mostly motion-blurred — median frame sharpness 6, and the
  min-sharpness=40 gate kept only 55 of ~1440 frames (4% room coverage).
  THAT is the "identified not even 1%" cause for home, not the namer.
  Re-running at fps3 + sharpness12 (/tmp/home_recover.sh -> /tmp/home_*2)
  for richer coverage; brief-12 gemma-confirm gates the blur phantoms.
  FUTURE CAPTURE FIX (brief candidate): use ARKit pose angular-velocity to
  select LOW-MOTION frames (sharp by construction) instead of post-hoc
  Laplacian — the poses.ndjson already has the data. Also instruct founder:
  slower pans, brief dwells.
- Codex firing brief 12 (ops/CODEX_BRIEF_12_trusted_naming.md): gemma-
  confirmed naming + abstention, trust tiers, re-name home world, append
  10 gemma-only vocab words. Watched.
- NEXT WAKE: when home_recover done + brief-12 namer ready -> run
  walk_name_objects on /tmp/home_labels2.json -> trusted home world ->
  re-fuse -> the DEFENSIBLE home object count is the deliverable.

## TRUSTED HOME WORLD COOKING (07:09) — the marathon's payoff

- Richer home re-extraction (fps3/sharpness12): 491 distinct CLIP objects
  from 9422 crops (was 179 from 55 frames). More real objects AND louder
  hallucinations (razorblade 429, diaper, cloak) — proves the gemma gate
  is essential.
- Brief 12 namer COMMITTED + gated (17b8dfe): walk_name_objects.py
  (CLIP floor 0.28 prefilter -> serial gemma3:12b-it-qat confirm/rename/
  NONE -> trust tiers). Self-test + suite 124 + north-star 1.00 green.
  gemma vision tag verified; abstention confirmed (1st crop -> NONE).
- RUNNING (nohup /tmp/home_trusted.sh, ~2-3h GPU marathon): gemma-confirm
  on 5837 surviving crops -> /tmp/home_named2.json -> trusted inventory ->
  fuse w/poses -> ingest. Marker "TRUSTED DONE". Log /tmp/home_trusted.log.
- NEXT WAKE (when TRUSTED DONE): the deliverable = defensible home object
  count (trusted distinct vs CLIP's 491) + trusted /world3d (phantoms
  abstained out). Then: rebuild vocab embeddings for the +10 words
  (.venv/bin/python scripts/build_vocab_embeddings.py --vocab
  ops/spatial_vocab.txt --out 'soma-native-fastvlm/FastVLM App/Resources/
  vocab_embeddings.json'); founder views /world3d; compare trusted-home vs
  the 24 on-device. Capture-quality brief (pose-angular-velocity frame
  selection) is the next density lever.
- All engines idle except the trusted gemma run. Lead chilling.

## NAMER HANG FIXED (07:14) — trusted marathon relaunched

- First trusted run HUNG at 1 crop: home crops come from 4K frames (median
  438px, max 2622x2160); gemma vision on those is ~15-30s each -> the
  5837-crop run was a ~24h non-starter that looked hung.
- FIX (debf271): walk_name_objects responder downscales crops to 384px
  before gemma. Smoke: 8 crops in 43s (~4s/crop warm), 7 trusted/1 NONE-
  rejected -> trust tiering confirmed working.
- RELAUNCHED /tmp/home_trusted.sh at floor 0.30 (3006 survivors, ~3.3h),
  progress-every 20. Advancing (record 2 in 0.6s). Marker "TRUSTED DONE".
- NEXT WAKE: trusted home inventory (distinct vs CLIP 491) + trusted
  /world3d. Then rebuild vocab embeddings (+10 words) and the iOS app
  build is unaffected (server-side only). Capture-quality brief (pose-
  angular-velocity sharp-frame selection) remains the next density lever.

## REBOOT RECOVERY (10:44) — durable disk + checkpointing now mandatory

- 3rd memory-pressure reboot wiped /tmp at ~10:14, killing the gemma
  marathon at 6176/9422 (~2.7h lost — namer wrote only at end) and all
  /tmp crops/labels. Daemons died.
- SURVIVED (durable): data/walks/home_capture_20260613/ (video 1.08GB +
  poses.ndjson 3MB + meta) — the move-to-durable decision saved the run.
  data/walks/walk_office_jun11.mov intact.
- RECOVERED: daemons restarted (hub/dash/cockpit 200, cockpit cable-sync
  zombie already removed earlier). ollama up.
- FIXES committed (927227f): walk_name_objects.py now CHECKPOINTS — each
  named record appends to <out>.ckpt.ndjson + flush; restart skips done
  crops (resume: N loaded). Pipeline model tag -> gemma3:12b-it-qat.
- RELAUNCHED durable: scripts/run_capture_pipeline.sh on the home capture,
  out-prefix data/walks/home_capture_20260613/work/run, pose-selected
  frames (brief 13, ~332 vs 55), floor 0.30. Log: work/pipeline.log.
  Checkpoint: work/run_named.json.ckpt.ndjson — survives reboot now.
- RULES GOING FORWARD: (1) pipeline working data -> data/walks/*/work/
  NEVER /tmp. (2) long model loops MUST checkpoint. (3) one heavy GPU job
  at a time (reboots are memory pressure). (4) iPhone in restore = device
  unavailable; all work is Mac-side now so unaffected.
- Codex fired brief 14 (capture-session dashboard, read-only, cloud = no
  memory load) while pipeline runs.

## ONE BUG, BOTH SYMPTOMS (11:05) — crop-path double-prefix

- Pose pipeline "completed" in 4min with 0 trusted / 0 positioned. ROOT
  CAUSE (single bug): records store the FULL relative crop path; old
  _record_crop_path prepended crops_dir again -> nonexistent -> all 2119
  survivors marked missing_crop -> gemma_calls=0 -> 0 trusted. And fuse
  only positions trust==trusted, so 0 trusted cascaded to 0 positioned.
- FIX 84cf0c3: resolve crop path as-is first, re-root only if missing.
  Verified: crop resolves+exists. Fuse needs box+crop_path+timestamp;
  records carry 'box' and frame_NNNNNN_T.Ys naming gives timestamp ->
  positioning will work once trusted records exist.
- RELAUNCHED naming on EXISTING durable labels (no re-extract/segment):
  /tmp/resume_naming.sh -> work/run_named.json (checkpointed), then
  inventory+fuse+ingest. ~2119 survivors, ~3h. Marker "NAMING RESUME
  DONE". This is the deliverable: trusted distinct count + positioned world.
- 6901 crops from 332 pose-frames (vs 877 crops / 55 frames before).

## SPEED+QUALITY BREAKTHROUGH (autonomous, 2026-06-13 ~12:30)
- Root cause of "very very slow": naming 6901 crops individually with a 12B
  vision model, re-naming the same object dozens of times = 10+ hours.
- FIX: scripts/walk_cluster_objects.py — embed every crop once (CLIP, fast),
  group crops that are the same object, name each group once. 6901 crops ->
  1277 unique objects in 75 SECONDS. Margin is object-vs-junk so synonym
  ties keep real objects.
- Result on home walk: 708 clean objects, 227 types, 446 placed in 3D,
  ingested + on /world3d. Gallery with photos: home_gallery.html.
- Remaining ~7% phantoms (diaper/videotape/cloak/bedpan = CLIP fabric/dark
  misreads). Bounded vision-verify of the 708 survivors running in
  background (was the slow path, now bounded+checkpointed ~1h) ->
  home_*_verified artifacts.
- One-GPU-job discipline held (founder: reboot = our fault now).

## STEP-BACK + COCKPIT-THAT-SHOWS (2026-06-13 ~13:05)
- Founder called out (rightly): cockpit told instead of showed; count bug
  (901/700 from reading stale shard checkpoints); phone ask stale though
  phone was connected; GOAL too narrow ("objects in a room").
- LOOKED at the actual home crops myself: distinct objects correct
  (keyboard real), but crumpled fabric -> 'diaper'/'cloak', and a dark box
  that says SUPREME -> 'videotape'. KEY INSIGHT: text on things is half the
  meaning and the object-namer throws it away -> OCR/text-reading is now a
  first-class milestone.
- GOAL REFRAMED (ops/cockpit/plan.json): from "3D world of named objects"
  to "a private searchable memory of your world - objects, TEXT, places,
  later sound - ask anything, answered with the photo as proof, on-device."
- COCKPIT REWRITTEN to SHOW: embeds live /world3d iframe, shows real crop
  thumbnails with names (red-flags the misreads), real moving progress bar
  (correct count of 708 + 'updated Ns ago / LOOKS STOPPED' heartbeat),
  auto-detects the phone. /img endpoint serves sandboxed thumbnails.
- Protocol (ops/OPERATING_PROTOCOL.md) now actually run each turn:
  checks/captures/attacks + flood-fill.
