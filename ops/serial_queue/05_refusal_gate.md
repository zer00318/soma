# S3 / TASK 05 — REFUSAL-CONFIDENCE GATE (crush hallucination < 10%)
*SERIAL. Start only after 04 validates AND the clean-store number is measured. One task, one gate.*

## GOAL
The agent answers on thin/conflicting evidence → confident-wrong. The pitch promise is "it never
makes things up." Make that literally true: refuse BEFORE the LLM call when evidence is insufficient.
Trade coverage for honesty. 3 correct + 18 honest refusals beats 7 answered with 5 lies.

## INPUT CONTEXT
- `src/trace_memory/brain/agent.py` (answer(), _search_context(), _evidence_chain(),
  _contract_prompt(), _frontier_answer/_ollama_answer)
- `src/trace_memory/store.py` (SearchSlice.hits[].score, .node.text)
- `evaluation/ras/store_eval.json` + the per-row failure detail from the latest run
- `data/phone_captures/live/ground_truth.json` (21 founder questions)

## EXACT DIRECTIVE
Add a deterministic pre-LLM gate in `TraceMemoryAgent.answer`:
1. Compute question subject tokens (reuse `_tokens`). Require the top evidence rows to LEXICALLY
   cover the subject — if no retrieved node contains the subject tokens, REFUSE ("I didn't capture
   anything about X").
2. Confidence floor: if the best hit score < `TRACE_MIN_HIT_SCORE` (env, tune), REFUSE.
3. Conflict check: if retrieved rows give contradictory values for the asked attribute, do NOT pick
   one — return the calibrated hedge / refuse.
4. Keep the evidence-only contract for everything that passes the gate. NEVER use outside knowledge.
Do NOT reintroduce the deleted COUNT/EXISTS/ATTRIBUTE regex fast-path.

## VALIDATION METRIC
- Re-run `evaluation/annotate_live.py --reasoner frontier --store <demo store> --repeats 3`.
- GATE: `halluc_pct < 10` (non-negotiable) AND `correct > 0` (didn't refuse everything) AND result
  stable across the 3 repeats (halluc_pct spread <= 5 points).
- Write the before/after numbers into the cycle report. No threshold is "tuned" without the artifact.
