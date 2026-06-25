# CONTEXT SPRINT — 2026-06-23

*Author: the Chief. Founder: Satoshi. Branch: `chief/p0-honesty-sprint`.*
*Supersedes the "narrow to OCR" framing for the pitch prototype. The narrowing was a*
*Mac-side eval crutch; the real product already exists in Swift and is bigger.*

## THE CALL (founder, 2026-06-23)

Stop polishing the OCR eval. The product is a **CONTEXT engine** — spatial, voice,
place, cross-frame fusion, the works — not a text reader. Build a sprint that
**shatters the pitch-prototype progress bar**, with heavy work on the Swift app.

## WHAT I FOUND (this is why the call is right)

The native app `trace-native-fastvlm` is **already a multi-modal, on-device context
engine** and was validated on-device in **Munich on 2026-06-04** (`TRACE_NATIVE_LIVE_REPORT.md`):

| Channel | Evidence (2026-06-04 on-device run) |
| --- | --- |
| FastVLM vision | 102 observations |
| YOLO detector + tracking | 29, multi-track |
| Vision OCR | 40 records *(but acceptance = 0 — bug)* |
| Apple Speech / Whisper | transcript: "Trace, test, Benson." |
| CoreLocation + reverse-geocode | GPS 48.256, 11.610 → place name |
| **Fusion digest** | active/stable/provisional/stale facts, **seen-counts ("seen 252x")** |
| Privacy | **0 raw media** (audit PASS) |

`TraceLiveContextEngines.swift` has real, working `TraceAudioContextEngine`
(on-device Apple Speech on iOS + local whisper.cpp on Mac, commit-if-useful dedup)
and `TraceLocationContextEngine` (CoreLocation + geocoder). The "seen 252x" digest
**is the consensus / frequency=confidence principle already living in the app.**

**Conclusion:** we are not greenfield and not even "resurrect dormant scripts." The
multi-modal engine exists. The sprint = **light it up, harden it, apply one honesty
discipline across every channel, build the missing spatial channel, fuse cross-modal,
and prove it with a number.**

## THE UNIFYING IDEA (keeps the moat while widening the aperture)

Consensus was never an OCR trick. **"Frequency = confidence; refuse the one-off"** is
how you get honesty out of *any* noisy channel. Apply it everywhere:

- **TEXT** — cross-frame OCR consensus *(done)*.
- **SPATIAL** — a relation (left-of-me / held / near) must hold across frames or stay silent.
- **VOICE** — a line is committed only when clear + stable; mumble → refuse, never invent.
- **OBJECT/STATE** — seen-count threshold before it's a fact *(digest already does this)*.
- **FUSION** — bind read + heard + place + around into one episode; that is the CONTEXT
  no single frame holds (the founder's "gathering context from partial frames").

So: widen to full multi-modal context, and **no always-emitting channel is allowed to
manufacture a lie.** Every answer is grounded-or-refused, and a refusal names the
missing channel.

## THE REDEFINED BAR (what "shatter the progress bar" means)

Old bar: 73% — but against a narrow text-recall target you rejected.
New bar: **45% toward the multi-modal context engine** (`ops/cockpit/pitch_progress.json`).
Honest reset to the right target; the sprint drives it up fast. 11 milestones:

1. native_build — app builds & signs for iPhone 17 (Xcode 26.3)
2. multimodal_capture — vision+detector+OCR+speech+location live on device
3. fusion_digest — active/stable/provisional/stale + seen-counts *(done; harden)*
4. privacy — typed memory only, 0 raw media *(done)*
5. honest_gate — grounded-or-silent on EVERY channel
6. spatial — egocentric relations channel **(named gap)**
7. crossmodal — episode binding, queryable
8. ondevice_ask — ask → cited answer / honest refusal, on device
9. voice — hardened commit + speaker hint
10. demo — multi-modal narrative + cockpit
11. number — trustworthy multi-modal score (answer / refuse / lie)

## WORKSTREAMS (task board WS0–WS7)

- **WS0** Verify native hero builds + deploys today. *(in progress; see Day-0 finding)*
- **WS1** Re-verify live multi-modal capture on device; fix OCR acceptance=0.
- **WS2** Generalize the honest gate across all channels.
- **WS3** Build the egocentric spatial-relations channel.
- **WS4** Cross-modal binding into queryable episodes.
- **WS5** On-device Ask → cited answer / honest refusal, verified on device.
- **WS6** Pitch surface: redefined bar (done) + cockpit + multi-modal demo script.
- **WS7** Trustworthy multi-modal capture + founder gold + the number (the gate).

## HERO DEMO (the moment that must land)

A short **Munich walk** (the founder's real city). The phone passively perceives
across vision + OCR + speech + place. Then ask the things **only a context engine can
answer**, and watch it ground or honestly refuse:

- "What did that sign say?" → OCR consensus.
- "What did they just say / what name did they give?" → voice.
- "What's to my left / what did I just walk past?" → spatial.
- "Where am I?" → place.
- "What was the price on the menu I looked at near the church?" → **cross-modal fusion.**
- one unanswerable → refusal that **names the missing channel** (not a guess).

A captioner-with-a-camera refuses or lies on most of these. A context engine does not.

## OPERATING MODE

Max-load local LLMs (ollama gemma3:12b/27b) + Codex (`codex exec --full-auto`) for
bounded plumbing/tests; Chief = judgment, orchestration, verification, recording.
**Do NOT hand the 2868-line brain or the Swift engine to blind full-auto** — bounded
briefs only, and the Chief re-verifies every result (agent self-tests ≠ verification).

## DAY-0 FINDING (honest)

Native app **built for device yesterday** (BuildStamp `f0df532`, 2026-06-22), so deploy
is unblocked (the "Metal-blocked" memory is stale). BUT a **clean-room compile today
FAILED** on a SwiftPM dependency-resolution issue in the MLX package graph
(MLXLMCommon → Hub/Tokenizers/MLXNN/... unresolved). Likely a clean-DerivedData /
package-resolution artifact, not a source regression. **WS0 is red until a clean build
is green** — diagnosing first; no green claimed until proven.
