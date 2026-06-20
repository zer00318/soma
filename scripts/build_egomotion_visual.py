#!/usr/bin/env python3
"""
build_egomotion_visual.py  —  Project TRACE

VISUAL EGOMOTION from video frames (the clip has NO sensor pose, but the
camera visibly pans/tilts as the wearer walks and looks around).

We estimate per-frame-pair dominant horizontal (pan) and vertical (tilt)
camera motion using dense Farneback optical flow on consecutive frames in a
caller-supplied frame directory, then integrate the pan rate into a cumulative
*relative* heading.

--------------------------------------------------------------------------
SIGN CONVENTION  (read this before trusting any number)
--------------------------------------------------------------------------
When the CAMERA pans to the RIGHT, the world slides to the LEFT across the
sensor, i.e. the median horizontal optical-flow component dx is NEGATIVE.
We therefore define:

    pan_deg_per_s  > 0   ==>  camera turned to the RIGHT   (= +dx camera)
    pan_deg_per_s  < 0   ==>  camera turned to the LEFT

So  pan_signed_px = -median(dx_world_flow)   (we flip the sign of the flow).

cumulative_pan_deg is the running integral of pan_deg_per_s. A larger
cumulative_pan_deg at time t2 vs t1 means the camera is pointing further
to the RIGHT at t2 than it was at t1; smaller means further LEFT.

answer_relative_direction(anchor_t, target_t):
    delta = cumulative_pan_deg(target_t) - cumulative_pan_deg(anchor_t)
    delta > +thresh  -> the target view is to the RIGHT of the anchor view
    delta < -thresh  -> LEFT
    |delta| <= thresh -> AHEAD (roughly same heading)

Tilt (vertical) uses the same idea on dy: pixels slide DOWN when the camera
tilts UP, so tilt_deg_per_s > 0 means camera tilted UP. We record it but the
primary question is horizontal pan.

--------------------------------------------------------------------------
HONESTY NOTE
--------------------------------------------------------------------------
This is a head/body-worn walking clip. Forward locomotion creates a radial
flow field (expansion) that is NOT pan; footstep bounce injects vertical
jitter; people/vehicles move independently. We mitigate with the MEDIAN of
the flow field (robust to moving foreground), and we down-weight frames
whose flow is dominated by radial expansion rather than coherent translation
(low horizontal coherence -> the pan estimate for that frame is unreliable).
Each track entry carries a per-frame `coherence` (0..1). Confidence in the
direction answer is derived from |delta| relative to the integrated noise.
"""

import argparse
import json
import glob
import math
import os
import re

import numpy as np
import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))

# --------------------------------------------------------------------------
# Camera / geometry assumptions
# --------------------------------------------------------------------------
# Portrait phone-style capture, frames are 1080 (W) x 1920 (H).
# A typical phone main/ultrawide rear cam has a horizontal FOV in portrait of
# roughly 60-70 deg across the SHORT (1080 px) axis. We use 65 deg.
# This sets the px->deg scale; the *direction* (sign) does not depend on it,
# only the magnitude calibration does. We expose it in the JSON notes.
H_FOV_DEG = 65.0          # horizontal field of view across the image width
V_FOV_DEG = 100.0         # vertical FOV across the tall axis (portrait), approx

# Downscale for speed + noise robustness. Flow is computed at this width.
PROC_W = 320

# Crop fraction: ignore the outer border where rolling-shutter / vignetting /
# the wearer's hands or body tend to dominate. Keep central 80%.
CROP = 0.10

# A flow vector is only trusted if the frame's horizontal flow is reasonably
# *coherent* (the median is large relative to the spread). Below this the pan
# rate is kept but flagged low-confidence.
COHERENCE_MIN = 0.15

# Direction-decision threshold (degrees of cumulative pan delta).
DIR_THRESH_DEG = 8.0


# --------------------------------------------------------------------------
# Frame loading
# --------------------------------------------------------------------------
def _parse_t(path):
    """Extract the timestamp (seconds) from a frame filename frame_NNNNNN_<t>s.jpg."""
    m = re.search(r"_(\d+(?:\.\d+)?)s\.jpg$", os.path.basename(path))
    return float(m.group(1)) if m else None


def list_frames(frames_dir):
    paths = glob.glob(os.path.join(os.fspath(frames_dir), "frame_*s.jpg"))
    items = []
    for p in paths:
        t = _parse_t(p)
        if t is not None:
            items.append((t, p))
    items.sort(key=lambda x: x[0])
    return items


def load_gray(path):
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    h, w = img.shape[:2]
    scale = PROC_W / float(w)
    img = cv2.resize(img, (PROC_W, int(round(h * scale))), interpolation=cv2.INTER_AREA)
    # central crop
    ch, cw = img.shape[:2]
    y0, y1 = int(ch * CROP), int(ch * (1 - CROP))
    x0, x1 = int(cw * CROP), int(cw * (1 - CROP))
    return img[y0:y1, x0:x1]


# --------------------------------------------------------------------------
# Optical-flow pan estimation between two consecutive frames
# --------------------------------------------------------------------------
def pair_motion(prev_gray, gray, dt):
    """
    Return dict with:
      pan_deg_per_s, tilt_deg_per_s, coherence, dx_px_med, dy_px_med
    Sign convention applied (see module docstring): pan>0 == camera RIGHT.
    """
    flow = cv2.calcOpticalFlowFarneback(
        prev_gray, gray,
        None,
        pyr_scale=0.5, levels=3, winsize=21,
        iterations=3, poly_n=5, poly_sigma=1.1, flags=0,
    )
    fx = flow[..., 0].ravel()
    fy = flow[..., 1].ravel()

    # Robust center of the flow field. Median resists moving foreground and
    # the radial component of forward locomotion (which is ~symmetric and so
    # cancels around the median for a centered crop).
    dx_med = float(np.median(fx))   # world pixels move +x  => camera panned LEFT
    dy_med = float(np.median(fy))   # world pixels move +y (down) => camera tilted UP

    # Coherence: how much the global translation stands out from the spread.
    # MAD = median absolute deviation around the median.
    mad_x = float(np.median(np.abs(fx - dx_med))) + 1e-6
    coherence = abs(dx_med) / (abs(dx_med) + mad_x)   # 0..1

    # px width of the *cropped, downscaled* frame -> deg per px (horizontal)
    cw = prev_gray.shape[1]
    ch = prev_gray.shape[0]
    deg_per_px_x = H_FOV_DEG / cw
    deg_per_px_y = V_FOV_DEG / ch

    # SIGN FLIP: camera pan-right == world moves left == dx_med negative.
    pan_px = -dx_med
    tilt_px = -dy_med   # camera tilt-up == world moves down (+y) => flip

    pan_deg = pan_px * deg_per_px_x
    tilt_deg = tilt_px * deg_per_px_y

    return {
        "pan_deg_per_s": pan_deg / dt if dt > 0 else 0.0,
        "tilt_deg_per_s": tilt_deg / dt if dt > 0 else 0.0,
        "pan_deg_step": pan_deg,          # per-step (not per-second)
        "tilt_deg_step": tilt_deg,
        "coherence": coherence,
        "dx_px_med": dx_med,
        "dy_px_med": dy_med,
    }


def dominant_dir(pan_deg_per_s, coherence):
    if coherence < COHERENCE_MIN:
        return "uncertain"
    if pan_deg_per_s > 2.0:
        return "right"
    if pan_deg_per_s < -2.0:
        return "left"
    return "ahead"


# --------------------------------------------------------------------------
# Build the full track
# --------------------------------------------------------------------------
def build_track(frames_dir):
    frames = list_frames(frames_dir)
    if len(frames) < 2:
        raise RuntimeError(f"Need >=2 frames, found {len(frames)} in {frames_dir}")

    track = []
    cumulative = 0.0
    cumulative_tilt = 0.0

    prev_t, prev_path = frames[0]
    prev_gray = load_gray(prev_path)

    # anchor entry at t0 (no motion yet)
    track.append({
        "t": round(prev_t, 3),
        "pan_deg_per_s": 0.0,
        "tilt_deg_per_s": 0.0,
        "cumulative_pan_deg": 0.0,
        "cumulative_tilt_deg": 0.0,
        "coherence": 1.0,
        "dominant_dir": "ahead",
    })

    for t, path in frames[1:]:
        gray = load_gray(path)
        if gray is None or prev_gray is None or gray.shape != prev_gray.shape:
            prev_gray, prev_t = gray, t
            continue
        dt = t - prev_t
        if dt <= 0:
            prev_gray, prev_t = gray, t
            continue

        m = pair_motion(prev_gray, gray, dt)

        # Integrate using the per-step degrees (already accounts for dt).
        # Down-weight low-coherence steps so jitter doesn't accumulate drift,
        # but keep a fraction so genuine slow pans still register.
        w = max(m["coherence"], 0.0)
        cumulative += m["pan_deg_step"] * (0.3 + 0.7 * min(w / 0.5, 1.0))
        cumulative_tilt += m["tilt_deg_step"] * (0.3 + 0.7 * min(w / 0.5, 1.0))

        track.append({
            "t": round(t, 3),
            "pan_deg_per_s": round(m["pan_deg_per_s"], 3),
            "tilt_deg_per_s": round(m["tilt_deg_per_s"], 3),
            "cumulative_pan_deg": round(cumulative, 3),
            "cumulative_tilt_deg": round(cumulative_tilt, 3),
            "coherence": round(m["coherence"], 3),
            "dominant_dir": dominant_dir(m["pan_deg_per_s"], m["coherence"]),
        })

        prev_gray, prev_t = gray, t

    return track


# --------------------------------------------------------------------------
# Query helpers (the public API)
# --------------------------------------------------------------------------
def _validate_track(track):
    if not isinstance(track, list) or len(track) < 2:
        raise ValueError("egomotion track must contain at least two samples")
    previous_t = None
    for index, sample in enumerate(track):
        if not isinstance(sample, dict):
            raise ValueError(f"egomotion sample {index} is not an object")
        for key in ("t", "cumulative_pan_deg", "coherence"):
            value = sample.get(key)
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"egomotion sample {index} has invalid {key}")
        if previous_t is not None and sample["t"] <= previous_t:
            raise ValueError("egomotion timestamps must be strictly increasing")
        previous_t = sample["t"]
    return track


def load_track(artifact_path):
    """Load one explicitly selected clip artifact; there is no global fallback."""
    if artifact_path is None:
        raise ValueError("artifact_path is required")
    with open(os.fspath(artifact_path)) as artifact_file:
        artifact = json.load(artifact_file)
    if not isinstance(artifact, dict):
        raise ValueError("egomotion artifact must be a JSON object")
    return _validate_track(artifact.get("track"))


def _cum_at(track, t):
    """Nearest-sample cumulative_pan_deg at time t (with linear interp)."""
    if not track:
        return None
    # exact / nearest with interpolation
    below = None
    above = None
    for e in track:
        if e["t"] <= t:
            below = e
        if e["t"] >= t and above is None:
            above = e
    if below is None:
        return track[0]["cumulative_pan_deg"]
    if above is None:
        return track[-1]["cumulative_pan_deg"]
    if below is above or above["t"] == below["t"]:
        return below["cumulative_pan_deg"]
    frac = (t - below["t"]) / (above["t"] - below["t"])
    return below["cumulative_pan_deg"] + frac * (
        above["cumulative_pan_deg"] - below["cumulative_pan_deg"]
    )


def _avg_coherence(track, t0, t1):
    lo, hi = min(t0, t1), max(t0, t1)
    vals = [e["coherence"] for e in track if lo <= e["t"] <= hi]
    return sum(vals) / len(vals) if vals else 0.0


def answer_relative_direction(anchor_t, target_t, track=None, artifact_path=None):
    """
    Where is the target view relative to the anchor view, from cumulative pan?

    Returns dict:
      {direction: 'left'|'right'|'ahead', delta_deg, confidence (0..1), note}
    """
    if track is None:
        track = load_track(artifact_path)
    else:
        track = _validate_track(track)
    a = _cum_at(track, anchor_t)
    b = _cum_at(track, target_t)
    if a is None or b is None:
        return {"direction": "unknown", "delta_deg": None,
                "confidence": 0.0, "note": "no track data"}

    delta = b - a  # +deg => target is to the RIGHT of anchor

    if delta > DIR_THRESH_DEG:
        direction = "right"
    elif delta < -DIR_THRESH_DEG:
        direction = "left"
    else:
        direction = "ahead"

    # Confidence: how decisively |delta| clears the threshold, scaled by the
    # average flow coherence over the interval (noisy intervals => less trust).
    coh = _avg_coherence(track, anchor_t, target_t)
    margin = (abs(delta) - DIR_THRESH_DEG) / max(DIR_THRESH_DEG, 1.0)
    if direction == "ahead":
        # confident-ahead when delta is well inside the band AND flow is clean
        conf = max(0.0, 1.0 - abs(delta) / DIR_THRESH_DEG) * (0.4 + 0.6 * coh)
    else:
        conf = (1.0 / (1.0 + math.exp(-2.5 * margin))) * (0.4 + 0.6 * coh)
    conf = round(min(max(conf, 0.0), 1.0), 3)

    return {
        "direction": direction,
        "delta_deg": round(delta, 2),
        "confidence": conf,
        "anchor_cum_deg": round(a, 2),
        "target_cum_deg": round(b, 2),
        "avg_coherence": round(coh, 3),
        "note": ("positive delta = target view is right of anchor "
                 "(camera panned right between the two times)"),
    }


def build_artifact(frames_dir):
    """Build a clip-neutral egomotion artifact from an explicit frame directory."""
    frames_dir = os.path.abspath(os.fspath(frames_dir))
    track = build_track(frames_dir)
    print(f"[egomotion] computed {len(track)} track samples "
          f"({track[0]['t']}s .. {track[-1]['t']}s)")

    # Summary stats for the notes
    cums = [e["cumulative_pan_deg"] for e in track]
    cohs = [e["coherence"] for e in track]
    pans = [e["pan_deg_per_s"] for e in track]

    notes = (
        "Visual egomotion from dense Farneback optical flow on consecutive "
        "0.5s-spaced frames. SIGN: pan_deg_per_s>0 = camera panned RIGHT "
        "(world flow slides left). cumulative_pan_deg = running integral of "
        f"pan, coherence-weighted. H_FOV={H_FOV_DEG}deg sets px->deg scale "
        "(magnitude only; direction is scale-free). Walking clip: forward "
        "locomotion + footstep bounce add radial/vertical jitter, mitigated "
        "by MEDIAN flow + coherence weighting. Treat the SIGN of cumulative "
        "deltas as the reliable signal; absolute degrees are approximate."
    )

    return {
        "schema": "egomotion_visual.v1",
        "frame_clock": "video_seconds",
        "source_frames": os.path.relpath(frames_dir, ROOT),
        "method": "cv2.calcOpticalFlowFarneback dense flow, median translation, coherence-weighted integration",
        "sign_convention": {
            "pan_deg_per_s_positive": "camera panned RIGHT",
            "pan_deg_per_s_negative": "camera panned LEFT",
            "cumulative_pan_deg": "running integral; larger = pointing further right",
            "tilt_deg_per_s_positive": "camera tilted UP",
        },
        "params": {
            "h_fov_deg": H_FOV_DEG,
            "v_fov_deg": V_FOV_DEG,
            "proc_width": PROC_W,
            "crop_frac": CROP,
            "coherence_min": COHERENCE_MIN,
            "dir_thresh_deg": DIR_THRESH_DEG,
        },
        "summary": {
            "n_samples": len(track),
            "t_start": track[0]["t"],
            "t_end": track[-1]["t"],
            "cumulative_pan_deg_final": round(cums[-1], 2),
            "cumulative_pan_deg_min": round(min(cums), 2),
            "cumulative_pan_deg_max": round(max(cums), 2),
            "mean_coherence": round(sum(cohs) / len(cohs), 3),
            "mean_abs_pan_deg_per_s": round(sum(abs(p) for p in pans) / len(pans), 3),
        },
        "track": track,
        "notes": notes,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames-dir", required=True,
                        help="frame directory for this clip (frame_*_<seconds>s.jpg)")
    parser.add_argument("--out", required=True,
                        help="egomotion_visual.json path beside this clip's memory")
    args = parser.parse_args(argv)

    print(f"[egomotion] frames dir: {args.frames_dir}")
    artifact = build_artifact(args.frames_dir)
    out_path = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as artifact_file:
        json.dump(artifact, artifact_file, indent=2)
    # Round-trip validation is clip-neutral: it checks the actual output rather
    # than asserting known WALK events or directions.
    load_track(out_path)
    print(f"[egomotion] wrote and validated {out_path}")
    return artifact


if __name__ == "__main__":
    main()
