# FULL CONTEXT HANDOFF — TRACE/SOMA (2026-06-27)
*Complete transfer of a long working session so a fresh chat continues seamlessly. Read top to bottom.*

## WHO / WHAT
- **Founder = Satoshi** (KIT student; thesis at Max Planck IPP Garching). Lives in a German apartment.
  Low-touch, near Claude usage limits, wants LOCAL LLMs used majorly (ollama gemma3:12b/27b),
  Codex sparingly. Values BRUTAL HONESTY over hype — explicitly called out hype this session.
- **You = "the Chief"** — autonomous engineer. cwd `/Users/zer00/Documents/VLM`. Branch
  `cleanup/repo-declutter-20260625`. Commit footer: `Co-Authored-By: Claude ...`.
- **The product (TRACE/SOMA):** a wearable/phone **continuous context engine**. Passively capture
  lived experience (derived text/numbers; raw frames go to the user's OWN Mac, perceived, then
  deleted — LOCAL trust boundary, not on-device-only). Ask ANYTHING later, answered honestly.
  **THE THESIS (founder, crisp):** answer LATER the questions people today answer by attaching a
  LIVE image to ChatGPT ("how much soya is this?") — from PASSIVE capture, no deliberate framing.

## THE FULL ARCHITECTURE (crystallized this session — build foundation-up)
```
[0] FRAME SUPPLIER (intake)  — 60fps in -> sharp keyframes + motion signal; DISCARD blur, keep
                               movement signal; adaptive rate; on-device; decoupled from slow loop.
[1] PERCEPTION              — VLM + helper society on the good frames (+ depth grid).
[1.5] COMPOUNDING BRAIN     — reconcile conflicting reads with ACTIVITY PRIORS (kitchen: keep soya,
                               drop rocks), carry CALIBRATED UNCERTAINTY -> honest-but-helpful.
[2] ACTIVITY CHARACTERIZER  — recognize WHAT the person is doing -> SPAWN domain specialists.
[3] DOMAIN SPECIALISTS      — chess(board/moves->opening), cooking(ingredient+amount), reading,...
 └─ SPINE (always on): SPATIAL-TEMPORAL substrate stamps EVERYTHING with (x,y,z,t).
    Binder ties helper outputs to coords/time; brain derives count/relations/answers LATER.
```
Key founder principle: **counting/identity is GEOMETRIC (distinct world coordinates), not semantic**
— so VLM mislabels corrupt the LABELS on nodes, not the NUMBER of nodes. Individuate by LOCATION.

## DEPLOYED STACK (as of end of session)
- **iOS app:** `trace-native-fastvlm/` (scheme "FastVLM App"), on iPhone 17 (UDID
  D3A506B2-8923-5313-B8A3-FF769ABBA228, also id 00008150-001460D83686401C), bundle `de.zer00.trace`,
  Xcode 26.3. Build: `xcodebuild -project FastVLM.xcodeproj -scheme "FastVLM App" -destination
  'platform=iOS,id=00008150-001460D83686401C' -allowProvisioningUpdates -configuration Debug
  -derivedDataPath build/dd build`; install: `xcrun devicectl device install app --device
  D3A506B2-8923-5313-B8A3-FF769ABBA228 "build/dd/Build/Products/Debug-iphoneos/FastVLM App.app"`.
- **Mac brain:** `scripts/trace_brain_server.py` on :8765. Launch:
  `TRACE_BIND=0.0.0.0 TRACE_BRAIN_PORT=8765 TRACE_PERCEIVE=1 TRACE_INSTANCE_PIPE=1 TRACE_EVENTLOG=1
  TRACE_DEBUG_FRAMES=1 PYTHONUNBUFFERED=1 nohup caffeinate -is .venv/bin/python
  scripts/trace_brain_server.py > /tmp/trace_brain.log 2>&1 & disown`. (Use .venv — has transformers
  4.49 / GroundingDINO / ultralytics. System python3 lacks numpy.)
- **389 tests green** (was 301 at session start).

## WHAT WAS BUILT THIS SESSION (chronological, with files)

### A. SPATIAL COORDINATE COUNTING (the big validated win)
Problem: "how many jars" gave "one jar" or "9 jars" — counting was broken. Root cause traced
through layers: text/appearance dedup fails because the per-crop VLM reads the SAME jar differently
each frame. SOLUTION = world-coordinate individuation:
- `scripts/world_binder.py` — project each detection's box to world (x,y,z) via the phone's depth
  grid; cluster by 3D location into distinct nodes; count = distinct nodes. (`bind_world_instances`,
  `sample_world`, `count_of`.)
- `scripts/node_merge.py` — ANISOTROPIC jitter merge: depth(z) is the NOISY no-LiDAR axis, bearing
  (x,y) reliable. Merge same-type same-brand nodes tight on x,y (0.13m) loose on z (0.22m, stable
  band 0.18-0.25). Fixes one jar split into many by depth jitter.
- `scripts/spatial_relations.py` — left/right/above/on-top/next-to from world coords (the
  "relational helper").
- `scripts/perception_consensus.py` — tier nodes confirmed(>=2 frames) vs provisional; one-off
  hallucinations demoted.
- `scripts/screen_quarantine.py` — a detection inside a screen-type box (laptop/monitor) is
  on-screen content, bound to the screen, NOT a phantom physical object. (Caveat: fails when ZOOMED
  INTO a screen — detector sees content not frame.)
- iOS: `TraceARKitEngine.depthGridSnapshot` raycasts an 8x6 grid -> world points (feature points +
  estimated planes, no LiDAR on iPhone17 base); attached to streamed frames; brain saves `.depth.json`.
- **VALIDATED ON A REAL PHYSICAL SHELF (no screen): 3 nutella, 1 pesto, 1 pringles — ALL CORRECT,
  laptop refused.** This proved the architecture. (Tuned on n=1 scene; n>=100 number still pending.)

### B. PERSISTENCE (founder mandate: never lose memory)
- Brain persists `instance_graph.json` (coordinate nodes + relations + frame accumulation) after
  each perceive, reloads on startup (`_persist_instance_graph`/`_load_instance_graphs`). PROVEN:
  `IGRAPH-LOAD moment=live nodes=29` on restart. (kf_memory.json + events.db already persisted.)

### C. ACTIVITY-AWARE LAYER (the "helper-identifier" the founder described via chess)
- `scripts/activity_identifier.py` — recognizes cooking/chess/reading/coding/shopping from
  perception cues -> dispatches specialists.
- `scripts/activity_dispatch.py` — glue: identify -> reconcile node identities -> run specialists.
- `scripts/specialist_cooking.py` — ingredient + utensil + HEDGED amount. "how much soya" ->
  "~half a bowl (≈250 ml), rough visual estimate, no scale."
- `scripts/specialist_chess.py` — move list -> opening. "what opening" -> "Scandinavian Defense".
- `scripts/specialist_reading.py` — title/numbers/entities. "what dose" -> "50 mg".
- Wired as brain **Source 2.5** in `_ask` (`_moment_perception` builds the perception dict).

### D. COMPOUNDING BRAIN (founder's key refinement to the honest boundary)
- `scripts/context_reconciler.py` — `reconcile_node(reads, activity, plausibility_fn)` uses an
  activity prior to KEEP the plausible read + DROP the implausible (kitchen: keep soya, drop rocks),
  carries calibrated uncertainty. `phrase_uncertainty` -> "not certain it was soya, but if it was,
  ~250 ml". Wired into `activity_dispatch.analyze(perception, nodes, plausibility_fn)`.
- Brain `_plausibility(candidate, activity)` = local-LLM (gemma) prior, cached. Proven: node read
  'rocks'/'soya'/'soya' in cooking -> reconciled to soya -> "how much soya" answered.
- `scripts/identity_consensus.py` — assert identity only when frames AGREE; nutella(agree)=reliable,
  soya/scallops/paper-bag(disagree)=unreliable -> hedge.

### E. FOUNDATION HARDENING (frame quality)
- `scripts/frame_quality.py` — Laplacian-variance blur gate. VALIDATED on real frames: blurry pan
  1-28 rejected, sharp 270-482 kept (threshold 60, clean gap). Wired into brain `_frame_is_usable`.
- iOS `FrameSupplier.swift` — motion-aware keyframe selection (emit when attitude settles) +
  movement signal + on-device blur gate (`sharpness`, same Laplacian method, threshold 60).

### F. FULL-VIDEO CAPTURE (last thing built — founder demanded it, was furious it wasn't there)
- `trace-native-fastvlm/Video/VideoRecorder.swift` — taps the raw 30fps sample-buffer stream via
  AVAssetWriter, records the ENTIRE video to `.mov` (NOT sparse keyframes). On app background:
  finalize + upload to brain `/debug/video` (background task). Saved under
  `data/phone_captures/live/video/`. CameraController.captureOutput feeds it.
  ⚠️ STANDARD (AVCapture) MODE ONLY — ARKit/spatial mode feeds a different path, not yet wired.
  ⚠️ Upload is on-background with ~30s budget — a long video may not finish; switch to background
  URLSession / chunked upload if it fails. NOT YET VERIFIED end-to-end (founder testing it now).

## CRITICAL PITFALLS / OPEN PROBLEMS (the honest state — DO NOT HYPE)
1. **CAPTURE WAS CATASTROPHICALLY SPARSE.** A 9.5-min real video -> only 26 keyframes (0.05/sec).
   The vision loop is ~0.5fps AND the supplier kept ~9%. This is WHY full-video capture (F) was
   built. The supplier (blur+motion gate) over-aggressive on a slow loop. TRUE 60fps decoupling
   still not done.
2. **PERCEPTION FLOOR is the gate.** On a real messy kitchen the VLM misread soya as
   "scallops/paper bag/cat food", bowls as "pressure cooker". Clean/close/branded (nutella shelf)
   WORKS; messy/reflective/transparent/distant FAILS. The compounding brain + consensus make it
   honest (hedge/refuse) but can't fix genuinely-hard recognition.
3. **It's IMAGE vision per-frame, not VIDEO/motion understanding.** Founder wants VLM over the
   actual video (movement, actions: "scooped an amount"), not stills. NOT BUILT.
4. **Coordinates-across-visits memory** ("go back to kitchen, recall last kitchen memory to build
   on") — the spine + persistence exist but this cross-visit recall isn't demonstrated/wired as a
   feature. Founder asked for it explicitly.
5. **iOS frame rate**: ~0.44-0.5 fps loop is the bottleneck under everything.
6. GroundingDINO MPS path crashes on some frames (Metal resize assertion) -> force CPU for batch
   (`torch.backends.mps.is_available = lambda: False`).
7. Speech STT: 1st utterance right, 2nd garbled; no confidence gate.
8. ARKit + AVCaptureSession CANNOT share the camera (no multitasking-cam entitlement) -> black/
   rotated frames. Reverted to AVCapture; ARKit behind a `spatialMode` toggle (default OFF). Depth
   grid + world coords only flow in spatial mode -> tension with video recording (standard only).

## HARD-WON FACTS (don't relitigate)
- Frontier-look "it works" on one curated photo != works on real messy capture. Validate on REAL
  frames every time. The founder filming a LAPTOP SCREEN showing our chat caused "nutella" ghosts
  (screen contamination) — physical captures (no screen) are the clean test.
- Codex (`codex exec --sandbox workspace-write -c approval_policy=never - < brief.md`) HIT ITS
  USAGE LIMIT mid-session; some modules (node_merge) were hand-written. Codex commits but never
  updates docs. Local gemma is the runtime LLM (ollama :11434).
- Validation scripts live in the SESSION scratchpad (rotates!) — `validate_cached.py` caches
  perception so merge-tuning is instant; forces CPU detector.

## IMMEDIATE NEXT STEPS (founder's stated order)
1. **VERIFY FULL-VIDEO CAPTURE WORKS** (founder is testing: record in standard mode -> background app
   -> check `data/phone_captures/live/video/*.mov` arrived complete). If upload fails for long
   videos, switch to background URLSession or chunked/segmented upload.
2. THEN (founder: "we can work later"): video/motion VLM understanding; coordinates-across-visits
   memory; true 60fps intake; perception accuracy on hard objects.

## PROGRESS BAR
`ops/cockpit/pitch_progress.json` (gitignored) ~90%. But honest: the activity-aware + compounding
+ spatial pieces are BUILT & unit-proven; the END-TO-END product on real long captures is NOT yet
working (sparse capture + perception floor). The founder is (rightly) unimpressed with end-to-end.

## MEMORY FILES (read these — auto-loaded index in MEMORY.md)
frame-supplier-and-full-stack-20260627, spatial-context-engine-plan-20260626,
arkit-avcapture-camera-conflict, moat-local-boundary-and-async-qa, tough-battery-findings-20260626,
product-extent-do-more-not-less, anti-tunnel-leash, founder-operating-contract.
