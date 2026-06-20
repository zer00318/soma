# CODEX BRIEF 11 offline world fusion RESULT

## Shipped

- Added `scripts/walk_fuse_world.py`.
  - With poses: nearest pose by frame timestamp, crop-center backprojection, floor-plane intersection from pose-height percentile, `depth=2.0m` fallback, same-label clustering within 1.0m, `depth_mode` honesty.
  - Without poses: emits ingestable positionless inventory objects with `x/y/z=null` and `depth_mode=none`.
  - `--self-test` covers clustered positioned crops and the null-position path.
- Added `scripts/ingest_walk_world.py`.
  - Posts one object per fused entry to `/capture/perception` with `source=offline_walk`.
  - Positioned objects include `metadata.spatial_words`; positionless objects omit it and carry `metadata.offline_inventory`.
- Hub/dashboard/world changes:
  - `soma_hub/graph.py` accepts `offline_walk` spatial words and persists positioned objects as `spatial_pose` source `offline_walk`.
  - `/api/world` marks offline objects as `source:"offline"` and includes positionless offline inventory as non-spatial objects.
  - `/world3d` skips null-position objects and renders offline-positioned objects with lower opacity.
- Fixed existing offline-pipeline manifest compatibility:
  - `walk_label_crops.py` accepts `crop`, `path`, or `crop_path`, batches CLIP image encoding, and prints progress.
  - `walk_build_inventory.py` accepts the same crop keys and normalizes scores.

## Real office no-pose run

Using existing `/tmp/walk_frames` and `/tmp/walk_crops` from `data/walks/walk_office_jun11.mov`:

- `/tmp/walk_labels.json`: 6,799 crop labels regenerated with the repo venv.
- `/tmp/walk_inventory.json`: 426 distinct labels, 6,796 accepted instances at score floor 0.22.
- `/tmp/walk_world.json`: 426 objects, 0 positioned, all `x/y/z=null`, all `depth_mode=none`.
- Ingest dry-run: 426 payloads, 0 payloads with `spatial_words`.
- Temp-DB ingest of the real no-pose world: 426 payloads -> 418 deduped entities, 0 `spatial_pose` rows, `/api/world.has_spatial=false`, 418 offline positionless objects.

Top no-pose labels are noisy: `keyboard`, `monitor`, `map`, `trash bag`, `bedpan`, `razorblade`, `iron`. This should feed recall only until a pose-bearing capture is available.

## Verification

- `python3 scripts/walk_fuse_world.py --self-test` PASS.
- `python3 scripts/walk_label_crops.py --self-test` PASS.
- `python3 scripts/walk_build_inventory.py --self-test` PASS.
- Python compile checks PASS with bytecode cache redirected to `/tmp`.
- Focused offline hub test PASS.
- Full suite: 125/125 PASS.
- North-star: unchanged pre-existing `9/10 = 0.90`, threshold 0.8 PASS. The same `Alice Tester.open_commitments_none` case is the only miss.
- `/world3d` script body static syntax check PASS.
- Direct `scripts.trace_demo_dashboard.api_world()` against the current DB returns without error: 79 world objects, 79 spatial, 0 offline.

## Not device-verified

LOUD WARNING: device verification and git commits were blocked by this sandbox.

- `xcrun devicectl list devices` failed: CoreDeviceService timed out during initialization.
- Process restart law could not be fully completed: `pkill` cannot list processes (`sysmond service not found`), and new localhost binds for hub/dashboard failed with `Operation not permitted`. Direct function verification and tests were used instead.
- In-app Browser was unavailable (`iab` missing), so `/world3d` could not be visually verified in Browser.
- `git add` failed: `.git/index.lock` cannot be created (`Operation not permitted`). Changes are uncommitted.

## Fusion accuracy caveats

- Pose-backed coordinates are inferred, not raycast-pinned. Plane mode assumes a floor band from camera pose heights; fallback mode uses a fixed 2.0m depth.
- No-pose office output intentionally has no renderable positions. It is inventory for recall only.
- The current CLIP crop labels are high-recall but noisy; real first verification should use a pose-bearing capture session and inspect the transparent offline objects in `/world3d` before trusting spatial recall.
