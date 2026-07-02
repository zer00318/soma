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

**M0 — Close the unicorn breach + repo red. (≤1 day)**
  Move `_permanence_count` behind the S1 grounding gate; count subject must match the counted
  label itself (irregular plurals handled); delete/fix the 3 orphaned test files so committed
  pytest is green; kill the :8799 zombie process and its launcher.
  DoD: count-of-absent battery (unicorns/flamingos/dogs ×10 phrasings) → 100% refuse; committed
  `pytest -q` green; only :8765 serves.

**M1 — ONE counting path.**
  The agent's count answer = binder-authored instance count (I3). `permanence.py` text-clustering
  demoted to a binder-internal signal; `explicit_count_floor` may only FLAG a discrepancy
  (hedge), never override upward from unanchored OCR digits (kills the "5 buses from a poster"
  class). Delete the COUNT_RE routing anchor: count intent detected robustly (embedding or LLM
  intent tag), not `^how many`.
  DoD: garage-suite counting block (identical multiples, split-attributes, fragmentation,
  number-poisoning, phrasing variants) ≥8/10 with 0 confident-wrong.

**M2 — Object identity that survives real capture (THE hard problem, no substitutions).**
  Fix track fragmentation at the binder: cross-track re-ID merge using appearance embedding +
  temporal overlap logic + DepthPro sleep-time 3D consolidation. Target on the LIVE desk store:
  keyboard 12→1, tv 12→≤2, mouse 9→1, cup 8→2 (verify truth with founder).
  DoD: on TWO real captures (desk + one never-seen room), binder instance counts within ±1 of
  founder-verified truth for every COCO-class label with ≥3 observations.

**M3 — De-overfit the ranker (I5 enforcement).**
  Delete SCREEN_REPORT_NOISE, LOCATION_ANCHORS, drink-cue lexicon, dead code (_first_colour,
  EXISTS_RE/ATTRIBUTE_RE, _heuristic_answer stub). Replace with: subject-token anchoring +
  embedding similarity + helper-type priors (helper priors are structural, not content).
  DoD: paraphrase battery ≥90% parity; garage suite (novel vocab) does not regress below 13/18.

**M4 — OCR→object binding at capture ("DeWalt" class).**
  OCR hits bind to the overlapping track/crop on-device (bbox intersection), so brand/label text
  attaches to the object instance, not to a floating text row.
  DoD: 5 planted branded objects in a real capture → ≥4 brand questions answered verbatim.

**M5 — Capture coverage & rate.**
  Per-track crops feed the VLM (small/far objects), crop-zoom OCR specialist wired live
  (1.48× real-time measured — it fits), ASR channel verified continuously (store has 2 asr rows
  from a full session — that is a wiring bug until proven otherwise).
  DoD: day-in-life-style blind battery on a NEW founder capture ≥65% RAS, <10% halluc.

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
