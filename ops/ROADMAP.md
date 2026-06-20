# TRACE — Implementation Spec & Macro Roadmap (CANONICAL)
*Chief's plan · v2 · 2026-06-17 · supersedes scattered goal statements*

> **This is the single source of truth.** Every session STARTS by reading this and
> ENDS by updating it. If a task doesn't serve this, it doesn't get done.
> `ops/OPERATING_PROTOCOL.md` is superseded (it pointed at a dead "3D world" goal).
> `ops/NORTH_STAR.md` remains valid background; this file governs execution.

## 0. Prime directive
**Reconstruct lived experience as lossless context, then make it answerable.** Every
choice serves one question: *did the brain have everything it needed, as if the video
and audio were still present?* Raw pixels/audio are discarded the instant they're
converted to text; the derived context is what must be lossless.

## 1. Problem / who it's for
The valuable artifact was never the footage — it was the bound, queryable *meaning*.
TRACE captures meaning and discards the medium. **This prototype's audience is one
person: the angel.** Its job is to prove the **moat** (architecturally incapable of
surveillance) and the **market** (empty quadrant, named acquirers). It is NOT a
recorder, an assistant, a 3D renderer, or "answer anything at 50%."

## 2. The central hypothesis (UNVALIDATED — this is the whole game)
> Perception can be decomposed into channels that reconstruct *lossless-enough
> context* — the complete continuous spatial/temporal/audio scaffold from genesis —
> such that a tractable brain answers arbitrary retroactive questions, **including hard
> spatial ones**, at near-zero hallucination.

We validate this. We do not assume it.

## 3. The instrument: every failure is diagnosed (A) or (B)
- **(A) Context not lossless enough** — the fact was never captured/derived → discover a new channel.
- **(B) Brain couldn't use it** — the fact was in the store but the brain didn't reach/hold/reason over it → token/navigation/reasoning wall.

Every answer logs *what the brain looked at*, so (A) vs (B) is mechanical, not a guess.
If we can't tell them apart on a miss, we're blind. This separation is the backbone.

## 4. Method: sufficiency → necessity → efficiency (in order)
1. **Sufficiency (brute force, offline).** On a recorded clip, thermal/token limits
   don't apply. Throw the kitchen sink: deep VLM every frame, full pose/IMU/GPS track,
   OCR every frame, full audio. Ask only: *can the brain answer the hard set at ~0
   hallucination?* Isolates "does it work at all" from "can we do it cheaply."
2. **Necessity (ablation = "capture all, discard what doesn't add").** Remove one
   channel at a time, re-score. Removal that breaks no answer = not load-bearing for
   this set. This DISCOVERS the helper set empirically — open-ended, never capped by
   guesses. Pruning is measured, never intuited.
3. **Efficiency (last).** Only once we know what's necessary do we bring back the
   salience scheduler to approximate it cheaply for live/glasses.

## 5. Architecture (lossless context → answerable)
- **CAPTURE from genesis.** Cheap channels — camera pose/tilt/pan/motion (IMU),
  GPS/place, audio events, ASR, OCR, scene gist — kept *losslessly and continuously*
  from the first instant (they're tiny). Deep-visual is the only rationed channel, and
  offline we don't ration it. **Egomotion is a first-class input to the brain, not a
  nightly afterthought** — it is what answers "which floor / which side," the validated
  form of the spatial insight the 3D render botched.
- **THE LOSSLESS STORE (never discarded).** Complete scaffold on disk, time- and
  entity-indexed. Losslessness lives in storage + retrievability, not in any one
  context window.
- **THE BRAIN = agentic reasoner over the store.** It can't swallow the day in one
  prompt, so it navigates — timeline, egomotion track, deep visual notes for a moment,
  cross-check audio — iteratively, until it answers WITH CITATIONS or HONESTLY REFUSES.
  Local-first (Gemma3 + Qwen2.5-VL); **text-egress hatch** swaps a frontier text model
  when local is the wall — measured against local, raw never leaving.
- **NIGHT-BIND = accelerator, not gatekeeper.** Nightly dedup/binding builds an index
  over the lossless track with per-binding confidence (weak links refused). It speeds
  navigation; it is NEVER the only path to context — the brain can always fall back to
  the raw scaffold.

## 6. The proving ground
The **92s outdoor-walk clip + its 25-question adversarial set** (`walk_outside_20260614`).
**Honest baseline (scored 2026-06-17 from the frozen Jun-14 answers, SPRINT variant):
RAS 40.0 / 27.3% hallucination** — 16 correct, 6 wrong, 3 refused. (The "41.7" seen live
earlier was only 12/25 scored; 40.0 is the full-25 truth.)

**Headline diagnosis: 8 of 9 misses are (B) BRAIN, only 1 is (A) missing-channel.** The
wall is the binder/brain mis-using context it ALREADY captured — wrong-object binding
(Q2/Q10/Q18), confident-wrong binaries (Q17 zip, Q24 draft), bad counting (Q3), retrieval
misses (Q12/Q25) — NOT missing sensors. The ONE sensor that unlocks currently-impossible
questions is **head-pose/egomotion** (Q8/Q11 spatial, correctly refused today).

Two workstreams follow: **goal #1 = drive hallucination 27.3% → ~0 by fixing the brain**
(biggest lever); **goal #2 = add head-pose so the spatial demo questions become
answerable**. New captures/sensors are EARNED by diagnosed (A) failures only.

## 7. Done bar & invariant
- **Coverage:** one hero capture handled impressively across its full adversarial set.
- **Anti-overfit guard:** a cold second capture passes a private regression check
  before we pitch (so the live "ask anything" kicker can't faceplant).
- **Invariant across all phases: hallucination → 0.** A confident wrong answer is
  catastrophic; an honest "I don't know" is a win. **RAS = (correct − made_up)/total.**

## 8. Pitch deliverable (moat + market)
Fixed demo + live kicker: (1) hero clip answered with citations; (2) **no-raw-media
proof panel** — frames convert to text and are deleted on screen, store shown
text-only (surveillance made structurally impossible, live); (3) live "ask it
anything," where an honest refusal is a feature; (4) one market beat (empty-quadrant
table + acquirers, from `MARKET_AND_SCOPE.md`).

## 9. Roadmap (phases → gates)
No deadline → optimize for readiness in tight weekly cycles.

| Phase | Work | Gate |
|---|---|---|
| **0 — Baseline & instrument** *(now)* | Pin exact 92s clip + 25Q. Wire the (A)/(B) diagnosis log on every answer. Reproduce 41.7/27.3 cleanly. Establish this file as source of truth; retire stale protocol. | Honest baseline + diagnosis log + one source of truth. |
| **1 — Sufficiency** | Brute-force maximal offline capture; run agentic brain; score; tag every miss (A)/(B). | Clean answer to "does lossless context + brain work at all?" with each failure diagnosed. |
| **2 — Close (A)s, kill hallucination** | Build only the channels failed questions demand (likely real pose/IMU/GPS for spatial). Tighten refusal gate until made_up ≈ 0. | Hallucination ~0; spatial answered or honestly refused. |
| **3 — Close (B)s** | Where context was present but unused: improve navigation/indexing, or invoke measured text-egress brain. | No unexplained (B) failures on the set. |
| **4 — Necessity + harden** | Ablate to load-bearing channels; drop the rest. Build moat-proof panel; pass cold second-capture test. | Anti-overfit guard green; known-minimal channel set. |
| **5 — Package** | Demo script + moat-proof + market beat, rehearsed end-to-end. | Founder can run the whole pitch without the Chief in the room. |

**Founder's low-touch rituals (the only things needing human hands):** record clips
(with real-sensor capture), write/extend adversarial questions, run one command,
occasionally capture extra parameters when a miss demands it. Everything else — capture
pipeline, helpers, ablation, scoring, night-bind, doc-keeping — is the Chief's and the
machine's, 24/7.

## 10. Governance — the anti-diversion law
1. **One source of truth:** this file. Read first, update last, every session.
2. **Plan-gate:** before any build, name the roadmap item + the missed question that
   authorizes it. No authorization → not built. (Kills the next "3D render.")
3. **Missed-question rule:** helpers are earned by diagnosed (A) failures, never
   imagined or enumerated ahead.
4. **Verify before claiming:** render the artifact / run the query / read the number.
   No "it works" without proof.
5. **Firepower:** Chief builds solo by default; big well-defined sweeps get a
   multi-agent push only after the founder says yes.

## 11. Risks tracked
Refusal not generalizing past one scene (→ cold test); real-sensor capture is a true
dependency for the spatial story (this clip has real audio but no pose track yet —
likely the first (A) we hit); local brain ceiling on hard chains (→ measured
text-egress); moat only as strong as it is provable (→ software proof panel now,
hardware attestation post-prototype).

## 12. Status log (append every session; newest first)
- 2026-06-18 (COLD TEST + ROOT CAUSE + PROMPT-TUNING DEAD-END) — Founder dropped a cold clip
  `day_in_life_20260618` (58s montage: speech, a lecture screen, a game HUD, food, brands,
  self-attributes) = the Phase-4 anti-overfit gate. Built full ingest (added the missing SPEECH
  channel: local mlx-whisper → `asr.json`, wired into `load_transcript`). **Honest cold RAS 15.8 /
  20% halluc.** Auto (A)/(B) diagnosis (`scripts/diagnose_ab.py`): **12 of 15 misses were (B)
  BRAIN (captured-but-unused), only 3 (A)**. ROOT CAUSE: the assembler (the all-channels reasoning
  core) was **crashing on EVERY question** (`where` was a list, dossier builder assumed str) and the
  crash was **silently swallowed** → every Q fell back to the OCR-only legacy path → mass false
  refusals. The "brain that reasons over everything" wasn't running. FIXED (`_flatten_text` +
  loud-logged fallback), raised dossier caps (KF_MAX 8→16, per-channel 6→10, num_ctx 8192→16384).
  Then tested whether **prompt-tuning the leash** could recover recall safely: **NEGATIVE — RAS
  15.8 → 10.5 (loosened) → 0.0 (uniqueness-guard); halluc 20%→37.5%→50%.** gemma-12B does NOT
  reliably obey an accreting rule-prompt; each edit got differently-wrong. CONCLUSION (founder's
  "bandage" critique, proven with data): **prompt-tuning the leash/gate is ABANDONED.** Reverted the
  prompt experiments; kept the structural fixes. Two distinct hallucination sources, neither fixable
  by prompts: PERCEPTION errors (walk: phantom train/bag = 4-bit captioner) and MIS-ATTRIBUTION
  (day Q13/17/18: right token, wrong entity). DECISIONS LOCKED: perfect-recall exocortex (never
  delete; decay = retrieval cost); helpers = society of parallel aspect-specialists (live-budget),
  brain unbounded; building on recorded videos, not live yet. SHIPPED: progress-first **steerable
  cockpit** (steer/interject inbox + ack read-back, report-stuck, live ETA, heartbeat;
  `cockpit_client.html` + `/api/state` + `/api/steer`; legacy object-naming UI deleted); run_live ETA.
  NEXT = **Sprint 1: structural brain** — replace the prompt-gate with provenance+confidence+entity
  binding (the founder's neuron-graph), verified on ≥2 clips, built for live.
- 2026-06-17 (v3 — best yet) — **RAS -4.0 / hallucination 53.8%** (6 correct / 7 wrong / 12
  miss). Trajectory: v1 -8/55.6 → v2 -12/58.8 (raw signals REGRESSED: crowd-from-sound,
  zip-closed) → v3 -4/53.8 (BINDER DISCIPLINE recovered+surpassed). v3 = semantic binding
  (local sentence-transformers, ollama embed broken) + audio relative-spike + temporal dwell +
  **visual egomotion** + **grounding gate ON** + state-refusal clause. WINS: Q11 lift="left"
  CORRECT from pure optical-flow egomotion (no sensor); Q12 crowded now honestly refuses.
  Validates North Star "more signals need a binder that refuses weak links". COSTS: gate
  OVER-refuses 2 correct (Q6 location = same place/multiple names; Q15 years) → tune to recover
  ~+2. STUBBORN: Q14 (gemma still writes Röntgen though Fischer ranks #1 = reasoning-binding);
  Q17 zip / Q18 bag / Q20 "train" = 4-bit captioner perception errors → captioner upgrade.
  OPEN: bag blue-vs-white (pixels+VLM say white). Next: gate-tune → Q14 reasoning → captioner.
- 2026-06-17 (BASELINE) — First HONEST restored number on the CORRECTED gold:
  **RAS -8.0, hallucination 55.6%** (correct 8 / wrong 10 / miss 7). The old "40" was vs a
  broken gold (free passes Q1/Q8/Q11, accepted wrong answers) — THIS is the real floor.
  Breakdown: **~8 (B) brain-wiring** (answer is in the OCR, wrong binding: Q14 Fischer-vs-
  Röntgen, Q2 elevator-vs-station, Q10, Q16, Q22, Q25, Q12, Q7-temporal) → FREE fixes;
  **~3 caption hallucinations** (Q9 starry-night, Q18 bag-black-not-blue, Q20 mural-as-train)
  → captioner upgrade; **~6 (A) missing-channel** (Q1 audio-yell @~89s detector missed,
  Q8/Q11 spatial egomotion, Q17 zip, Q23 screen-notif). DATA: OCR channel is STRONG (read
  Röntgen/Fischer/Sauer/elevator-sign/Max-Planck verbatim); the wall is binding + captions.
  NEXT: implement Phase-2 binding fix in build_evidence_dossier → re-measure (target: halluc
  down). On-device tests blocked on founder installing full Xcode (devicectl/xcodebuild).
- 2026-06-17 (rebuild+gold) — Restored the stack fully (ollama+gemma3:12b+bge-m3+venv;
  brew dead on Ventura → official ollama binary; transformers pinned 4.49 for mlx-vlm 0.1.15).
  Rebuilt memory from the recovered clip `IMG_4045.MOV` (= the original 92s walk; audio channel
  reproduced gold exactly: -47.6dB, usable_sound=false). **Founder RE-ANSWERED all 25 Qs directly
  → caught 2 GOLD ERRORS:** Q1 (a child was *visibly* yelling near the end — audio silent, so the
  prior gold "no" was WRONG) and Q9 (the blue poster is the **W. Meißner / Meissner-Ochsenfeld**
  poster — prior gold "iceberg mural" was a hallucination IN THE GOLD). Refined Q2/Q16/Q19/Q24.
  **ARCH SHIFT (founder):** Q8/Q11 are ANSWERABLE from the VISIBLE camera pan/tilt (VISUAL
  egomotion), NOT auto-refuse → adds a visual-odometry helper to Phase 1 (try on existing clips
  before any sensor re-capture). Corrected gold backed up; live 25Q eval vs corrected gold running.
- 2026-06-17 (sprint) — Found the machine RESET to code-only: runtime (ollama+models+
  venv), the hero clip `Test.MOV`, its frames, and `world_memory.json` are all WIPED.
  Restore in progress (ollama + gemma3:12b pulling). Agent team delivered: honest
  baseline **RAS 40.0 / 27.3% halluc (SPRINT, full 25)**; **8/9 misses are (B) BRAIN**,
  1 is (A) missing-channel (scene-ID); capture + brain pipeline runbooks; pose-ingest
  design in flight. Phase-2 brain-fix design running as a workflow. NEXT: founder's clip
  → rebuild memory → re-confirm live → apply + test brain fixes.
- 2026-06-17 — ROADMAP v2 ratified ("Go"). Phase 0 started: source of truth locked,
  baseline + (A)/(B) diagnosis instrument. (Superseded by the sprint entry above.)
