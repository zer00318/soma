# CODEX BRIEF 18 — world-coordinate binder (counting by distinct 3D location)

Branch: `codex/18-world-binder`. Python via `.venv/bin/python`. Create ONE new module
`scripts/world_binder.py` + tests `tests/test_world_binder.py`. Do NOT edit other files.

## The architecture (why this exists)
Individuate physical objects by WORLD COORDINATE, not by the VLM's (noisy/inconsistent) text.
The phone (ARKit) raycasts a grid of screen points to world (x,y,z) and sends it per frame. Each
detected instance's box center is projected to a world coordinate via that grid. The SAME physical
object seen across frames lands at the SAME world coordinate (one node); two objects at different
coordinates are two nodes — regardless of what the VLM calls them. The binder NEVER counts; it just
makes each distinct-location object a distinct node with its bound attributes. The brain counts nodes.

## The module: `scripts/world_binder.py`

```python
def sample_world(box, img_wh, depth_grid):
    """World (x,y,z) for a detection's box center, via the phone's raycast grid.
    box = [x0,y0,x1,y1] px; img_wh=[W,H].
    depth_grid = {"w":gw,"h":gh,"pts":[ [x,y,z] | None, ...]}  # row-major, gw*gh entries,
        each is the world point the phone raycast hit at that screen cell, or None (no hit).
    Take the box center in normalized [0,1] coords, find the grid cell it falls in, and return the
    NEAREST non-None grid point (search outward up to 2 cells). Return None if none found.
    """

def bind_world_instances(frame_instances, frame_depth_grids, eps_m=0.12):
    """Cluster detections across frames into distinct world-located nodes.

    frame_instances[i] = list of instance dicts (type/det_label, text/name/brand, box, img_wh...).
    frame_depth_grids[i] = the depth_grid for frame i (or None).

    For each instance: world = sample_world(box, img_wh, grid). Cluster by EUCLIDEAN 3D distance:
    an instance joins an existing node if same normalized type AND within eps_m metres of the node's
    centroid; else a new node. Instances with NO world coordinate (grid miss / no grid) go to a
    SEPARATE text/type fallback bucket (cluster by type+text) so they aren't lost — mark those nodes
    "located": False.

    Each node: {"world_xyz":[x,y,z] | None, "type":t, "texts":[all distinct reads],
                "label":..., "frames":[i...], "count_frames":N, "located":bool, "attrs":{merged}}.
    Node centroid = running mean of member world points.

    Return {"nodes":[...], "counts_by_type": {t: {"distinct":n, "located":n_located}},
            "summary": "..."}.  distinct = number of nodes of that type.
    """

def count_of(binder_result, query_noun):
    """Helper: distinct count of nodes whose type OR any text matches query_noun (singularized,
    substring). Returns int. (e.g. count_of(res, 'nutella') scans node texts.)"""
```

## Honest rules
- Located nodes (real world coord) are the trustworthy count. Unlocated (grid-miss) nodes are kept
  but flagged — the brain may hedge with them.
- Reuse simple helpers; keep it deterministic, no I/O / network / LLM.

## Acceptance tests (`tests/test_world_binder.py`)
1. sample_world: a center box with a populated grid returns the correct nearest world point; a grid
   of all None returns None.
2. Same jar in 4 frames, its box center projecting to ~the same world point (within 3cm) each frame
   despite text varying ("Nutella"/"Aleksandar"/"Kinder") -> 1 located node, count_frames=4.
3. Two jars 30cm apart (distinct world points) in the same frame -> 2 nodes.
4. Two detections 5cm apart (< eps) -> merged into 1 node.
5. Instance with no grid coverage -> node with located=False, still counted in distinct but flagged.
6. count_of(result, "nutella") finds nodes by text across the cluster's `texts`.

## Guardrails
- `pytest tests/ -q` stays green. Commit on branch. Report the 6 results + the node count for test 2 (must be 1).
