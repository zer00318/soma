# MORNING HANDOFF — Pitch Day (2026-07-01)

*Written overnight by the Chief while you slept. Read this first.*

## TL;DR
- ✅ **A bulletproof, offline, zero-latency demo is built and verified** (`ops/demo/demo.html`).
  Open it in a browser. Every answer is the REAL local engine's output over a genuine capture
  of your room — pre-computed so nothing can dice-roll or stall on stage.
- ✅ **The two pillars are solid and real:** verbatim recall of high-confidence objects, and the
  honesty moat (it refuses what it never saw — wifi password, passport, etc.).
- ⛔ **ARKit / exact-counting is NOT in the demo** — see "The ARKit blocker" below. It needs YOU
  awake to do one instrumented capture. The mechanism is built and proven; only the capture is blocked.

## How to run the 3-minute demo
1. Open `ops/demo/demo.html` in any browser (double-click it). No server, no network needed.
2. Follow `ops/demo/PITCH_SCRIPT.md` — tap each question card in order; the answer reveals with a
   GROUNDED (green) or WON'T-INVENT-IT (amber) badge + the evidence it's standing on.
3. Optional live flex at the end: `.venv/bin/python scripts/trace_prototype.py ask \
   data/trace_store_prototype2.sqlite3 "<any question>" --model gemma3:12b-it-qat`
   (slower, ~30s, and can occasionally garble — only do this if you're comfortable).

## What is REAL (no spin)
- The pipeline runs end to end, fully local: capture → observer triage (keeps ~8-12% of frames) →
  crop-zoom + scene perception (gemma-vision) → binder authors cited memories → local-Gemma answers.
- Raw frames are deleted after perception; only derived text persists. The privacy story is true.
- 0% confident-wrong held across every test — the honesty floor is the moat and it works.

## What is NOT solved (so you're never caught off guard)
- **Perception misreads.** gemma-vision sometimes invents a one-off label (a jar read as "burrito").
  The demo sidesteps this by asking about HIGH-CONSENSUS objects (seen many times) and by the
  honesty floor. Do NOT ask the live demo "list everything in my room" — it will surface a misread.
- **Exact counting needs real 6-DOF coordinates** (the Nutella-jar-count goal). The binder logic is
  built and proven (distinct coordinates → distinct instances → deterministic count), but ARKit
  never tracked, so we don't have stable coordinates. See below.

## The ARKit blocker (your one morning task, ~10 min)
Two recordings tonight both got stuck in `"Limited: relocalizing"` — ARKit never locked on, so no
usable coordinates/depth. I built an instrumented app build that now SHOWS the tracking status on
screen (a coloured dot + "ARKit: …" + a Reset button), so you're no longer recording blind.

**It is built but NOT installed** — the install hung waiting on an on-device trust dialog while you
were asleep. To finish it:
1. Unlock the phone, keep it awake and in view.
2. Run `bash scripts/deploy_ios.sh` and **tap the trust/install dialog the instant it appears.**
3. Open the app → Hub Setup → "Spatial mode (ARKit)" on.
4. Watch the new on-screen status. Tap **Reset**, then hold still / pan slowly until the dot turns
   GREEN ("ARKit: Tracking"). Only THEN start the capture, and do a slow deliberate pass over the
   5 Nutella jars.
5. Hand me the capture; the coordinate-counting pipeline (`scripts/build_coord_store.py`) is ready
   to run on real coordinates and should finally count the jars.

If ARKit still won't lock after this, that's a real hardware/environment limit and we ship the demo
as-is (recall + honesty) — which is already a strong pitch.
