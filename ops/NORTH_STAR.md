# SOMA — North Star (canonical, rewritten 2026-06-14)

> The single source of truth for what we're building and how. If a task doesn't
> serve this, don't do it. Supersedes scattered goal statements.

## What it is
A memory you can question. SOMA senses your day through cheap, always-on
perception, turns everything into **words the instant it happens** — never keeping
one frame of video or one second of audio — and at night **thinks over those
words**, binding scattered facts into understanding. Later you ask anything; it
answers from that understanding, cites what it saw, and says "I don't know" when it
didn't perceive it.

## The machine — three stages
1. **CAPTURE** (live, cheap, parallel, no big model): each sense writes text as it
   happens — OCR (text), ASR (speech), sound-event tagger (cry/alarm/hum), sensors
   (motion/location/orientation), scene gist (small VLM, ONLY on attention/dwell/
   change). Raw pixels/audio discarded the instant the words are out.
2. **SLEEP** (nightly, the big model): congregate the day's words, dedupe, and
   BIND them by *when + where they co-occurred* — which hum was the laptop fan,
   which blue thing was the bag, which name belongs to which face. Tentative
   bindings carry a confidence; weak links are refused, not hardened.
3. **ASK**: answer from the bound words only. Cite. Refuse what wasn't perceived.
   Never re-open raw.

## Core principle (resolves the tension)
"Maximum context" and "detail follows attention" are in tension. Resolution:
**capture EVERYTHING cheaply (always-on narrow helpers) + perceive DEEPLY only
what attention marks.** Maximum *cheap* context + selective *deep* context. The
attention/salience SCHEDULER that makes that call is the moat — a first-class
component, not an afterthought.

## Method — how we find what to build
We do NOT guess helpers. We ask questions; the questions the system MISSES name the
next helper to build (the overnight self-play job automates this). RULE: nothing
gets built until a missed question demands it. (This rule kills detours like the
3D world-render that no question needed.)

## Honest critiques we must hold (devil's advocate)
- More signals ≠ better answers. Every added signal needs a confidence; the binder
  must refuse weak links or context becomes noise and hallucination climbs.
- Most moments don't matter — value is the FEW that do (keys, what the doctor said,
  did I lock the door, who was that). Salience-first, not uniform deep capture.
- Local models (gemma-12B / Qwen-VL-7B) may be the wall. Be ready to route SLEEP
  binding + ANSWER reasoning to a stronger TEXT-ONLY model (text-egress OK, raw
  never) and MEASURE when local quality stops being enough.
- Questions remain unconstrained and native. Do not create a fixed question-type
  product surface; use open-vocabulary typed observations, grounded retrieval,
  and calibrated refusal to drive hallucination toward zero.

## Metric
A stranger asks about your day and is amazed, with near-zero made-up answers.
RAS = (correct − made-up)/total; hallucination must approach zero.

Also report the oracle-answerability gap (OAG): among questions an offline oracle
with raw frames can answer, the percentage the on-device text memory cannot.
OAG separates capture loss from reasoning failure and must approach zero under
the real-time device budget. Raw media is oracle-only evaluation input; it never
enters production recall or leaves the device.

## Prototype tiers + timeline (constant work)
- **V0** — Mac-processed, generalizing, trustworthy (record → one command → ask →
  cited answers). **~3–5 days.** Hinges on local-model quality + a few real captures.
- **V1** — live, on-device, attention-gated, all-day (phone rig). **~2–4+ weeks.**
- **Glasses** — months.

## Current substrates (in order)
1. Outdoor walk (done — extraction+assembly proven; one scene, overfit risk).
2. **Live-digital vlog** (next — Claude drives a day-in-the-life vlog on screen,
   perceives the live stream, is the ceiling oracle). Tests perception+binding
   GENERALIZATION; NOT the live-egocentric loop (no sensors/egomotion — be honest).
3. Audio-rich moving walk (founder to capture — real-world generalization + audio).
4. Real phone-live capture with sensor streams (the V1 moat).
