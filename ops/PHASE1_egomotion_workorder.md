# Phase 1 Work Order — Egomotion Scaffold (make spatial answerable)
*Derived from the pose-design agent, 2026-06-17. Authorized by ROADMAP §5/§9/§11. Closes the (A) gap behind Q8/Q11.*

## The key finding
**The pose pipeline already exists end-to-end; the hero clip just predates it.** Not a
greenfield build — a re-capture + small wiring.
- `trace-native-fastvlm/FastVLM App/CaptureMode.swift` already writes
  `capture_<ts>/{video.mov, poses.ndjson, meta.json}`; each pose line =
  `{t, transform[16], intrinsics[9], tracking_state}` at ~10 Hz, sharing the video clock
  (`firstFrameTimestamp`, CaptureMode.swift:333-347).
- `scripts/walk_select_sharp_frames.py` already parses it (`parse_poses`, keeps
  `tracking=="normal"`; lines 29-87) — proven on 7,184 poses (`home_capture_20260613`).
- `scripts/walk_fuse_world.py --poses` backprojects objects to x/y/z;
  `scripts/ingest_walk_world.py` emits `spatial_words{x,y,z, pose_mode}`.
- `scripts/run_capture_pipeline.sh` already branches on whether a pose track exists.

## The real (A) gaps
- **A1** — the hero `Test.MOV` had NO pose track (the whole spatial story rests on a re-capture).
- **A2** — NO GPS/heading anywhere in the app → can do "30° to my right" (relative) but not
  "Max Planck is to my north/west" (absolute, Q8). ARKit gives a local frame, arbitrary heading.
- **A3** — the offline brain `ask_home.py` never loads a pose channel (assembler channel dict
  ~line 1097) AND hard-refuses all spatial (`SPATIAL_REFUSAL`, ~line 1432). Even a perfect track
  wouldn't reach the reasoner.
- **A4** — the AR `video.mov` is video-only (no audio track) → audio channel must be preserved
  on re-capture (regression guard for Q1/Q21).

## Capture decision: extend the existing ARKit app (not Record3D / Sensor Logger)
Record3D = good pose, NO GPS. Sensor Logger = GPS + raw IMU but NO ARKit world transform + bad
video sync. The existing app already emits exactly the schema the Python parses and shares one
clock. Two small additions:
1. `CLLocationManager` → `gps.ndjson` `{t, lat, lon, alt, course, trueHeading, h_acc}` on the
   shared `frame.timestamp` clock (~1 Hz sparsely anchors the dense ARKit track). **trueHeading is
   load-bearing for Q8.**
2. Audio: add an `AVAssetWriterInput(.audio)` to the writer, OR a sibling `audio.m4a` +
   `audio_offset` in `meta.json` (drops straight into `build_audio_events.py`).
3. (defer) raw `imu.ndjson` — only if a Phase-4 ablation shows ARKit's fused transform insufficient.

**Capture protocol:** re-walk the same Garching-Forschungszentrum scene; during the walk do a few
deliberate anchored fixations (stand facing the laptop ~2 s, pan to put the campus and the lift in
frame) so Q8/Q11 become gradeable. Then re-gold Q8/Q11 from recorded `trueHeading` (blind-battery
discipline preserved).

## Ingest: `scripts/build_egomotion_scaffold.py` (new) → `memory/egomotion.json`
A continuous, time-indexed channel kept losslessly from genesis, alongside the other channels.
- Reuse `parse_poses`/`_rotation_from_transform`/`_position_from_transform` from
  `walk_select_sharp_frames.py` (don't re-derive the column-major simd handling).
- Same frame clock as `kf_memory.json` → join each keyframe to nearest pose by bisect, no re-align.
- Fuse GPS `trueHeading` + ARKit yaw at the same t into one `yaw_alignment_deg` → bridges
  relative bearing (Q11) to absolute bearing (Q8).
- Carry `tracking_state` per sample through ingest (it is the refusal signal). Lossless = include
  the confidence.

## Brain: pose-gated spatial answer (ask_home.py)
1. Replace the blanket `SPATIAL_REFUSAL` (~line 1432) with `answer_spatial(question, mems,
   egomotion)`: anchor the reference moment ("when viewing the laptop") via keyword overlap →
   look up observer pose at that t → look up target object xyz → compute relative bearing
   (left/right/ahead) + absolute bearing (via `yaw_alignment_deg`) → return a CITED answer.
2. Add `"egomotion"` to the assembler channel dict (~line 1097) and an `=== EGOMOTION ===` block
   in `build_evidence_dossier` so general questions also see the track.

**Refusal rule (invariant: hallucination → 0) — refuse, don't guess, when ANY of:**
no scaffold / nearest pose within ±0.5s is `tracking != normal`; the anchor moment can't be
located; absolute bearing requested but GPS heading missing or `heading_acc > ~20°` (downgrade to
relative-only or refuse the compass claim); target object has no xyz. A spatial miss is then (A)
if pose was missing/degraded, (B) if pose was present but the chain failed.

## Ordered build list (frozen baseline → spatial answerable)
| # | Build | Closes | Auth Q | Effort |
|---|---|---|---|---|
| 1 | GPS + true-heading capture in CaptureMode.swift → `gps.ndjson` | A2 | Q8 | S |
| 2 | Preserve audio in AR capture (writer input or sibling m4a + offset) | A4 | Q1/Q21 | S |
| 3 | Re-capture Garching walk w/ anchored fixations; pull via devicectl runbook | A1 | Q8,Q11 | S (founder ~30m) |
| 4 | `build_egomotion_scaffold.py` → `memory/egomotion.json` (reuse pose parsers) | A3-ingest | Q8,Q11 | M |
| 5 | `answer_spatial()` replacing the blanket refusal (anchor→pose→bearing→cite) | A3-brain | Q8,Q11 | M |
| 6 | EGOMOTION dossier section + channel load | A3-brain | Q8,Q11 | S |
| 7 | Re-gold Q8/Q11 + add a pose-absent refusal regression case | invariant | Q8,Q11 | S |
| 8 | (defer) raw `imu.ndjson` — only if ablation demands | — | none | S |

Critical path: 1→2→3 (capture) then 4→5→6 (software) then 7 (score). Items 1-2 ∥ 4 (scaffold can
be developed against existing `home_capture_20260613` pose data before the new capture exists).

**Phase-1 done bar:** on the new capture Q8/Q11 are answered WITH citations to the anchor frame +
GPS heading; with `egomotion.json` removed, both fall back to honest refusal — proving the answer
was earned from real pose, not confabulated. Spatial-class hallucination stays 0 either way.

## Key files
- `trace-native-fastvlm/FastVLM App/CaptureMode.swift` (capture; add GPS+audio; pose at 89-101, 333-347)
- `scripts/walk_select_sharp_frames.py` (reuse pose parsers, 29-87)
- `scripts/ask_home.py` (brain: SPATIAL_REFUSAL ~1432; channel dict ~1097)
- `scripts/ingest_walk_world.py` (object xyz already emitted, 97-117)
- `evaluation/ras/walk_outside_20260614.gold.json` (re-gold Q8/Q11, lines 11 & 14)
