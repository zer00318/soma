# Phase 2 Work Order — Brain Fixes (drive hallucination 27% → ~0)
*From the brain-fix workflow (8 agents: 4 root-cause + 4 skeptic verdicts), 2026-06-17. All in `scripts/ask_home.py` unless noted.*

## THE one root cause (all 4 clusters share it)
The default path `ask()` → `answer_assembler` → `build_evidence_dossier` → `think_and_answer`
(ask_home.py:1443-1448, 1362-1376) **bypasses every strong retrieval/binding guard.** Those —
`_sem_retrieve` (bge-m3, :494), `attribute_rerank` (:352), `resolve_item_term` (:424), the
counting specialist — run ONLY in the LEGACY FALLBACK (:1487-1508), reached only if the assembler
throws/returns empty (≈never). The dossier's keyframe channel ranks the full kf list by literal
`_score_overlap` (:1034) — no IDF, no synonyms, no embeddings — then hard-truncates to
`max_per_channel=6` (:1008). `ASSEMBLER_GROUNDING_GATE=False` (:1359). The only guard left is a
soft prompt leash a 12B model can ignore.

**So the headline Phase-2 move = reconnect the existing strong machinery INTO the assembler.** Not
a model problem; a wiring regression.

> ⚠️ EVERY fix below is reasoned from code, NOT executed — `kf_memory.json` was wiped, so no agent
> could run retrieval. **Each fix is a hypothesis; validate by re-running the 25Q after rebuild,
> one fix at a time, watching the named regression questions.** This is the (A)/(B) discipline.

## The fixes (skeptic-revised; apply + measure in this order)

### FIX 1 — Wire strong retrieval into the dossier KF channel  [retrieval-miss Q12/Q25 + binding Q10]
*Verdict: REVISE (direction right, plumbing gaps).* In `build_evidence_dossier`, feed the KF
channel from `_sem_retrieve(question, kf, kf_path, k=12)` + `attribute_rerank(..., pool=kf)` unioned
via `_merge_scenes` with today's literal list — **recall-additive**, so the 16 correct are safe by
construction.
- Plumb `channels['kf_path']=kf_path` in `gather_evidence` (:1097) — else `_sem_retrieve` returns None.
- **Respect focus**: when `attribute_rerank` returns an EXACT-match focus, emit ONLY those frames —
  do NOT merge the literal list back over it (that re-introduces the gray-bag/wrong-poster distractor).
- Raise `_merge_scenes` cap (:477) and a KF-only cap (6→8) above the merge.
- **Fallback**: if embedder/index/kf_path missing → today's literal ranking (zero regression when cold).
- Caveat: **Q12 ("crowded?") rides entirely on bge-m3 cosine** (crowded~empty/platform) — `attribute_rerank`
  is a no-op for it (no colour/type word). So Q12 only fixes with the embedder live + `.semidx.json` warm.
- Watch for regression: Q5, Q9, Q10, Q14, Q18 (added frames could let a distractor leak), Q23 badge colour.

### FIX 2 — Binary-state refusal clause + surface "checked-couldn't-tell"  [binary-state Q17/Q24]
*Verdict: ADOPT.* This is the cleanest hallucination kill.
- **EDIT 2 (load-bearing):** append ONE rule to `ASSEMBLER_PROMPT` (~:1306): if the question asks
  whether something is in a particular STATE (open/closed, zipped/unzipped, plugged/unplugged,
  sent/unsent, empty/has-a-draft, on/off) and NO line explicitly reports that state for THAT item,
  reply "I don't have that in my memory." — do NOT assume the expected default.
- **EDIT 1 (helper):** in the OBJECT ATTRIBUTES section (:1223), stop dropping `unknown` values —
  render them as `zip=NOT CONFIRMED (checked, could not tell)` so the gap is explicit. Bound it to
  the asked attribute to avoid dossier noise.
- Effect: Q17/Q24 flip from **confident-wrong → honest refusal** (lowers the 27%). Does NOT make them
  *correct* — that needs perception fixes (deferred): extend `screen_reader.py` crop past 0.58 to
  capture the compose field (Q24 draft); improve zip read in `build_attributes.py` (Q17). Those are
  separate (A)-ish recall fixes, behind their own self-tests.
- Watch for regression: Q22/Q23 (badge "Needs Input"/colour read like on/off states) — tighten the
  clause to fire only when NO line reports the state; verify the badge questions stay answerable.

### FIX 3 — Counting Q3: inject region-level evidence into the dossier (do NOT patch the specialist)  [counting Q3]
*Verdict: REVISE / root-cause CORRECTED.* The proposed counting_specialist patch is **dead code** —
the assembler answers Q3 with gemma prose, not the specialist (proof: live answers are "one warning
sign and one button", not the specialist's "I counted N…" template). And reverting to specialist-first
reintroduces the "at least 7 signs" regression. **Real fix:** surface per-region door-plate OCR
(from each frame's `ocr` list, not the joined `_ocr_txt`) into the dossier so gemma can count the
~2 distinct plates, + a tiny range-cap from the question ("two or three" → cap 3). Lowest priority;
needs the rebuilt `kf_memory.json` to confirm the door sign is stored as 2-3 regions.

### FIX 4 — Turn the grounding gate on (measured)  [hallucination backstop]
`ASSEMBLER_GROUNDING_GATE=True` (:1359) adds a second verify pass. It currently only flags unsupported
entities/numbers/biography — **not** binary states — so extend `GATE_PROMPT` to also flag unsupported
state claims. Measure the latency vs hallucination tradeoff on the 25Q (gate on vs off).

## Expected impact (to be measured, not claimed)
- FIX 2 alone: Q17+Q24 confident-wrong → refusal ⇒ hallucination drops (2 of 6 wrong removed).
- FIX 1: Q25 (synonym pull) and Q12 (semantic) → correct *if embedder warm*; helps Q10.
- Q2 (which sign) and Q18 (which bag) are the hardest — wiring alone may not fix them (need
  resolve_item_term + possibly better captions / a colour-word fix since "colour" isn't in COLOUR_WORDS).
- Net target: from RAS 40 / 27% → materially higher RAS / single-digit hallucination, **verified live**.

## Apply protocol (gated)
1. Restore runtime + rebuild `world_memory.json`/`kf_memory.json` from the clip.
2. Re-run the 25Q LIVE → confirm the ~40/27 baseline reproduces on the restored stack.
3. Apply FIX 2 → re-run 25Q → record delta + check Q22/Q23.
4. Apply FIX 1 → re-run 25Q → record delta + check Q5/Q9/Q10/Q14/Q18/Q23.
5. Apply FIX 3, FIX 4 → re-run → record.
6. Each step: tag any new miss (A)/(B); never ship a fix that regresses the 16 correct.

## Key files/lines
`scripts/ask_home.py`: ask 1443-1448 · answer_assembler 1362-1376 · build_evidence_dossier 1102-1135 ·
_score_overlap 1034-1040 · ASSEMBLER_MAX_PER_CHANNEL 1008 · _sem_retrieve 494-504 · attribute_rerank
352-422 · resolve_item_term 424-474 · _question_attributes 258-284 · COLOUR_WORDS 223-227 ·
TYPE_SYNONYMS 239-250 · ASSEMBLER_PROMPT 1285-1310 · gate 1359 · GATE_PROMPT 791-808 · OBJECT
ATTRIBUTES section 1205-1227. `scripts/build_attributes.py`: zip 191-204. `scripts/screen_reader.py`:
crop 97-102. `scripts/counting_specialist.py`: _count_from_kf 567-676.
