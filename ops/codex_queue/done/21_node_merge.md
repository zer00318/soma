# CODEX BRIEF 21 — jitter-absorption merge (collapse depth-noise duplicates of one object)

Branch: `codex/21-node-merge`. Python via `.venv/bin/python`. Create ONE new module
`scripts/node_merge.py` + tests `tests/test_node_merge.py`. Do NOT edit other files.

## Why
On a real physical capture the world binder counted 5 nutellas for 3 jars. Cause: estimated depth
(no LiDAR) JITTERS, so the SAME jar's world coordinate wobbles frame-to-frame and lands in 2 nodes
when the wobble exceeds the cluster radius. Fix: a post-pass that merges same-type nodes that are
(a) close in 3D AND (b) share a distinctive BRAND token — i.e. clearly the same physical object
seen with a jittery coordinate — WITHOUT merging genuinely different objects (different brand) or
far-apart ones.

## The module: `scripts/node_merge.py`

```python
# Generic words that do NOT distinguish two objects (so don't use them to justify a merge).
GENERIC = {"jar","bottle","can","container","spread","hazelnut","chocolate","cup","box","pack",
           "packet","tube","glass","of","the","a"}

def brand_tokens(node):
    """Distinctive lowercase tokens from a node's `texts`/`label` (alnum, len>=3, not GENERIC).
    e.g. a node read 'nutella'/'Nutella jar'/'Hazelnut spread' -> {'nutella'}."""

def merge_jittered(binder_result, radius_m=0.15):
    """Merge nodes that are the same physical object split by depth jitter.

    binder_result = output of world_binder.bind_world_instances: {"nodes":[...], "counts_by_type":{...}}.
    Each node has world_xyz ([x,y,z] or None), type, texts (list), count_frames, frames.

    Merge rule (union nodes A,B when ALL hold):
      - same normalized type,
      - both have world_xyz and euclidean distance <= radius_m,
      - they SHARE at least one brand token  (brand_tokens(A) & brand_tokens(B) nonempty)
        OR neither has any brand token (both generic, same type, close -> same object).
    Do NOT merge if both have brand tokens that are DISJOINT (e.g. 'nutella' vs 'barilla') —
    different products, keep separate even if close.

    Use union-find / iterate to fixpoint. Merged node: union of frames (count_frames = distinct
    frames), union of texts, world_xyz = mean of members, located True if any member located.
    Recompute counts_by_type = distinct merged nodes per type.
    Return {"nodes":[merged...], "counts_by_type":{...}, "summary": "..."}.
    """
```

## Acceptance tests (`tests/test_node_merge.py`)
1. Two 'jar' nodes 0.10 m apart, both texts containing 'nutella' -> merge to 1.
2. Two 'jar' nodes 0.50 m apart, both 'nutella' -> stay 2 (too far).
3. A 'jar' 'nutella' and a 'jar' 'barilla' 0.05 m apart -> stay 2 (disjoint brands).
4. Two 'jar' nodes 0.08 m apart, both generic (texts ['Jar']) -> merge to 1.
5. count_frames after merge = number of DISTINCT frames across members (no double count).
6. Nodes with world_xyz None are never merged by distance (kept as-is); empty input safe.

## Guardrails
- Pure, deterministic, no I/O / network / LLM. `pytest tests/ -q` green. Commit on branch. Report results.
