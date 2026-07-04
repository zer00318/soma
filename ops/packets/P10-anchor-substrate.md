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

## Landed (code) — 2026-07-04
Mac side (fully tested, 288 pytest green, battery 96.7/100/0/100 held):
- Contract (spec §5, `contract.py`): optional first-class `pose` / `grade` / `room` fields +
  a closed, ordered, monotone grade vocab (`world>session>track>none`); unknown grade → "none"
  (keeps the row, never a flattering fidelity). `normalize_grade` / `best_grade` are the owners.
- Store (`sqlite_store.py`): additive `anchors` table (idempotent — pre-P10 stores keep working,
  those rows just have no anchor). `record_anchor` upserts a sighting: keeps the BEST grade ever
  (a later .limited frame can't unpin a world lock), extends the seen-window, and counts a
  re-localization when the anchor turns up in a session it wasn't last seen in. `anchor_coverage`
  is the honest Done-when instrument (empty store → 0.0, never flatters). `AnchorRecord` model.
- Hub (`trace_hub.py`): both ingest shapes (contract + the legacy shape the phone actually
  streams) pin their row via one shared `_record_spatial`; `/status` reports anchor totals,
  re-localizations, row-coverage, grade histogram.

Phone side (`TraceARKitEngine.swift` + `ContentView.swift`, build-verified compiling; behavior
device-pending): `spatialStamp()` promotes ARKit state into the contract's spatial fields at the
single POST funnel (`postPerceptionPacketToHub`) so every helper's rows pin identically. grade =
world (relocalized vs saved map) / session (fresh normal tracking) / track (limited) / none.
Cross-session-stable `anchor_id` = `arkit:world:<persisted space id>` only at grade "world";
session-scoped otherwise. Space id persists with the saved world map, is dropped on
`forceFreshStart` (a new room is honestly a new anchor).

## Device-proof checklist (unlocks INDEX → MERGED; needs a walk on the new build)
1. Deploy the new build; restart the hub (`scripts/trace_hub.py`) so it has `record_anchor`.
2. Record a ≥2-min walk. `GET /status` → `anchors.row_coverage` ≥ 0.80, grades present.
3. Background the app (saves world map), re-enter a mapped room next session →
   `anchors.relocalized` > 0 (GREEN) or grades degrade honestly to `track`/`none` (RED).
4. Battery still 0-confident-wrong on the post-walk store.
