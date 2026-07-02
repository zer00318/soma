# CODEX BRIEF 19 — relational helper (spatial relations between world nodes)

Branch: `codex/19-spatial-relations`. Python via `.venv/bin/python`. Create ONE new module
`scripts/spatial_relations.py` + tests `tests/test_spatial_relations.py`. Do NOT edit other files.

## Why (the founder's design)
Beyond counting, the brain needs spatial relations to reason and disambiguate: "the nutella is to
the LEFT of the pesto", "the spoon is ON TOP of the jar", "the laptop is IN FRONT of the window".
These are DERIVED FROM GEOMETRY (world coordinates), deterministically — no LLM guessing. This gives
the brain extra information so it can answer spatial questions AND better separate close instances.

## The module: `scripts/spatial_relations.py`

```python
def relations(nodes):
    """Derive pairwise spatial relations between located world nodes.

    nodes = list of dicts each with "world_xyz":[x,y,z] (world: x=right, y=up, z=toward-camera/depth
    — document the assumed axes) plus "label"/"type". Skip nodes with world_xyz None.

    For each unordered pair (a,b) emit the dominant relation(s) from the world delta (b - a):
      - horizontal: "left of" / "right of"        (x axis, if |dx| dominates)
      - vertical:   "above" / "below"             (y axis, if |dy| dominates)
      - depth:      "in front of" / "behind"      (z axis, if |dz| dominates)
      - "next to"   when centroids are within 0.15 m on the dominant-plane and similar depth
      - "on top of" when b is directly above a AND horizontally overlapping (small dx,dz, dy>0)
    Pick the 1-2 strongest relations per pair (don't spam all six). Return a list of
    {"from": a_label, "to": b_label, "rel": "...", "dist_m": float}.
    """

def describe(nodes):
    """Human-readable lines, e.g. 'Nutella is to the left of and next to Pesto (0.08 m).'
    Returns a list[str] for injection into the brain's evidence."""
```

## Axes convention (document + use consistently)
ARKit world: +x = right, +y = up, +z = toward the camera/back. State this in a comment and the
docstring so the brain prompt can rely on it.

## Acceptance tests (`tests/test_spatial_relations.py`)
1. Node A at (0,0,0), B at (0.3,0,0) -> "B right of A" / "A left of B".
2. A at (0,0,0), B at (0,0.3,0) with horizontal overlap -> "B above A" (and/or "on top of" if close).
3. A at (0,0,0), B at (0,0,0.4) -> "B in front of A".
4. A and B within 0.1 m on x with similar y,z -> includes "next to".
5. "on top of": B at (0.01, 0.12, 0.0) over A at origin -> "B on top of A".
6. nodes with world_xyz None are skipped; describe() returns readable strings.

## Guardrails
- Pure, deterministic, no I/O / network / LLM. `pytest tests/ -q` green. Commit on branch.
  Report the 6 results + one example describe() line.
