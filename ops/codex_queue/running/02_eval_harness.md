# CODEX BRIEF 02 — honest-number eval harness over the event log

Branch: `codex/02-eval-harness`. Python via `.venv/bin/python`. Additive; do not touch
`trace-native-fastvlm/`. Depends on brief 01 (event-log persistence + object-grounded answering).

## Goal
A small, repeatable eval that measures the brain's HONESTY on a frozen gold set, so we have a
real number (correct % and hallucination %) instead of vibes.

## Tasks
1. `evaluation/gold/scene_gold.json`: a small gold file — a list of items, each:
   `{ "moment": "<id>", "question": "...", "expect": "answer" | "refuse", "must_contain": ["..."]? }`.
   Seed it with ~12 entries spanning: a present object (expect answer + must_contain), a flavour/label
   reading (answer), an absent thing like "rings"/"pesto" when not in scene (expect refuse), and an
   OCR-only term like "nutella" with no nutella object (expect refuse).
2. `evaluation/run_scene_eval.py`: for each gold item, call the brain's answer path over the event-log
   memory for that moment, then classify each result as correct / wrong / hallucination:
   - expect=="refuse": correct if the answer is a refusal; HALLUCINATION if it asserts content.
   - expect=="answer": correct if not refused AND all `must_contain` substrings present; else wrong.
   Print a summary: N, correct %, hallucination %, and the per-item table. Exit 0 always.
3. Make it runnable offline against a fixture event log (build a tiny `events.db` fixture in the
   script or under `evaluation/gold/` so the eval runs without a live capture).

## Acceptance (add `tests/test_scene_eval.py`)
- Running the eval on the fixture prints a summary with correct% and hallucination% and a per-item table.
- An item expecting "refuse" that the brain answers is counted as a HALLUCINATION (not just "wrong").

## Guardrails
- Additive; `.venv/bin/python -m pytest tests/ -q` must pass. Commit on the branch (do not push/merge).
- Report a summary + the pytest result + an example eval run.
