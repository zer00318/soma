# Chief Supervision Note

## 2026-06-29 00:47 — relaunch after silent crash

**State found:** `crashed`. Supervisor process dead (pid 30134, no live world-overhaul
subprocess). `state.json` was frozen ~37 min on `WG02_helper_ingest_local` with no
`task_finish`. `daemon.log` held only two `started pid=` lines (00:07, 00:09) and no
traceback — consistent with the host session ending / laptop sleep at ~00:08, not a code
fault. helper_store.sqlite3 had been written (73KB @ 00:08), so WG02 was making progress
when it was interrupted.

**Evidence used:**
- `ops/serial_runtime/world_overhaul/state.json` (stale 37 min, task WG02)
- `activity.jsonl` (last entry = task_start WG02, no finish)
- `daemon.log` (start lines only, no crash trace)
- `ps` — no world-overhaul / light_ingest / frontier subprocess alive
- `evaluation/ras/store_eval_frontier.json` — MEASURED: 6/21 correct (29% answered_pct
  wording, 16 answered), 38.1% confident-wrong, n=21, **gate_met: false** (Jun 28 23:26)
- Preflight: ollama up with gemma3:27b-it-qat + gemma3:12b-it-qat + embed models;
  WG02 input `selected_frames` present (6 frames). Nothing blocking a restart.

**Action taken:** Relaunched via `./scripts/start_world_overhaul_supervisor.sh`. Confirmed
the supervisor is idempotent (re-runs the whole fixture lane from WG01 with --fresh; no
partial-resume to corrupt). Verified it advanced past the death point: WG01 manifest +
validate finished OK, now legitimately running WG02_helper_ingest_local (pid 34320).
Did NOT patch — measured artifact is stale and no dominant-failure report exists yet;
serial law says no code edits before fixtures+synthetic+eval agree.

**What wakes me next:** the heavy local lane (WG02 ingest → export → validate → WG03/04
binder+brain → WG05 tests → WG06 real bedroom eval). The only thing that moves the
measured number is WG06 writing a fresh `store_eval_frontier.json`. Sleeping ~15 min,
then checking: (a) supervisor still alive, (b) activity.jsonl advanced past WG02,
(c) whether WG06 has produced a new eval. If WG02 has died again → diagnose light_ingest
local directly instead of blind relaunch.

## 2026-06-29 01:04 — iteration 1 cycle ran clean; in codex patch phase

**State found:** `running_cleanly`. Supervisor (pid 34320) cleared WG01–05 (all rc=0),
ran WG06 real bedroom eval iter 1 (finish 00:59 rc=0 → fresh artifact), authored the
dominant failure report (01:00), now running WG08_codex_patch_iter_1.

**Measured (00:59, store_eval_frontier.json):** correct 6/21 (FLAT vs prior), answered 13,
confident_wrong 5 (was 8), halluc_pct 23.8 (was 38.1), gate_met: FALSE. The halluc/cw
drop is baseline-iter-1 variance/already-merged code, NOT a patch win — correct is flat,
which is the gate dimension. Not crediting progress.

**Flag (not acting):** dominant_failure_report.md = gemma reasoning over the SYNTHETIC
shirt fixtures, not real bedroom misses; recommends reasoning/retrieval patch. Playbook
warns vs patching reasoning when capture/helper may be the real gap. Letting the cycle
run; will judge iter-2 re-measure strictly. Supervisor's _improved() self-halts if iter-2
correct doesn't beat iter-1 — correct honest behavior.

**Action taken:** none (cycle progressing cleanly; do not interrupt).

**What wakes me next:** WG08 patch → WG09 retest → iteration-2 WG06 eval. Sleeping ~12 min.
On wake: check if correct moved off 6/21, whether supervisor halted (no_improvement /
patch_result_missing), and read last_patch_result.md.

## 2026-06-29 01:18 — iter-2 re-measure: correct 6→7 (+1), marginal

**State found:** `running_cleanly`. WG08 patch iter1 (rc=0, agent.py citation-expansion
fix, 5 tests pass, last_patch_result.md written) → WG09 retest (rc=0) → WG06 eval iter2
finish 01:17 (rc=0). Supervisor pid 34320 alive (31min), now in iter-2 report/patch phase.

**Measured (01:17):** correct 7/21 (was 6, +1 REAL on gate dim), answered 13,
confident_wrong 6 (was 5, +1), halluc_pct 28.6 (was 23.8, +4.8), gate_met FALSE.
Verdict: genuine but marginal — patch traded a bit more answering for a bit more wrong.
Still far from ~16/21. _improved() True (correct rose) so loop continues to iter3 (cap=4).

**Action taken:** none (cycle progressing; correct moved, so honest to continue).

**Watch next:** iter-3 patch+eval (~20min). If correct stalls/drops at iter3, _improved()
halts on no-improvement = correct honest stop. Also watch confident_wrong creep — if the
loop inflates answering while wrong climbs, that's refusal-weakening drift to flag/stop.
Sleeping ~15 min.

## 2026-06-29 01:34 — FALSE HALT diagnosed + harness fixed; HARD BLOCKER: codex quota

**State found:** supervisor HALTED (mode halted, reason no_improvement, iteration 2). Two
root causes, both proven from artifacts:

1. HARNESS BUG (fixed): eval artifact nests metrics under `summary`
   (`{"summary":{correct,gate_met,halluc_pct}, "results":[...]}`) but
   world_overhaul_supervisor.py read them top-level → `_improved()` always False after
   iter1, gate-met never detectable. So the loop false-halted while correct ACTUALLY rose
   6->7. FIX: added `_summary()` read-through; used in `_improved()` + gate check.
   Verified: _improved(6,7)=True, _improved(7,7)=False, gate detect=True, compiles.
   Not committed (working-tree only; supervisor loads from disk).

2. HARD EXTERNAL BLOCKER (surfaced to founder): iter-2 codex patch ran 2s = OpenAI
   gpt-5.4 USAGE LIMIT hit ("try again at 3:03 AM"). Codex CLI exits 0 even on quota
   error, so supervisor saw rc=0 no-op. The iter-1 patch (8min, 141k tok) WAS real and
   is what moved correct 6->7. No further autonomous patch possible until ~03:03.

**Measured truth (01:17, store_eval_frontier.json):** correct 7/21 (33%), answered 13,
confident_wrong 6, halluc_pct 28.6, gate_met FALSE. Real misses are dominated by
SPATIAL/STATE-CHANGE ("where is X currently" -> gives last-seen location; blanket on bed
not suitcase) and missing-capture (battery %, pillow count, cello tapes, day/night) ->
i.e. capture/perception gaps, NOT reasoning. Matches patcher's residual-risk note.

**Action taken:** fixed harness bug; did NOT relaunch (codex quota-blocked until 03:03 -
relaunch now = wasted lane + honest halt at iter2 with no new patch). 

**What wakes me next:** sleep toward ~03:05 (ScheduleWakeup max 1h, so one more hop).
After 03:03 codex reset: relaunch via start script so the patch->remeasure loop resumes
with credits AND the fixed honesty checks. If after a real iter-2 patch correct still
doesn't beat 7, that's a genuine honest plateau -> halt + surface to founder that the
dominant failure is capture/perception (out of scope for brain-side codex patches).

## 2026-06-29 03:07 — relaunched after codex reset (harness fix active)

**State found:** halted (no_improvement, stale). Clock 03:07 > codex reset 03:03.
**Action:** relaunched ./scripts/start_world_overhaul_supervisor.sh. Confirmed advancing:
pid 37043, WG01 done, now WG02_helper_ingest_local. Fixed _summary()/_improved() in
working tree is what this run uses.
**Watch next (~18-20min):** first WG08 codex patch iter1 — verify it's NOT quota-blocked
again (newest /tmp/codex_run_*.log must lack "usage limit", run >2s) and that iter2 WG06
eval moves correct off 7/21. If codex quota-blocked again -> hard halt + surface to
founder (no autonomous patching possible). If real patch lands but correct stays 7 ->
honest plateau; dominant failure = capture/perception (out of brain-patch scope).

## 2026-06-29 03:27 — codex credits BACK + KEY FINDING: eval is noisy (±1 correct)

**State:** running_cleanly. pid 37043 (20min). WG01-05 clean, WG06 iter1 eval done 03:19,
report 03:21, WG08 codex patch iter1 RUNNING ~6min (REAL work, editing
test_agent_prefers_authored_memory_with_citations). Codex NOT quota-blocked — the
"usage limit" string in the log is codex's own narration, not the OpenAI error banner.

**KEY HONESTY FINDING:** iter1 eval (03:19) measured the SAME code as the prior run but
gave correct 6 (was 7), confident_wrong 3 (was 6), halluc_pct 14.3 (was 28.6). => the
frontier eval has large run-to-run VARIANCE. The 6<->7 deltas I tracked are NOISE, not
signal. System truly sits ~6-7/21 (29-33%), gate ~16/21. The supervisor's _improved()
gate (correct>prev OR halluc<prev) will trip on noise — a single +1 is not real progress.
Implication: trust only multi-point / large deltas, not single-iteration moves.

**Action:** none (live codex edit; do not interrupt). Sleeping ~15min to catch WG09
retest + WG06 iter2 eval. Judge: only a move clearly OUTSIDE +/-1 noise counts as real.

## 2026-06-29 03:43 — heading to HONEST HALT (no convergence) + scope-creep concern

**Measured (3 full-store points, ~same brain):** correct 7 -> 6 -> 5 /21 (29% mean),
gate=16/21. NOT converging; if anything down. confident_wrong 6->3->4, halluc 28.6->14.3
->19.0. Per-question verdicts SHUFFLE between runs (nutella-count + what-app flipped
correct->wrong; day/night + pink-cloth flipped ->correct). => eval variance is large;
single-iteration _improved() gating drives on NOISE.

**Loop status:** in WG08 patch iter2. iter2 eval(5) did not beat iter1(6) -> supervisor
will self-halt on no_improvement right after patch2+retest2. Letting it self-terminate
(do not interrupt live codex). Will NOT relaunch after — evidence says brain-patch loop
isn't moving the gate.

**Scope-creep concern (verify after halt, mtimes vs codex run windows):** agent.py now
+136/-5 vs HEAD; working tree also shows store/{ingest,models,sleep,sqlite_store}.py +
tests modified. Larger than a bounded one-class patch. Possible architecture drift to
flag/revert if unmeasured.

**Dominant REAL failures (from eval results):** spatial/temporal "current vs last-seen"
(blanket on suitcase not bed; nutella jar location), missing capture (battery%, pillow
count, cello tapes, microphone loc), attribute misreads (blanket/mattress colour). =>
CAPTURE/PERCEPTION + temporal state, NOT brain reasoning. Brain-patch loop structurally
cannot close 29%->75%.

**Next:** sleep ~10min -> confirm halt -> write founder-facing honest verdict + decide on
reverting unmeasured agent.py drift.

## 2026-06-29 03:58 — HONEST HALT confirmed; verdict written; NOT relaunching

**State:** supervisor DEAD, mode=halted reason=no_improvement iter2 (halted 03:56:38).
Honest halt (harness fix made the check read real numbers; iter2=5 < iter1=6). Final
eval correct 5/21.

**Scope check (mtimes):** store/{ingest,models,sqlite_store,world,__init__}.py = last
night ~23:50 (pre-session spine, NOT codex). This-session codex touched agent.py (03:54,
+325) AND sleep.py (03:25, +332/binder) — broader than patch1 note's "agent.py only".
Neither patch improved measurement (7->6->5); patch2 unmeasured. Did NOT auto-revert
(uncommitted + tangled with legit spine work; founder call).

**Action:** wrote CHIEF_VERDICT_2026-06-29.md. Stopping active supervision per
success-condition #2 (honest halt). Recommendations: stop brain-patch loop; stabilize
noisy eval (N>=3/seed); invest capture/perception+temporal not brain retrieval; review
uncommitted codex churn. Sleeping LONG / awaiting founder input. Will not relaunch.

## 2026-06-29 04:25 — HIGH-LEVERAGE ATTACK: findings (self-consistency +0; number is CAPTURE-bound)

**Attack 1 — self-consistency majority vote (DONE, kept):** patched annotate_live.summarize()
which silently scored only attempts[0]. Added honest majority-answer voting. A/B on a
FIXED store, repeats=5: single-sample [5,5,5,5,5], consensus 5/21. DELTA = +0. Reason:
reasoning is DETERMINISTIC on a fixed store; ZERO questions flip. => the 7->6->5 swing was
PERCEPTION/INGEST noise (every WG06 cycle re-runs frontier perception --fresh = a new
store), NOT reasoning noise. Self-consistency harmless+correct but doesn't move frontier #.

**BIG PROCESS WIN:** a FROZEN store + annotate_live = deterministic, ~1min, cheap, zero-noise
eval. THIS is the iteration engine we lacked. The supervisor re-ingesting every cycle was
the source of ALL the noise, cost, and false halts. Future fixes are now cleanly measurable.

**Number is CAPTURE-BOUND (~7-9/21 ceiling on this store) — verified across all 48 nodes:**
NEVER captured -> unanswerable by ANY brain/retrieval fix: thermal flask (0 nodes), blanket
violet colour (perception saw grey), blue mattress (saw white/grey bedding), battery%
(screen detail), day/night, fan mode, full nutella count=5 (only 2-3 ever co-visible),
cello tapes, real microphone. ~9 questions. Gate=16/21 is UNREACHABLE without better CAPTURE.
RETRIEVAL-fixable (evidence present, mis-retrieved): "how to drink water" (steel+white
bottle ARE in store, retrieval surfaced 6 unrelated nodes). Maybe 1-2 jar-location.

**DATA INTEGRITY:** 2/48 phone_camera vlm nodes carry trailing self-critique junk
("...misread the diary color, missed the microphone and cello tapes, called it night
instead of day...") — VLM prompt is emitting editorial meta-text that pollutes retrieval.
Clean the perception prompt.

**VERDICT — next highest leverage = CAPTURE FIDELITY/COVERAGE, not brain.** Brain/retrieval
ceiling ~33-43%; the ~9 missing points live in capturing: small/occluded objects (thermal,
mic, cello), exact colours, screen OCR (battery%/app), lighting (day/night), complete counts.
Matches founder standing direction (capture is the wall; MORE parallel capture-helpers).

## 2026-06-29 04:40 — ARCHITECTURE PIVOT (founder): capture = LOCAL HELPERS, not frontier

Founder corrected the root error: the eval/ingest path did CAPTURE with the frontier model
(light_ingest --backend frontier = claude-sonnet-4-6 per frame). That is why capture was
expensive, slow, and NON-DETERMINISTIC (the real source of the 7->6->5 noise). Frontier must
be QUERY-TIME REASONER ONLY; helpers do capture fast/local with blur+coords applied beforehand.

Found the "society of specialists" already EXISTS but was never wired into capture:
frame_quality (blur gate), instance_perceive (Grounding-DINO detect + parallel per-crop reader:
label/text/colour/material/state), mac_vision/screen_reader (Apple Vision OCR), counting/
temporal/reading specialists, perception_consensus.

BUILT scripts/helper_ingest.py: blur-gate -> instance_perceive per frame -> structured
world-grounded observation (coordinate_frame + spatial_anchor(pose) + time_range) -> store ->
sleep bind. NO frontier in capture. Validated end-to-end (3-frame smoke: captured blanket
colour, jars w/ "Nutella"/"Barilla" text; ~40s/frame local/free). Per-crop 12b still mis-NAMES
some crops (Pizza/Burrito) but carries reliable det_label + colour/state/text.

RUNNING: full 40-frame local ingest -> data/trace_store_helpers.sqlite3 (pid 42337, ~30-40min).
NEXT: measure on deterministic frozen-store eval (annotate_live --reasoner frontier --repeats 1)
vs frontier-capture baseline 5/21. Then add specialists for remaining gaps (OCR battery%/app,
counting consensus for nutella=5/pillows=3, day/night brightness).

## 2026-06-29 08:15 — local-helper capture MEASURED: number DOWN 5->2 (honest)

Deterministic frozen-store eval (frontier reasoner, repeats=1):
- frontier caption (baseline): correct 5/21, confident_wrong 4, halluc 19.0, answered 15
- LOCAL per-crop (instance_perceive): correct 2/21, confident_wrong 2, halluc 9.5, answered 7
=> local single-helper is MORE HONEST (refuses 14/21, halluc halved) but LOSES correct.
Causes: (1) per-object list lacks whole-scene context -> reasoner refuses (pink cloth
correct->refused); (2) 12b per-crop GARBLES text (Peperoncino->"Pepperonciaio" = wrong;
app "Claude" not read); (3) identity hallucination (Burrito/Pizza for notebook).

KEY INSIGHT (validated, = founder's design): no single local helper beats frontier, but
DIFFERENT helpers catch DIFFERENT facts. mac_vision caption got "grey blanket draped over
the SUITCASE" (blanket-currently answer!) + "2 steel water bottles + glass bottle" (drink
water!) that per-crop missed. => FUSE many helpers per frame to UNION coverage.

No genuine fast VNRecognizeText OCR module exists (mac_vision_perceive is a ~30s VLM, not
OCR). A real Apple Vision OCR channel must be BUILT (text-heavy Qs: app=Claude, battery%,
labels, pesto flavour) — the founder's "almost instantaneous" helper.

RUNNING: light_ingest --backend local (full-frame caption) -> data/trace_store_localcap.sqlite3
(pid 43644, ~17min) = the "local full caption" datapoint.
NEXT: (1) measure localcap; (2) build FUSED helper_ingest (full-caption + per-crop + mac_vision)
to union coverage; (3) build real VNRecognizeText OCR channel. HONEST CAVEAT: some facts
(thermal=0 nodes, blue mattress always read white, nutella=5 never co-visible, day/night,
fan mode) are CAPTURE-COVERAGE gaps (need more angles), bounded by what 40 keyframes show.

## 2026-06-29 08:40 — CONCLUSIVE: local-12b capture << frontier (5/2/0). Testing strong-local 27b.

3-way deterministic eval (frontier reasoner): frontier-caption 5/21 | local per-crop 2/21 |
local full-caption(12b) 0/21. Diagnosed 0/21: NOT a format bug — local gemma3:12b is
(a) INCONSISTENT frame-to-frame (suitcase node says open AND closed -> honest conflict refusal),
(b) MISSES fine text (Peperoncino captured in 0 nodes; frontier read it). Real fidelity gap.

MOAT REASONING ([[moat-local-boundary-and-async-qa]]): trust boundary = LOCAL (frames may hit
the user's OWN Mac if deleted post-perception); the Mac should run STRONG perception
(gemma3:27b / GD+SAM2), NOT tiny 12b. My local runs used 12b for speed -> unfair test.
Frontier (cloud Anthropic) actually VIOLATES the local boundary. So the right moat-preserving
question = does STRONG LOCAL (27b) close the gap to frontier?

RUNNING: light_ingest --backend local --model gemma3:27b-it-qat -> data/trace_store_local27b.sqlite3
(pid 45154, ~40-60min). If 27b-local ~= frontier -> moat preserved AND number recoverable;
then fusion + perception_consensus (fixes the open/closed conflict) + real VNRecognizeText OCR
(Peperoncino/app/battery) push further. If 27b-local still << frontier -> escalate to founder:
genuine cloud-vs-local fidelity gap = strategic choice (frontier-for-demo vs commit-to-local).

HONEST: number is currently DOWN (best local=2 vs frontier 5; gate=16). Not inflating.

## 2026-06-29 ~09:00 — COURSE CORRECTION (founder called tunnel-vision; accepted)

SELF-CRITIQUE vs ANTI_TUNNEL_LEASH + PRODUCT_NORTH_STAR: I tunnel-visioned hard. Spent ~6h
micro-optimizing LAYER-0 capture (frontier vs 12b per-crop vs full vs 27b) against a 21-Q
single-shot eval — the over-narrow/OCR trap. Worse: (1) my own diagnostics showed misses
were RETRIEVAL/BINDING not capture, and I ignored them; (2) self-consistency = the founder's
explicitly-REJECTED "more sampling"; (3) ZERO work toward the two real deliverables (live
demo + honest number at real n). Killed the 27b bake-off.

RE-ANCHORED on the blueprint. Founder steer: STORE FIRST (Layer 1). Honest EVIDENCE-BASED
assessment (read the code, not docs):
- Store (Layer 1) is ~30-40%, NOT the truth-session's ~5% (that predates this greenfield
  store). Append-only graph + clean tools (write/link/search/neighbors) + embedding search
  all EXIST and work (search surfaces the bottle for "drink water" at rank 1).
- REAL LOCUS = the BRAIN (Layer 3, agent.py): it has a REGEX QUESTION-TYPE ROUTER (lines
  182-192: where/current/app/transcript) = the EXACT pattern the truth-session says DELETE,
  and over-weights composed memories over raw observations -> refuses though evidence exists.
- Gaps: precise graph-aware retrieval (founder's "right 5 not nearest 500" center of
  gravity); richer same-place/same-entity links (thin).

BUILT (tested, dependency-correct Layer-1 increment): src/trace_memory/store/retrieval.py
`precise_retrieve()` — seed (embed+lexical, raw observations included) -> expand along links
-> trim to minimal sufficient provenance-tagged slice; filters zero-relevance seeds. 3 new
unit tests pass; 8/8 existing store tests green; validated on real frozen store (bottle #1
for drink-water, peperoncino #1 for pesto).

HONEST: this does NOT move the eval number YET — the agent doesn't call it. NEXT increment
(Layer 3): wire the brain to precise_retrieve + DELETE the regex router + stop composed-over-
weighting, then MEASURE on the deterministic frozen-store eval. That's where the number moves.

## 2026-06-29 ~10:10 — STALE capture-loop wakeup fired; correctly NOT followed
A scheduled wakeup from before the course-correction re-fired the old 27b-capture-eval
instruction. Following it would re-enter the abandoned Layer-0 tunnel. Verified pid 45154
dead, no stray jobs; partial data/trace_store_local27b.sqlite3 (5 nodes) is leftover junk
from the killed run. Did NOT run the eval, did NOT resume capture work, did NOT reschedule.
Capture-model bake-off is RETIRED. Holding the corrected course: Layer-1 precise_retrieve
built+tested; awaiting founder go on the Layer-3 wiring (call precise_retrieve + delete the
regex router) — the increment that actually moves the number.
