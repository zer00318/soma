export const meta = {
  name: 'binder-verify-diagnose',
  description: 'Adversarially verify authored binder memories are grounded in citations, and diagnose each residual eval miss into a fix class',
  phases: [
    { title: 'Verify' },
    { title: 'Diagnose' },
    { title: 'Synthesize' },
  ],
}

// args = { store: "data/trace_store_rebind.sqlite3", eval: "evaluation/ras/treatment.json" }
const store = (args && args.store) || 'data/trace_store_rebind.sqlite3'
const evalPath = (args && args.eval) || 'evaluation/ras/treatment.json'

const GROUNDING_SCHEMA = {
  type: 'object',
  properties: {
    checked: { type: 'number' },
    ungrounded: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          memory_id: { type: 'string' },
          claim: { type: 'string' },
          why: { type: 'string' },
        },
        required: ['memory_id', 'claim', 'why'],
      },
    },
  },
  required: ['checked', 'ungrounded'],
}

const DIAGNOSIS_SCHEMA = {
  type: 'object',
  properties: {
    question: { type: 'string' },
    verdict: { type: 'string' },
    gap_class: {
      type: 'string',
      enum: ['capture_missing', 'perception_wrong', 'binder_missing', 'binder_wrong', 'retrieval_ranking', 'counting', 'judge_too_strict'],
    },
    evidence_exists: { type: 'boolean' },
    explanation: { type: 'string' },
    proposed_fix: { type: 'string' },
    fix_owner: { type: 'string', enum: ['binder', 'agent_retrieval', 'perception', 'none'] },
  },
  required: ['question', 'gap_class', 'evidence_exists', 'explanation', 'proposed_fix', 'fix_owner'],
}

phase('Verify')
// Fan out grounding checks over authored-memory id ranges. Each agent inspects the store
// directly (sqlite, NOT the embedding search) so it never touches the GPU.
const VERIFY_SHARDS = 4
const verifyResults = await parallel(
  Array.from({ length: VERIFY_SHARDS }, (_, shard) => () =>
    agent(
      `You are auditing the world-grounded binder for HALLUCINATION. Store: ${store}.\n` +
      `Use sqlite3 (the CLI or python3 sqlite3) to read memory_nodes. Do NOT use any embedding search.\n` +
      `Select authored memories: SELECT id, text, source_support_json, metadata_json FROM memory_nodes ` +
      `WHERE node_type IN ('entity_memory','group_memory') AND (rowid % ${VERIFY_SHARDS}) = ${shard}.\n` +
      `For each, parse support_ids from source_support_json, then read those supporting observations: ` +
      `SELECT text FROM memory_nodes WHERE id IN (...).\n` +
      `A memory is UNGROUNDED if its current_location, count, or attribute claims are NOT supported by ` +
      `the cited observations' text (allowing reasonable synonyms). Report only ungrounded claims.\n` +
      `Be adversarial: the binder used a local LLM and may have invented specifics. Return JSON.`,
      { label: `verify:shard${shard}`, phase: 'Verify', schema: GROUNDING_SCHEMA }
    )
  )
)

phase('Diagnose')
// Load the eval misses and fan out one diagnostician per wrong/refused question.
const misses = (args && args.misses) || []
const diagnoses = await parallel(
  misses.map((m) => () =>
    agent(
      `Diagnose ONE eval miss for the TRACE memory system. Store: ${store}.\n` +
      `QUESTION: ${m.question}\nGROUND TRUTH: ${m.truth}\n` +
      `SYSTEM ANSWER: ${m.answer}\nVERDICT: ${m.verdict}\n` +
      `EVIDENCE IDS USED: ${JSON.stringify(m.evidence_ids || [])}\n\n` +
      `Investigate with sqlite3 ONLY (no embedding search, no GPU): does the store actually contain ` +
      `observations that support the ground truth? Search memory_nodes.text with LIKE for the key nouns.\n` +
      `Classify the gap:\n` +
      `- capture_missing: the fact was never observed (no supporting obs anywhere).\n` +
      `- perception_wrong: observed but the helper read it wrong (e.g. wrong colour).\n` +
      `- binder_missing: obs exist but no authored memory composed them.\n` +
      `- binder_wrong: an authored memory exists but states the wrong thing.\n` +
      `- retrieval_ranking: right memory exists but wasn't surfaced/ranked to the reasoner.\n` +
      `- counting: an individuation/count error.\n` +
      `- judge_too_strict: the answer is actually right but scored wrong.\n` +
      `State whether evidence exists, explain, and propose a concrete fix + which layer owns it. Return JSON.`,
      { label: `diagnose:${(m.question || '').slice(0, 28)}`, phase: 'Diagnose', schema: DIAGNOSIS_SCHEMA }
    )
  )
)

phase('Synthesize')
const ungrounded = verifyResults.filter(Boolean).flatMap((r) => r.ungrounded || [])
const checked = verifyResults.filter(Boolean).reduce((a, r) => a + (r.checked || 0), 0)
const good = diagnoses.filter(Boolean)
const byOwner = {}
for (const d of good) byOwner[d.fix_owner] = (byOwner[d.fix_owner] || 0) + 1

const synth = await agent(
  `Synthesize a binder-sprint action report. Pitch is tomorrow; honesty floor (confident-wrong <10%) is sacred.\n` +
  `GROUNDING AUDIT: ${checked} authored memories checked, ${ungrounded.length} ungrounded claims found:\n` +
  JSON.stringify(ungrounded, null, 2) + `\n\n` +
  `PER-MISS DIAGNOSES:\n` + JSON.stringify(good, null, 2) + `\n\n` +
  `Produce: (1) the single highest-leverage fix that is binder- or retrieval-owned (in-scope tonight), ` +
  `(2) which misses are capture/perception-bound and out of scope, (3) any ungrounded authored memory that ` +
  `risks a confident-wrong answer and must be suppressed. Be concise and concrete.`,
  { label: 'synthesize', phase: 'Synthesize' }
)

return {
  grounding: { checked, ungrounded_count: ungrounded.length, ungrounded },
  diagnoses: good,
  fix_owner_histogram: byOwner,
  report: synth,
}
