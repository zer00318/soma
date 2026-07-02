# CODEX BRIEF 17 — cross-frame consensus / hallucination control

Branch: `codex/17-consensus`. Python via `.venv/bin/python`. Create ONE new module
`scripts/perception_consensus.py` + tests `tests/test_perception_consensus.py`.
Do NOT edit instance_consolidate.py, the brain, or trace-native-fastvlm/ (avoids conflicts).

## Why
The per-crop VLM HALLUCINATES products that aren't there — a single blurry crop returned
"Doritos", "Little Caesars pizza", "Alexa smart speaker" (it was a laptop), each appearing in
exactly ONE frame. A real object on a desk is seen across MANY frames as the camera lingers/pans.
So consensus = truth filter: assert what recurs, demote what appears once.

## The module: `scripts/perception_consensus.py`

```python
def tier_instances(consolidated: dict, total_frames: int) -> dict:
    """Tag each consolidated instance with a confidence tier based on how many frames
    it was seen in (cross-frame consensus). Returns a NEW dict (don't mutate input).

    consolidated = output of instance_consolidate.consolidate()/consolidate_world():
        {"instances": [ {..., "count_frames": N, "frames": [...]} ], "counts_by_type": {...}, ...}

    For each instance add "tier":
        "confirmed"   if count_frames >= 2
        "provisional" if count_frames == 1
    Add "confidence": round(min(1.0, count_frames / 3.0), 2).

    Add a top-level "confirmed_counts_by_type": like counts_by_type but counting ONLY
    confirmed instances (provisional/one-off reads excluded) — this is the honest count.
    Keep the original counts_by_type untouched (it's the upper bound).

    Add "summary_confirmed": one line listing confirmed counts.
    """

def confident_instances(consolidated: dict) -> list[dict]:
    """Return only the instances with tier == 'confirmed' (seen in >= 2 frames)."""
```

## Honest rule
- A 1-frame instance is NOT a lie to assert exists, but it must be hedged/demoted — when asked
  "how many X", the answer should use confirmed_counts (>=2 frames) as the trustworthy number and
  may mention provisional ones separately. This module just produces the tiers; the brain decides
  how to phrase. Do NOT delete provisional instances — keep them, just tier them.

## Acceptance tests (`tests/test_perception_consensus.py`)
1. 3 instances: jar seen in 4 frames, jar seen in 3 frames, "doritos" seen in 1 frame
   (total_frames=8) -> first two "confirmed", doritos "provisional";
   confirmed_counts_by_type for jar == 2 (not 3).
2. confidence: count_frames 1 -> ~0.33, 2 -> ~0.67, 3+ -> 1.0.
3. confident_instances() returns only the 2 confirmed.
4. All-provisional input (every instance 1 frame) -> confirmed_counts_by_type all 0 or empty;
   summary_confirmed says nothing confirmed.
5. Input not mutated (original counts_by_type unchanged; no "tier" key added to the input object).
6. Empty input -> safe empty output.

## Guardrails
- Pure, deterministic, no I/O. `pytest tests/ -q` green. Commit on branch. Report the 6 results.
