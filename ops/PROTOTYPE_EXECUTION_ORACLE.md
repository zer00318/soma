# PROTOTYPE EXECUTION ORACLE
*The single dictating document. Read it BEFORE every work cycle. If a task does not advance a
CRITICAL-PATH item below, it is improvement / stall / regress — name which, and justify or stop.
This supersedes scattered status notes. Updated 2026-06-25 eve.*

---

## 0. THE LOCK (what the product IS — does not change)
A wearable **continuous context engine**. The phone perceives lived experience ON-DEVICE (rich,
multi-helper), keeps **only derived text — never a raw frame or second of audio**, binds it, and later
answers **anything** honestly: it states what it actually saw (cited) and **refuses or hedges** what it
didn't. The moat is honesty + binding, not OCR, not a chatbot.

## 1. THE PROTOTYPE = DONE-DEFINITION (the finish line; everything is measured against this)
Two deliverables, both required:
- **D1 — the 3-minute live demo:** point the phone at a real scene, walk away, then ask 5–8 questions and
  get correct **two-zone** answers (what I saw, cited | fenced world knowledge) AND at least one honest
  **refusal** of something not captured — running end-to-end on the device, zero raw media stored.
- **D2 — the honest number:** correct% and hallucination% (95% CI) on a frozen gold set of **REAL**
  captures, target ≥ ~60% correct / < ~10% hallucination.

If a piece of work doesn't move D1 or D2 closer, it is not prototype work.

## 2. THE CRITICAL PATH (ordered; the ONLY things that gate the prototype)
- **CP1 Rich on-device perception, no raw media** — the helper society (VLM macro + OCR + spatial/pose +
  temporal + audio + GPS), each per frame, frame discarded.
- **CP2 Persistent bound memory** — append-only event log + cross-frame binder (dedup by pose/time).
- **CP3 Honest two-zone answering** — object-grounded, world-EXPAND, refuse-the-unseen.
- **CP4 STAMPING glue** — pose/time/location/audio stamped onto every observation so CP2's binder works on
  REAL data, not just fixtures. (Without this the binder has nothing to dedup by, live.)
- **CP5 Validated live end-to-end run** — D1 actually performed once on the device with the event-log path.
- **CP6 The number on REAL captures** — D2 measured, not on fixtures.
- **CP7 Demo surface** — the 3-min flow + an honest glance cockpit that reflects reality.

## 3. HONEST STATUS NOW (no spin)
- CP1: **PARTIAL.** Qwen2-VL-2B macro + Apple OCR work on-device, accurate, moat intact (verified). Audio,
  pose-stamping, trigger-helpers NOT wired. Detector demoted (noisy).
- CP2: **DONE (brain), fixture-tested.** Event log persists; binder dedups by pose (count 2 not 8). Not yet
  exercised on a real live events.db.
- CP3: **NEARLY DONE.** Object-grounded refusal ✅; two-zone EXPAND in flight (task 04).
- CP4: **NOT DONE — the current critical gap.** The app does NOT yet stamp pose (PoseStamper exists but its
  attitude isn't written into observation `spatial_anchor`), so the binder cannot dedup live. Audio not stamped.
- CP5: **NOT DONE.** The new event-log path has NEVER been run end-to-end on a real device capture. This is
  the real gate and it is untested live.
- CP6: **NOT DONE.** Number exists only on fixtures (task 05). No real-capture number yet.
- CP7: **NOT DONE.** Cockpit is stale; 3-min flow not assembled.

## 4. ARE WE MOVING? — YES, but watch the pivot.
The single biggest UNKNOWN — "can a heavy VLM perceive on-device under the no-raw-media moat?" — is now
**RETIRED (yes)**. The brain (CP2/CP3) leapt this session. **But** the remaining gates (CP4 stamping, CP5
the live run, CP6 the real number) are app-side + integration, and I have been polishing the brain. The
risk now is **brain-polishing stall**: shipping a 7th brain improvement instead of closing the live loop.
NEXT MOVES MUST BE CP4 → CP5, not more brain features.

## 5. THE GUARDRAIL (run every cycle)
Before any task, answer in one line: **"Which CP does this advance, toward D1/D2?"**
- **TUNNEL** = optimizing one channel (OCR, captions) or re-deriving a solved thing. STOP.
- **STALL** = another brain/quality improvement when CP4/CP5 are still red. Pivot to the live loop.
- **REGRESS** = a change with no test / that breaks a green base / re-introduces raw-media retention. Revert.
Every status note carries a `LEASH:` line naming the CP and D-deliverable it served.

## 6. IMMEDIATE NEXT (the only sanctioned work until CP5 is green)
1. Finish queued brain tasks 04 (two-zone) + 05 (number-on-fixtures) — already in flight; then STOP adding brain tasks.
2. **CP4:** app writes PoseStamper attitude into each observation's spatial_anchor + commit GPS/time; (then) audio.
3. **CP5:** one validated live device run of D1 over the event-log path. THIS is the prototype gate.
4. **CP6:** freeze ~30 real-capture gold items, run the eval → the real number.
5. **CP7:** update the cockpit to mirror this oracle, every cycle.
