# CODEX BRIEF 16 — world-anchored individuation (bearing-based counting)

Branch: `codex/16-world-anchor`. Python via `.venv/bin/python`. Edit ONLY
`scripts/instance_consolidate.py` (extend it) + `tests/test_world_anchor.py` (new).
Do NOT touch the brain server, instance_perceive, instance_graph, or trace-native-fastvlm/.

## Why (the core problem)
Text/appearance dedup over-counts: the per-crop VLM reads the SAME physical jar differently
each frame ("Nutella" / "Aleksandar" / "Kinder"), so identical objects look distinct → 1 jar
counted as 4. The fix: individuate by VIEWING DIRECTION. As the camera pans, a fixed object's
WORLD bearing stays ~constant; two side-by-side objects have different bearings. Bearing is a far
more stable identity key than the VLM's inconsistent text.

## Add to `scripts/instance_consolidate.py`

```python
# Approx iPhone main-camera field of view (degrees). Used to turn a box's pixel
# offset from frame center into an angular offset from the camera's optical axis.
H_FOV_DEG = 66.0
V_FOV_DEG = 50.0

def detection_bearing(box, img_wh, cam_yaw_deg, cam_pitch_deg=0.0):
    """World bearing (azimuth, elevation) in degrees for a detection.
    box = [x0,y0,x1,y1] pixels; img_wh = [W,H]; cam_yaw/pitch = camera orientation.
    azimuth   = cam_yaw   + (box_center_x/W - 0.5) * H_FOV_DEG
    elevation = cam_pitch + (0.5 - box_center_y/H) * V_FOV_DEG   # up = positive
    Returns (azimuth_deg, elevation_deg). If box/img_wh invalid, return (cam_yaw, cam_pitch).
    """

def consolidate_world(frame_instances, frame_poses):
    """Like consolidate(), but individuate by world BEARING instead of text.

    frame_poses[i] = {"yaw": deg, "pitch": deg} (or None). When pose is missing for a
    frame, fall back to the existing text/appearance consolidation for that frame's items.

    Clustering rule: two detections are the SAME physical instance iff
      - same normalized type (reuse _normalize_type), AND
      - both have a bearing AND angular distance <= 9 deg in azimuth AND <= 9 deg in
        elevation (great-circle-ish; wrap azimuth at 360). Text is NOT required to match
        (that's the whole point) but if BOTH bearings are missing, fall back to the text/
        colour rule from _detections_match.
    Greedy clustering in frame order, same structure as consolidate().

    Returns the SAME shape as consolidate(): {"instances":[...], "counts_by_type":{...},
    "summary": "..."}. counts_by_type[t]["distinct"] = number of bearing-clusters of type t;
    hedge = str(distinct) (bearing individuation is confident — no "1-N" range needed when
    bearings exist; keep the 1-N hedge only for the no-pose text-fallback path).
    Merge each cluster's attrs with the existing _pick_value majority logic; pick the most
    common read text as the cluster label (handles the inconsistent-VLM-text case).
    """
```

Keep the existing `consolidate()` unchanged (back-compat). `consolidate_world` is the new entry.

## Acceptance tests (`tests/test_world_anchor.py`)
1. Same jar, 4 frames, camera yaw sweeps 0,5,10,15 deg, the jar's box shifts LEFT across frames
   so its azimuth stays ~constant (compute boxes so bearing is stable) → **1 distinct jar**,
   even though text differs each frame ("Nutella","Aleksandar","Kinder","nutella").
2. Two jars side by side in ONE frame (boxes at left and right, >9 deg apart in azimuth) →
   **2 distinct jars**.
3. Three jars across a pan that are genuinely distinct (3 well-separated bearings) → 3.
4. `detection_bearing`: a box centered in-frame returns (cam_yaw, cam_pitch); a box on the far
   right returns azimuth ≈ cam_yaw + H_FOV/2.
5. No-pose fallback: frame_poses all None → behaves like text-based consolidate (same counts).
6. Elevation split: two objects same azimuth but one high one low (>9 deg elevation apart) → 2.

## Guardrails
- Pure functions, deterministic, no I/O / network / LLM. Reuse existing helpers
  (_normalize_type, _pick_value, etc.). `pytest tests/ -q` stays green. Commit on branch.
- Report the 6 test results + the distinct count for test 1 (must be 1, not 4).
