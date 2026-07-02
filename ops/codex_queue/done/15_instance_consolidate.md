# CODEX BRIEF 15 — cross-frame instance consolidator (spatial mapping core)

Branch: `codex/15-consolidate`. Python via `.venv/bin/python`. Additive — create ONE new module
`scripts/instance_consolidate.py` + tests `tests/test_instance_consolidate.py`. Do NOT edit the
brain server, instance_graph, or instance_perceive. Do NOT touch trace-native-fastvlm/.

## Why
Today the brain keeps only the LATEST frame's instance graph, so counting is per-frame and wrong
("one jar" when 3 are present; or 4→5→6 as the camera pans the SAME jars). We need to accumulate
instances across ALL frames of a moment and consolidate the same physical object into ONE node,
so count = number of distinct physical instances (hedged honestly), not per-frame recounts.

## The module: `scripts/instance_consolidate.py`

```python
def consolidate(frame_instances: list[list[dict]],
                frame_yaws: list[float | None] | None = None) -> dict:
    """Consolidate per-frame instance detections into a canonical instance set.

    frame_instances[i] = list of instance dicts from frame i. Each instance dict has
      (some keys may be missing): "type" (or "det_label"), "name"/"brand", "text",
      "colour", "material", "state", "orient", "box" ([x,y,w,h] normalized).
    frame_yaws[i] = camera yaw in degrees for frame i (from ARKit/CoreMotion pose), or None.

    Returns:
      {
        "instances": [ {canonical instance: merged attrs + "type", "label",
                        "frames":[i,...], "count_frames":N} , ... ],
        "counts_by_type": { "jar": {"distinct": 3, "hedge": "3-4"}, ... },
        "summary": "<one-line human summary>",
      }
    """
```

## Consolidation rule (the core logic)
Two detections are the SAME physical instance when ALL hold:
1. Same normalized TYPE (lowercase, singularize: "jars"->"jar"; map obvious detector synonyms,
   e.g. "bottle"/"jar" stay distinct but "cup"/"cups" merge).
2. Same TEXT/BRAND signature when both have non-empty text: normalized text overlaps strongly
   (token Jaccard >= 0.6 on alphanumeric tokens, case-insensitive). If BOTH lack text, fall back
   to (colour+material) signature match.
3. If yaws are provided for both frames: bearing within 25 degrees (same direction). If yaw is
   None for either, skip this check (don't block the merge on missing pose).

Greedy clustering: iterate detections in frame order; assign each to the first existing cluster it
matches, else start a new cluster. Merge attrs by majority/longest-non-empty.

## Honest hedging (critical — do NOT fabricate precision)
- Same type + SAME text seen across frames = ONE distinct instance (camera saw it repeatedly).
- Same type but DIFFERENT texts = that many distinct instances.
- Same type, NO text on any (can't disambiguate): report distinct = max single-frame count of
  that type, and hedge = "1-{max}" (we cannot tell identical untexted objects apart across frames
  without world coordinates). Put this uncertainty in the hedge string.
- counts_by_type[t]["distinct"] = best estimate; ["hedge"] = "N" if confident else "lo-hi".

## Acceptance tests (`tests/test_instance_consolidate.py`)
1. Same Nutella jar (type="jar", text="nutella") in 5 frames -> 1 distinct jar, not 5.
2. 3 distinct jars (texts "nutella","pesto","pringles") each in several frames -> 3 distinct jars.
3. Mixed: 3 texted jars + a 4th jar with no text -> distinct>=3, hedge reflects the untexted one.
4. Two frames, type "cup" no text, colour differs (red vs blue) -> 2 distinct (colour signature).
5. Same type+text but yaws 0 deg and 180 deg (opposite directions) -> 2 distinct (bearing split).
6. Empty input -> {"instances":[], "counts_by_type":{}, "summary": "<nonempty>"}.

## Guardrails
- Pure function, no I/O, no network, no LLM calls — deterministic clustering only.
- `pytest tests/ -q` stays green. Commit on branch. Report the 6 test results + an example
  consolidated output for the 3-distinct-jars case.
