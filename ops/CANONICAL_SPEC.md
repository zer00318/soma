# TRACE — CANONICAL SPECIFICATION & EXECUTION LAW (v3)
**Status: ABSOLUTE. Supersedes v2 (2026-07-01, preserved in git history) and ALL other ops/*.md.**
**Authored 2026-07-03 from the founder co-creation session (interactive MCQ brainstorm).**
**That session constitutes the founder's explicit written approval that v2 §1 required.**

> Lineage: v1 was falsified within hours. v2 fixed that with the serial ledger M0→M8; its
> CODE side completed 2026-07-02 (store, sleep binder, ask brain, honesty gate, canonical
> battery — 241 tests; battery 96.7 / 100 / 0 confident-wrong / 100, held at fd82215).
> v3 does not discard that work: it promotes the survivors into the larger architecture the
> founder defined from first principles, and replaces v2's founder-session gate with a new
> done bar. v2's M-ledger is CLOSED; its unresolved device DoDs are absorbed into §4.

---

## 0. THE RULES THAT END THE TRAP
1. **FREEZE.** The architecture in §2 is fixed. We compound on it; we never re-derive it.
   Changing §2 requires the founder's explicit written approval.
2. **ONE METRIC.** Progress = movement on measured batteries on REAL capture (canonical
   battery + the Leash's per-domain coverage, §6). Unit tests gate merges; they are never
   progress. "N tests green" has been falsified as a progress signal three times.
3. **ONE OWNER PER QUESTION.** Every question type has exactly one answering subsystem.
   Duplicate mechanisms for the same question are P0 bugs.
4. **NEVER LEGISLATE AHEAD OF MEASUREMENT.** Packets are authored in full only for the
   active wave. Future waves stay stubs until the previous wave's numbers are in.

---

## 1. THE PRODUCT

TRACE is a memory prosthetic: **perfect memory, ask anything.** A worn device (phone as
stand-in; the real product is an ambient wearable — battery/thermal engineering on the
phone is explicitly OUT of scope) perceives your whole life, physical and digital. Raw
frames and audio die on the device; distilled observations survive forever on hardware
you own. While you sleep, the memory consolidates. You ask anything about your past in a
chat app and get an honest, evidence-backed, calibrated answer — the system would rather
say "I didn't capture that" than lie.

**Next iteration (room reserved, nothing built now):** the second brain that ACTS —
reminders ("you said you'd call Marcus Thursday"), warnings, briefings. No design below
may foreclose it; none of it ships now.

---

## 2. THE ARCHITECTURE (v3 — the founder's blueprint)

```
[PHONE — worn all day]                      [MAC]
  camera + mic (frames/audio NEVER leave)     screen daemon (your digital life)
        │                                          │
        ▼                                          │
  PLACE-ANCHOR HIERARCHY                           │
  everything pinned to a place, graded:            │
  semantic place → session pose (ARKit, only       │
  because it's free) → track anchor (always)       │
        │                                          │
        ▼                                          ▼
  STANDING CREW (always on): tracker · VLM · OCR · ASR · place ·
  motion/IMU · person+voice clustering · sound events · etc.
        │
        ▼
  ACTIVITY DISPATCHER ──▶ SPECIALIST PLUGINS (open registry, user-extendable:
  recognizes the context      code, receipts, documents, media, … etc. — NEVER a closed list)
        │
        ▼
  LIVE BINDER — instant fusion at the anchor: this text, on that object, there.
  Same-vs-new decided by coordinates × appearance fingerprint × time × attributes.
  Includes the LOOK-AGAIN loop: perception notices its own gaps and re-asks
  (zoom, crop, re-run a helper) automatically. A bit of brain lives live.
        │
        ▼
  ONE STORE — never deletes on its own; verbatim; local-only; provenance on every row.
        │
        ▼
  SLEEP BRAIN (nightly, unbounded): individuation & counting · IDENTITY RESOLUTION
  (Frank@WeChat = Yanjun Lai@WhatsApp; two sightings = one mug — auto-merge when sure,
  review-card when not; merges logged, reversible) · DIGEST PYRAMID (episode → day → week).
        │
        ▼
  ASK BRAIN (per question, tiered): compiled fast paths (counts, current-location)
  → pyramid routing (climb digests) → agentic drill-down into raw rows.
  Context stays small forever, regardless of months lived.
        │
        ▼
  CHAT APP ON PHONE: timeline of episodes (incl. honest gaps) · multi-turn chat ·
  live retrieval narration → calibrated badge → expandable receipts · review cards.
  (The GRAPH — memory as a walkable node-world, snap-edges as permissions — is the
   post-done-bar centerpiece: designed, not in the prototype.)
```

**Identity model (hybrid, fused):** places are coordinates (rooms become persistent maps);
things are appearance fingerprints (compact, on-device, non-reversible visual signatures)
with a location history through coordinate space. The live binder weighs both —
coordinates pin the world, fingerprints pin the things, and they check each other.

**Coordinates ruling (founder question, 2026-07-03): a signal, not the foundation.**
The product's questions want semantic places ("on the kitchen shelf"), and firm counts
were already achieved coordinate-free at room scale (v2's M2, live desk). Metric pose is
adopted ONLY because ARKit provides it for free alongside the camera frames — it
strengthens same-vs-new (a pan is not co-visibility) and look-again re-acquisition.
Provider = ARKit, sole camera owner (P00 measures; the apparatus already exists in-app as
the `spatialMode` toggle). Open-source SLAM on iOS is rejected on evidence: the best OSS
mapping app on iOS (RTAB-Map) itself uses ARKit as its odometry front-end; porting
ORB-SLAM3/OKVIS2-class stacks is months of work for worse IMU fusion. Proprietary VIO of
our own is years, absurd for a prototype. If P00 fails on-device, the fallback is the
coordinate-light place-graph (place recognition + fingerprints + tracks) — NOT OSS SLAM —
which loses nothing the done-bar battery measures.

**Phone's own screen:** a stated, honest hole in the prototype ("the wearable sees your
phone screen naturally; the phone stand-in can't film itself"). No build.

---

## 3. THE LAWS (invariants — every packet carries them; violating any = P0, revert on sight)

- **L1 PRIVACY.** Not one video frame, not one second of audio leaves the phone. Derived
  text observations and non-reversible numeric fingerprints/embeddings MAY cross to the
  owner's own Mac. Nothing, ever, to anyone else's hardware.
- **L2 HONESTY.** Confident-wrong = 0 is a hard merge gate. The grounding gate runs BEFORE
  every answering fastpath — no routing shortcut may bypass it (the unicorn breach was
  exactly this violation). Every answer carries a calibrated badge. Refusal is a feature.
- **L3 SOVEREIGNTY.** The system never deletes or decays content on its own (decay =
  retrieval cost only). The owner's delete: hidden immediately everywhere, true purge after
  a 30-day grace window. Snapping a graph edge cuts ACCESS, never data.
- **L4 ONE OWNER** per question type (count, where, who-said, when, what).
- **L5 NO CONTENT LEXICONS.** Relevance is structural; hardcoded word lists are forbidden.
- **L6 MEASURE FIRST.** No wave's packets are finalized before the prior wave's numbers.
- **L7 OPEN REGISTRY.** Helpers are plugins with one contract (§5). The list is never
  closed; users can add their own. "Etc." is load-bearing.

**People:** anonymous-until-named — voice/face clusters christened retroactively by context
("thanks, Marcus") or by the owner in chat. Others' speech: **verbatim, attributed** —
defensible because it never leaves the owner's hardware.

**Review loops (the user is a helper too):** the memory may ask the owner questions
(uncertain voice, possible merge, unreadable text) through all three channels — on
app-open (max 3 cards, always skippable), evening digest, and in-context during chat —
whenever genuinely uncertain. Answers land as first-class observations (helper `owner`).

---

## 4. THE DONE BAR (replaces v2's founder-session gate; absorbs its device DoDs)

**3 real days** of the founder's life captured (phone continuous + Mac daemon),
sleep-consolidated nightly, then a **founder-authored blind battery** (~30+ questions the
implementers never saw, spanning: recall, counts, where-is-it-now, people/who-said,
digital/screen, temporal/cross-day, absent/gaslight) asked in the phone chat app.

**Gate: ≥75% correct-on-present · CONFIDENT-WRONG = 0 · honest refusal on absent.**
Plus the Leash's per-domain coverage report showing no starved domain.

**The 90-second investor demo (all four beats, choreographed only after the bar is met):**
1. *Plant-and-recall, live* — capture runs during the meeting; a planted object/phrase
   recalled with receipts.
2. *The gaslight refusal* — "you saw a unicorn, right?" → calm refusal.
3. *Three days of real life* — the founder's actual past, queried on stage.
4. *The privacy reveal* — airplane mode mid-demo; everything still works.

---

## 5. THE HELPER CONTRACT (L7 made concrete)

A helper is ANY process that emits observations shaped as:
`{text, t_ms, anchor_id?, fingerprint?, confidence, helper_id, provenance}`
into the hub's ingest seam. Standing-crew helpers run always; dispatched specialists are
invoked by the activity dispatcher; the owner's review-card answers arrive as helper
`owner`. The registry is data, not code — adding a helper must not touch the spine.

---

## 6. THE LEASH (the objective evaluator — anti-tunnel machinery)

A fixed per-domain battery scored against every captured real day: recall %, refusal
honesty, and **coverage per life domain** (physical objects · text-in-world · speech/people ·
digital/screen · motion/place · sound events · temporal). Numbers append to
`evaluation/leash_history.jsonl` on every run — trend is visible, not vibes.

**The mechanical rule: if 5 packets merge and no domain number moves, ALL work stops and
the plan is reassessed with the founder.** The leash yanks regardless of how busy we felt.
It exists because we once spent weeks inside one channel (OCR/VLM/coordinates) while the
others starved.

---

## 7. PACKET PROTOCOL (how all work is dispatched — mixed fleet)

Work lives in `ops/packets/` — one self-contained .md per packet + `INDEX.md` ledger.
Every packet header: `wave · tag · executor · effort · status · depends`.

| tag | executor | Opus effort | reviewer |
|---|---|---|---|
| mechanical | local LLM or Sonnet | low (if Opus used) | any higher tier |
| guided | Sonnet, or Opus | medium | judgment tier |
| judgment | Opus (agent teams allowed) or Fable | high | Fable / founder-visible |

**Merge gate for every packet:** committed `pytest -q` green AND canonical battery
(`.venv/bin/python evaluation/run_canonical_battery.py`) holds CONFIDENT-WRONG = 0 AND
(for perception/brain packets) a spot check on the real store. Battery moved or held in
the intended dimension, else revert the same day. No "keep it, we'll fix forward."
Close-out = flip the packet's status line in INDEX.md. No other doc is written.

**Executors are told:** the packet file is your ENTIRE context. If you need information
not in the packet, STOP and report — do not guess. Update no docs except your INDEX line.

---

## 8. WHAT SURVIVES / WHAT'S NEW

| Survives (battle-tested, evolve in place) | New builds (v3) |
|---|---|
| Store + ingest seam (`src/trace_memory/store/`) | Coordinate substrate (ARKit-as-owner) |
| Sleep binder (individuate/author/permanence/sleep) | Appearance fingerprints |
| Ask brain + honesty gate (`src/trace_memory/brain/agent.py`) | Live binder + look-again loop |
| Canonical battery instrument | Activity dispatcher + helper registry |
| Hub (`scripts/trace_hub.py`) | Mac screen daemon |
| On-device crew (detector/tracker, FastVLM, OCR, ASR) | Voice-identity, motion, sound-event channels |
| iOS app shell (`trace-native-fastvlm/`) | Digest pyramid + pyramid router |
| | Identity-resolution brain + review cards |
| | Chat app UI (narrate → badge → receipts) + timeline |
| | Hide-then-purge delete · The Leash |

The capture pipeline's camera ownership (AVCaptureSession) is REPLACED by ARKit-as-owner
(P00 spike validates; `TraceARKitEngine.swift` from the reverted experiment is the head start).

---

## 9. WAVES (live ledger: ops/packets/INDEX.md)

- **W0 — Foundations & spikes:** ARKit-owner spike · helper contract · Leash v1 ·
  ask-brain over-refusal fixes · repo hygiene.
- **W1 — Substrate & live binder:** anchors · fingerprints · live binder · look-again.
- **W2 — Coverage wave one:** Mac daemon · voice-identity · motion · sound events · dispatcher.
- **W3 — Memory organs (stubs until W2 numbers):** episode segmentation · digest pyramid +
  router · identity-resolution brain · multi-turn + narration events.
- **W4 — The app (stubs):** chat UI · timeline · review cards · hide-then-purge delete.
- **W5 — Finish line (stubs):** 3-day capture ops · blind battery protocol · demo choreography.

---

## 10. DECISIONS REGISTER (founder session, 2026-07-03)

core promise = perfect memory, ask anything (acting brain later, room reserved) · all-day
capture, phone stand-in, battery/thermal out of scope · perceive everything, both pillars ·
chat app surface · memory@scale = layered (compiled → pyramid → drill-down), pyramid-first ·
people anonymous-until-named · others' speech verbatim + attributed · Mac daemon → same
store · wave one = digital + WHO + motion + sound (coverage math, not demos — chess cut) ·
phone-screen hole stated honestly · hybrid identity (coords + fingerprints, fused) ·
ARKit-owner spike first (iPhone 17 base, no LiDAR) · privacy line = text + fingerprints may
cross, pixels/audio never · evolve the survivors, rebuild capture ownership · delete =
hide-then-purge (30-day grace) · graph after the done bar (chat + timeline first) · merge
auto-when-sure / ask-when-not (logged, reversible) · review cards via all three channels ·
demo = all four beats · executor fleet = mixed, packet-tagged (mechanical/guided/judgment).
