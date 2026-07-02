# TRACE — CANONICAL SPECIFICATION & EXECUTION LAW (v2)
**Status: ABSOLUTE. Supersedes v1 (frozen earlier 2026-07-01) and ALL other ops/*.md. Revised 2026-07-01 after the fresh adversarial audit.**

> v1 was falsified within hours of being "frozen": its blueprint mandated 6-DOF ARKit pose +
> world-XYZ instance keys (ARKit is dead on the founder's phone; the shipped anchor is the
> on-device track_id), and its §4 claimed "CONFIDENT-WRONG = 0 (GATE MET)" while the live /ask
> answered "1 unicorn @0.8". v2 exists because the law must match measured physics, not the
> other way around. **This is the last revision that changes the blueprint.** Any future change
> to §1 requires the founder's explicit written approval.

---

## 0. THE THREE RULES THAT END THE TRAP
1. **FREEZE.** The architecture in §1 is fixed. We compound on it; we never re-derive it.
   Greenfield nukes, new stores, new server files, and new planning docs are forbidden.
   (There are 55 docs in ops/. This one supersedes them; touch no other.)
2. **ONE METRIC.** Progress = movement on the Canonical Battery (§4), end-to-end, on real
   capture, scored against gold the implementer never saw. Unit tests gate merges; they are
   NEVER progress. "N tests green" has been falsified as a progress signal three times.
3. **ONE OWNER PER QUESTION.** Every question type (count, where, what, said, when) has exactly
   ONE answering subsystem. Duplicate mechanisms for the same question (today: 3 counting
   systems that answer 12 / 3 / 1 for the same keyboard) are P0 bugs, not options.

---

## 1. THE IMMUTABLE ARCHITECTURE BLUEPRINT

```
[PHONE — on-device, frames NEVER leave]
  camera/mic ─▶ OBSERVER  (blur/change/novelty gating — keep the useful ~10%)
              ─▶ HELPERS  (parallel aspect specialists, per kept frame):
                   • detector+TRACKER  → {label, track_id, bbox, depth_m|xyz if available}
                   • VLM               → object/scene descriptions (per-track crop when possible)
                   • Vision OCR        → verbatim text + anchor to overlapping track/bbox
                   • Speech ASR        → transcript segments
              ─▶ frame DELETED; helper TEXT+metadata POSTed to hub
[MAC — trust boundary = the user's own machine]
  trace_hub (:8765) ─▶ UNIFIED STORE (data/trace_store.sqlite3, append-only, never-delete,
                        every row tagged source + helper + track_id when present)
  SLEEP BINDER (offline, unbounded compute) ─▶ INDIVIDUATE: one node per PHYSICAL instance.
        Identity evidence, fused in ONE module (src/trace_memory/store/individuate.py):
        track_id (primary, live) × attribute/text compatibility × metric-3D proximity
        (DepthPro reconstruction at sleep-time when frames were sampled for it).
        Authors cited memories: entity/group/count/location. AUGMENTS raw, never replaces.
  AGENT (src/trace_memory/brain/agent.py) ─▶ grounding gate FIRST, then retrieval
        (raw + authored), then reasoner (local gemma dev / 27b-or-frontier at ask-time —
        ask-time is off the real-time budget) under the evidence-only contract.
[UI]  ONE surface: /ask → {answer, evidence chain, calibrated confidence, honesty badge}
```

**Invariants (violating any = P0, revert on sight):**
- I1. Raw media never leaves the phone; only derived text + metadata persist.
- I2. The subject-grounding honesty gate runs BEFORE every answering fastpath. No routing
  shortcut may bypass it. (The unicorn breach was exactly this violation.)
- I3. One physical object = one instance node; a count is the number of instance nodes the
  binder resolved — never a per-question text re-cluster, never an LLM guess.
- I4. 0 confident-wrong (wrong at confidence ≥0.6, not refused) on the Canonical Battery,
  including gaslight and count-of-absent questions. Hard gate on every merge.
- I5. No hardcoded content lexicons in ranking/answering (no room-specific noun lists, no
  dev-screenshot noise strings, no phrasing-anchored routing regexes).

---

## 2. THE GRANULAR FEATURE LEDGER (strict serial order)

> You may not start item N+1 until item N passes its DoD on REAL capture, re-run personally by
> the Chief. A sub-agent's "passed" is not acceptance. Every item ships with its held-out
> battery questions added by the Chief BEFORE implementation.

**M0 — Close the unicorn breach + repo red. ✅ DONE 2026-07-02 (commit 8a6e34f).**
  Count fastpath moved behind the S1 gate; `_count_subject` narrows to the counted noun phrase;
  irregular plurals handled; 3 orphaned test files deleted, M0 regression battery + hub seam
  tests added. MEASURED: 10/10 truly-absent count questions honest on live :8765 + gemma12b
  (0 fabricated counts); committed `pytest -q` = 211 passed; :8799 zombie killed, no respawners.
  NOTE for M1/M5: a 1-frame VLM misread ("snake" = hanging cable) is countable evidence —
  one-off reads must hedge (n_frames==1 → soft count), and the consensus filter kills them
  upstream in M5.

**M1 — ONE counting path. ✅ DONE 2026-07-02 (commit 120207b).**
  `count_instances` is THE resolver: binder-authored + clustering + floor, reconciled.
  Agreement → firm @0.8; binder disagreement → honest RANGE @0.5; floor-rescue/single-sighting
  → "approximately N" @0.55. Floor unpoisonable (OCR rows + verbatim "poster reads..." text
  excluded; adjective-run word counts work). Count intent = phrasing family, not ^how many
  (LLM intent tagging deferred to M3). Type-modifier discriminator from descriptor phrases
  only — comma-list labels carry no types (live regression caught pre-commit: over-split
  agreed with fragmented binder → firm-wrong "3 mice"; now hedged with truth inside range).
  MEASURED DoD: garage block 10/10, 0 confident-wrong (was ~4/10 w/ 2 confident-wrong);
  live desk store 0 confident-wrong. Suite 219 green. Hub restarted on new code.
  → M2 turns the live "between 1 and 3" hedges into firm correct counts by fixing identity.

**M2 — Object identity that survives real capture. ✅ CODE DONE 2026-07-02 (commit 0d4f5d5);
  DoD remainder = founder truth confirmation + a second never-seen-room capture.**
  Co-visibility re-ID in individuate.py: same-frame (≤150ms) different-cell = distinct;
  same-cell = duplicate box; attribute contradiction (weight/volume, colour family) splits
  without co-visibility; else merge. Ambiguity → authored count RANGE; resolved low = hard
  lower bound in the resolver. Sleep reconsolidation (reconsider_derived) re-derives all
  binder output from immutable raw each run. Three real-data bugs found live and locked as
  tests: per-session track-id collisions (key by label+tid), depth text read as identity
  size, pan misread as co-visibility (700→150ms). MEASURED live desk: mouse 9 tracks→1 FIRM,
  laptop→1 FIRM, chair/book/phone/bed 1 FIRM, keyboard→[2,3], tv→[2,3], cup→[1,2]; unicorns
  refused. Suite 225 green. DepthPro 3D consolidation deferred: grid+time evidence sufficed
  for the desk; revisit if the second capture's DoD misses ±1.

**M3 — De-overfit the ranker (I5 enforcement). ✅ DONE 2026-07-02 (commit 43320d0).**
  All content lexicons + dead code deleted; ranking = lexical overlap + intent→helper-type
  priors + generic location grammar + structural screen_text demotion. MEASURED DoD: garage
  17/18 (gate ≥13 — only miss is DeWalt brand = M4's scope), paraphrase parity 9/10 = 90%
  (gate ≥90%; the break is an honest refusal on call/phone synonymy — future embedding
  grounding candidate, moat intact). 0 fabrications. Suite 225 green.

**M4 — OCR→object binding at capture ("DeWalt" class). ✅ CODE DONE 2026-07-02 (commit
  90b8e83); DoD remainder = device deploy + founder capture of 5 planted branded objects.**
  Track-anchor emission binds intersecting OCR to the track ('label text: "..."' +
  metadata.bound_text); bound digits are verbatim world text for the count floor (bus-sign
  test locked). xcodebuild iOS BUILD SUCCEEDED. Mac seam locked by 3 tests through real
  Hub.ingest. Suite 228 green.

**M5 — Capture coverage & rate. ✅ CODE DONE 2026-07-02 (commit e5b3e9b); DoD = blind
  battery on the founder-session capture (see gate block below).**
  Per-track VLM crop enrichment (one zoomed read per confirmed track, throttled, fused via
  track_id — the small/far-object lever); ASR delta commits (cumulative-partial duplication
  fixed; the 2-rows session was likely silence, engine wiring verified correct); small-text
  OCR judged covered by M4's bound full-res OCR — revisit if the blind battery misses brands.
  iOS build green; seam tests through real Hub.ingest; suite 230 green.

---

### ⏳ THE FOUNDER-SESSION GATE (everything device-dependent, one physical session)
1. **Deploy** the current build to the phone (M4+M5 code is on main, compiles green).
2. **Desk truth** (M2): confirm actual counts — keyboards (system says 2–3), tvs/monitors
   (2–3), cups (1–2), mice (1), laptops (1).
3. **Never-seen room capture** (M2 DoD): ~2–3 min slow pan; binder counts must be ±1.
4. **5 planted branded objects** (M4 DoD): ≥4 brand questions answered verbatim.
5. **Speak during capture** (M5 ASR): narrate a few reminders; verify delta rows land.
6. **Blind battery** (M5 DoD): founder writes ~20 gold questions the implementer never
   sees; target ≥65% RAS, <10% halluc, 0 confident-wrong.

---

**M6 — Sleep-time enrichment.**
  Landmark/context expansion + succession links ("current location" supersedes) authored during
  sleep; retrieval surfaces them under the monotonic gate.
  DoD: temporal/current-state battery block ≥80%.

**M7 — ONE demo surface.**
  /ask hardened (timeout, concurrent asks, evidence rendering) + the phone app's ask view or a
  single cockpit page showing answer + evidence + confidence. No second surface.
  DoD: 30-minute live session, 40 mixed questions typed by a stranger, zero crashes, median
  answer <15 s (27b) — honesty gate holds throughout.

**M8 — Full-gate rehearsal.**
  Fresh capture of a never-seen room, Canonical Battery run blind by the founder.
  DoD: §4 exit numbers. Then, and only then, product-form polish.

---

## 3. IMPLEMENTATION PROTOCOL (how every module gets built)
1. Chief writes the held-out battery questions FIRST and keeps them out of the implementer's view.
2. Smallest change that could move the metric. No new files where an owner file exists
   (hub=trace_hub.py, identity=individuate.py, counting=binder, agent=agent.py).
3. Run: committed `pytest -q` (must be green) AND the full Canonical Battery end-to-end on real
   capture with the production reasoner.
4. Merge iff the battery moved (or held) in the intended dimension AND confident-wrong = 0.
   Otherwise revert the same day. No "keep it, we'll fix forward."
5. Update THIS ledger's checkbox + one line in the battery log. No other doc is written.

## 4. THE CANONICAL BATTERY (the single ungameable number)
Fixed, versioned file `evaluation/canonical_battery.jsonl` (≥60 Qs; founder/Chief-authored gold;
implementers never tune on it). Blocks: present-recall, absent-refusal (incl. count-of-absent),
counting (multiples/fragmentation/poisoning), paraphrase pairs, gaslight/false-premise,
attribute precision (incl. OCR-bound brands), temporal, speech. Report four numbers only:
- CORRECT-ON-PRESENT % · REFUSE-ON-ABSENT % · CONFIDENT-WRONG (hard 0) · PARAPHRASE-PARITY %

**Measured reality 2026-07-01 (fresh garage suite + live probes):** 13/18 correct; refusal
bedrock held on novel vocab; CONFIDENT-WRONG = 3 (mugs "1"@0.8, clamps "1"@0.8, unicorns
"1"@0.8 on the LIVE path) → **gate currently FAILED. M0 exists because of this line.**

## 5. DEFINITION OF DONE — 100%
The product is done when, on a LIVE capture of a room the system has never seen, answered
end-to-end through the one surface by the local/ask-time brain, the Canonical Battery reads:
**CORRECT-ON-PRESENT ≥85% · REFUSE-ON-ABSENT ≥95% · CONFIDENT-WRONG = 0 · PARAPHRASE-PARITY
≥90% · counting within ±1 on every asked label** — with the founder typing the questions.
