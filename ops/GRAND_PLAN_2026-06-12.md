# GRAND PLAN — June 12 → June 22 (architect: Fable 5, final session series)

This is the contract for the last 10 days of Fable 5 availability. One goal:
the prototype a stranger can feel in 10 minutes. Everything that does not
move that demo is cut or delegated.

## Prototype definition (locked)

1. Wear the chest-mounted iPhone, walk a room/building once.
2. Objects appear as permanent WORDS with positions (and sizes) in a
   navigable world view at http://localhost:8777/world — still there
   tomorrow, after app kill, after reboot; "X is missing/moved" events on
   re-entry.
3. Afterward, a blind founder battery (RAS) answers diverse questions with
   citations. Prototype gate: RAS ≥ 60, hallucination < 5%.
4. The all-day budget story holds: measured battery %/hr, thermal, and
   enrichments/hr numbers in the demo script.

## Independent audit verdicts (2026-06-12, evidence in HANDOVER)

- **MobileCLIP zero-shot naming: KEEP.** Founder rejected YOLO (closed
  classes) and FastVLM (slow/rambly) for cause. MobileCLIP-S0 is ANE-fast,
  words-not-prose, vocab grows without retraining. The weak link is NOT the
  namer — it is REGION PROPOSALS (objectness saliency caps at ~3 coarse
  regions/frame). Fix proposals (grid fallback), don't swap the namer.
  Alternatives weighed: OWLv2 (too heavy for ANE), YOLO-World (days of
  CoreML port risk, uncertain gain). Re-evaluate ONLY if desk-test diag
  shows naming (not proposals) is the bottleneck.
- **ARKit genesis frame + ARWorldMap: KEEP.** Only free 6DOF + reloc on
  this hardware. Reloc-gate + timeout already in code. Cross-day reloc is
  the open risk; measured at G1/G2, not assumed.
- **Graph schema: KEEP**, complete brief-2's `spatial_pose` upsert. The #1
  permanence gap is that /world renders only the LATEST snapshot (verified
  in trace_demo_dashboard.py) — the durable world must come from the DB.
- **App rewrite: REJECTED until after June 22.** The build+install loop
  works (verified tonight); a rewrite burns the only device-test loop.
- **RAS ≥ 60 bar: KEEP** as prototype gate; cut-line below defines what
  ships if it slips. Walk-1's −8.0 was dominated by capture-side misses
  (21/25) — the v2 armed build + MobileCLIP words + OCR stills + spatial
  answers attack exactly that class.
- **Prototype definition itself: KEEP** (founder's own spec). The only
  addition: the demo must run from a written script with zero architect
  intervention (G4).

### Process failures found (and fixes)

1. **Founder desk-tested a STALE build.** The 23:12 posts carry
   `word_source: native_vision_classifier` — a string that exists NOWHERE
   in current code. Brief-1 "acceptance failure" partly tested old code.
   FIX: build stamp — git SHA in the app status line + every posted
   packet's metadata (Codex brief 4, P0). Lead verifies device artifacts,
   never trusts "installed".
2. **"Device build blocked" was false.** The documented recipe
   (`-sdk iphoneos26.5` + `ASSETCATALOG_EXEC=/tmp/actool_wrapper/actool`)
   built clean tonight; destination-based builds are the thing that fails.
   The recipe in HANDOVER is law; follow it exactly before declaring
   blockage.
3. **Night shift died silently** on T1 and nobody noticed for hours.
   FIX: night-shift queue restarted with bounded tasks; lead checks
   state file at every session start.

## Schedule (owners: FOUNDER / CODEX / QWEN / GEMMA / LEAD=Fable 5)

Gates are hard: a phase does not start until the previous gate passes,
verified by LEAD on device artifacts or green suites.

- **Jun 12 (Thu)** — LEAD tonight: fresh build installed on iPhone
  (DONE 01:28), briefs + queue written (DONE). FOUNDER morning: desk test
  per ops/FOUNDER_DESK_TEST_2.md. QWEN overnight: diag analyzer script.
  CODEX: brief 4 P0–P1 (build stamp, durable world in graph).
  LEAD evening: analyze spatial_diag.ndjson, tune score floor / merge
  radius / promote distance from DATA. **G1 = desk acceptance: ≥4 desk
  objects named+pinned, no duplicates on re-show, survive swipe-kill,
  visible on /world.**
- **Jun 13 (Fri)** — G1 must pass (else LEAD root-causes from diag, fixes,
  reinstalls, founder re-tests same day). CODEX: brief 4 P2–P3 (extent,
  proposal fallback, vocab_misses). FOUNDER: walk 2 — GT video ON, then
  ~25 blind questions (walk2.txt). LEAD: replay spool, run RAS battery #2,
  score with founder verdicts.
- **Jun 14 (Sat)** — LEAD: walk-2 postmortem with GT video review
  (scripts/review_ground_truth.py + gemma vision) → capture-precision
  report; vocab grown from vocab_misses (rebuild embeddings, reinstall).
  CODEX: brief 4 P4 (re-entry events).
- **Jun 15 (Sun)** — **G2 = permanence payoff demo on device: hide an
  object, reopen app, "X is missing" event reaches hub and shows on
  dashboard.** LEAD verifies on device. LEAD + QWEN: episode layer
  (same-day separation) wired into recall time-scoping (cross-module =
  LEAD work, bounded pieces to QWEN).
- **Jun 16 (Mon)** — FOUNDER: walk 3 = full-building walk + blind battery
  → RAS #3. Battery/thermal measured over ≥2h continuous (target: report
  real %/hr + enrichments/hr; 8%/hr walk-1 baseline).
- **Jun 17 (Tue)** — LEAD: fix round from walk-3 taxonomy. Spatial recall
  intents ("where is X", "what is on the desk") answer from spatial_pose
  rows with citations. Suite + north-star stay green (project law).
- **Jun 18 (Wed)** — **G3 = dry-run the 10-minute stranger demo** —
  founder executes ops/DEMO_SCRIPT.md cold, LEAD watches logs only.
  Failures become Jun 19 fixes.
- **Jun 19 (Thu)** — FOUNDER: walk 4 blind battery → RAS #4 (target ≥60).
  Buffer day for unknowns.
- **Jun 20 (Fri)** — CODEX: /world polish (navigable 3D — orbit/walk view
  over DB objects; nice-to-have, cut first). LEAD: RAS curve chart +
  demo script final.
- **Jun 21 (Sat)** — LEAD: full HANDOVER.md rewrite for successor model
  (respawn protocol, verified state, RAS curve, open briefs, build
  recipe, founder protocols). Freeze non-essential change.
- **Jun 22 (Sun)** — **G4 = founder runs the complete demo solo from the
  script.** Whatever G4 shows is the truth we ship.

## LEAD turn budget (Fable 5, ~12 interventions — spend like a dying king)

1. Tonight: audit + build/install + briefs (this session).
2. Jun 12 eve: diag analysis + threshold tuning + G1 verdict.
3. Jun 13: walk-2 ingest + RAS #2 scoring.
4. Jun 14: GT-video postmortem + vocab rebuild + reinstall.
5. Jun 15: G2 device verification.
6. Jun 15: episode layer integration (the one cross-module coding turn).
7. Jun 16: walk-3 ingest + RAS #3 + battery/thermal readout.
8. Jun 17: spatial recall intents + suite/north-star gate.
9. Jun 18: G3 dry-run triage.
10. Jun 19: walk-4 RAS #4 + cut-line decision.
11. Jun 20: demo package review.
12. Jun 21–22: handover rewrite + G4 standby.
Everything else is Codex/qwen/gemma/founder. If a turn isn't on this list,
it must unblock a gate or it doesn't happen.

## Cut-line (what ships if everything slips)

Non-negotiable core: desk-scale spatial permanence (named+pinned words,
no dupes, survive kill+restart, missing-object event) + /world durable
from DB + RAS ≥ 30 with < 5% hallucination + an honest demo script that
shows real numbers including the misses.
First cuts, in order: 3D navigable renderer (top-down map is fine) →
episode layer (date-scoped retrieval hack instead) → battery OPTIMIZATION
(measure and report, don't fix) → extent/word-size rendering.

## After June 22 (succession)

- ops/HANDOVER.md is the respawn contract; the successor model reads it +
  auto-memory and continues. It must contain: verified state with dates,
  the RAS curve, every open brief, the build recipe, founder test
  protocols, and the standing laws (X-SOMA-Token, soma_hub.sqlite3,
  self._connect(), no Flask, suite+north-star green after soma_hub
  changes, never Apple ID/password).
- Open development continues via the same delegation law: briefs to Codex,
  bounded specs to qwen, gates to gemma, physical tests to founder.
- The RAS battery cadence (walk → blind questions → verdicts → taxonomy →
  fix) is the engine that survives any particular model.
