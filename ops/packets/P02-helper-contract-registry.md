# P02 — The helper contract + plugin registry
wave: W0 · tag: judgment · executor: Fable · depends: none
This packet is the keystone of L7 (open registry): every W2 channel builds against it.

## Context (self-contained)
Today helpers are hardcoded: Swift-side enums/strings (`helper_prompt` values like
`vlm_object`, `detector`, `vision_ocr`, `apple_speech`) flow into `Hub.ingest`
(`scripts/trace_hub.py`) and land in the store (`src/trace_memory/store/ingest.py`,
`models.py`). Adding a channel means touching the spine. The founder's requirement:
helpers are PLUG-AND-PLAY — users can add their own; the list is never closed.

## Laws that bind you
L1 (privacy fields must make the boundary auditable), L4, L5, L7. Merge gate: pytest green,
canonical battery holds 96.7/100/0/100, spot check on data/trace_store.sqlite3.

## Do
1. Define the observation contract as a versioned schema (one place, both sides consume):
   `{text, t_ms, anchor_id?, fingerprint?, confidence, helper_id, provenance, session_id}`
   — `helper_id` replaces ad-hoc helper_prompt strings (map old → new, keep reading old rows).
2. Registry = data: a `helpers.toml` (or json) the hub loads — id, kind (standing|dispatched),
   pillar (phone|mac|owner), dispatch_hint. Unknown-but-schema-valid helper_ids ingest fine
   and appear in the registry report; nothing about an unknown helper crashes the spine.
3. Ingest seam validates the contract, rejects schema violations loudly (log + count), and
   tags every row with helper_id + provenance so the Leash can compute per-channel coverage.
4. Back-compat: all 241 tests + the canonical battery fixtures ingest unchanged.
5. A 20-line example plugin (`scripts/example_helper.py`) that posts a valid observation —
   the template users copy.

## Forbidden
No content lexicons. No per-helper answering logic in agent.py (one owner per question).
Do not migrate/rewrite existing store rows — read-compat only.

## Done when
pytest green + battery holds + example plugin ingests end-to-end into a scratch store and
its row is retrievable via /ask evidence. INDEX flipped.
