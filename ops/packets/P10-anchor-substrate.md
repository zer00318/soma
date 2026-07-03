# P10 — Coordinate anchor substrate
wave: W1 · tag: judgment · executor: Fable or Opus effort=high · depends: P00 (finalize per its verdict)

## Context (self-contained)
Spec §2: everything perceived gets pinned to a place the moment it's perceived. Identity
model is hybrid — coordinates pin the world (this packet), fingerprints pin the things
(P11), fused in the live binder (P12). Today's anchor is the per-session on-device
track_id (keyed label+tid, see `src/trace_memory/store/individuate.py`); it dies when the
session ends and knows nothing about space.

## Laws that bind you
L1: pose/anchor metadata and text may leave the phone; frames may not. L2, L4.

## Do (P00 GREEN branch — ARKit owns the camera)
1. Phone: every emitted observation carries `anchor_id` = a stable ARAnchor-derived id +
   `pose` (world transform) + `tracking_state`. Room identity = ARWorldMap re-localization;
   when tracking is `.limited`, degrade honestly to track-anchor (graded fidelity — the
   observation says which grade it carries).
2. Contract: fill the `anchor_id` field from P02's schema; hub stores pose metadata on the row.
3. Store: anchors table (anchor_id, room/session, first/last seen, grade); nothing about
   old rows breaks (they simply have no anchor).

## Do (P00 RED branch)
Coordinate-light place-graph (spec §2 coordinates ruling): track-anchor stays primary;
room identity from place recognition (place+scene+GPS); optional on-device monocular
depth (small ANE model) for per-frame camera-relative 3D. Same contract fields, lower
grade label. NOT open-source SLAM, NOT proprietary VIO — that decision is closed.

## Forbidden
No counting/answering logic here (owners stay in binder/agent). No Mac-side processing of
pixels (L1 — the old DepthPro-on-Mac path is dead).

## Done when
A 2-minute real capture produces observations where ≥80% of confirmed-track rows carry an
anchor_id with grade labels; a re-entered room re-localizes (GREEN branch) or degrades
honestly (RED); seam tests through real Hub.ingest; pytest + battery hold. INDEX flipped.
