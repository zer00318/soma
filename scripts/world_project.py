#!/usr/bin/env python
"""Project a per-instance 2D detection box to a world-aligned 3D coordinate.

The capture gives, per frame:
  - depth.json: a sparse h×w grid (6×8) of CAMERA-FRAME 3D points (x right, y up, z fwd-negative).
  - pose.json:  camera ORIENTATION (quaternion qx,qy,qz,qw). No translation.

So we read the instance's depth from the grid cell under its box centre, then rotate that
camera-frame point by the camera orientation into a world-ALIGNED frame (shared across frames
up to the unknown — and for a pan-dominant capture, small — translation). That gives each
physical object a roughly stable coordinate, which is what lets the binder individuate
instances by 3D proximity (5 nutella jars at 5 coords -> 5 instances) instead of collapsing
them by label.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def _quat_to_matrix(qx: float, qy: float, qz: float, qw: float) -> np.ndarray:
    n = (qx * qx + qy * qy + qz * qz + qw * qw) ** 0.5
    if n == 0:
        return np.eye(3)
    qx, qy, qz, qw = qx / n, qy / n, qz / n, qw / n
    return np.array([
        [1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
        [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
        [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)],
    ])


def instance_world_xyz(
    box: list[float] | tuple[float, float, float, float],
    img_wh: tuple[int, int],
    depth: dict[str, Any] | None,
    pose: dict[str, Any] | None,
    world_depth: bool | None = None,
) -> tuple[float, float, float] | None:
    """Return world-aligned (x,y,z) for the object in `box`, or None if depth is missing.

    box: [x0,y0,x1,y1] in pixels. img_wh: (W,H). depth: {'h','w','pts':[[x,y,z]*h*w]}.

    Two depth regimes:
      - WORLD depth (6-DOF ARKit capture): `pts` are already world coordinates (raycast hits),
        so the grid cell under the box IS the object's stable world position — return it directly.
        Same object across frames -> same coordinate -> no drift -> correct counts. This is the
        product-correct path (auto-detected when the pose carries a camera transform/position).
      - CAMERA-frame depth (legacy orientation-only capture): rotate the camera-frame point by
        the device attitude into a world-ALIGNED frame; drifts under translation (a bandage).
    """
    if world_depth is None:
        world_depth = bool(pose and ("transform" in pose or "position" in pose or "arkit_camera" in pose))
    if not depth or "pts" not in depth:
        return None
    h, w = int(depth.get("h", 0)), int(depth.get("w", 0))
    raw_pts = depth.get("pts")
    if not isinstance(raw_pts, list) or not all(isinstance(p, (list, tuple)) and len(p) == 3 for p in raw_pts):
        return None
    try:
        pts = np.asarray(raw_pts, dtype=float)
    except (ValueError, TypeError):
        return None
    if h <= 0 or w <= 0 or pts.ndim != 2 or pts.shape[1] != 3 or pts.shape[0] < h * w:
        return None
    W, H = img_wh
    cx = 0.5 * (box[0] + box[2]) / max(W, 1)   # normalised box-centre, 0..1
    cy = 0.5 * (box[1] + box[3]) / max(H, 1)
    col = min(w - 1, max(0, int(cx * w)))
    row = min(h - 1, max(0, int(cy * h)))
    grid = pts[row * w + col]
    if not np.all(np.isfinite(grid)):
        return None
    # Reject invalid/missing depth: a cell that returned ~0 (or a near-origin point) is "no depth
    # here", not "object 2cm from the lens". Without this, every object with a missing-depth view
    # gets a spurious second instance clustered at the origin -> systematic over-counting.
    if abs(float(grid[2])) < 0.12 or float(np.linalg.norm(grid)) < 0.12:
        return None

    # 6-DOF path: the grid point is ALREADY a stable world coordinate — return it directly.
    if world_depth:
        return (round(float(grid[0]), 4), round(float(grid[1]), 4), round(float(grid[2]), 4))

    # The grid is too coarse (48 cells) to separate objects in the same cell, so use it only for
    # RANGE (z) and recover finer x,y from the box-centre pixel via a focal scale self-calibrated
    # from the grid's own geometry: across cells, x ≈ (u-0.5)·kx·|z|, y ≈ -(v-0.5)·ky·|z|.
    z = grid[2]
    us = (np.arange(w) + 0.5) / w - 0.5      # per-column normalised x offset
    vs = (np.arange(h) + 0.5) / h - 0.5      # per-row normalised y offset
    U = np.tile(us, h)
    V = np.repeat(vs, h if False else 1)      # placeholder; recomputed below
    V = np.repeat(vs, w)
    absz = np.abs(pts[:, 2])
    good = (np.abs(U) > 1e-3) & (absz > 1e-3)
    kx = float(np.median(pts[good, 0] / (U[good] * absz[good]))) if good.any() else 1.0
    goodv = (np.abs(V) > 1e-3) & (absz > 1e-3)
    ky = float(np.median(-pts[goodv, 1] / (V[goodv] * absz[goodv]))) if goodv.any() else 1.0
    cam = np.array([(cx - 0.5) * kx * abs(z), -(cy - 0.5) * ky * abs(z), z])
    if not np.all(np.isfinite(cam)):
        cam = grid

    if pose:
        q = (float(pose.get("qx", 0)), float(pose.get("qy", 0)),
             float(pose.get("qz", 0)), float(pose.get("qw", 1)))
        world = _quat_to_matrix(*q) @ cam
    else:
        world = cam
    return (round(float(world[0]), 4), round(float(world[1]), 4), round(float(world[2]), 4))
