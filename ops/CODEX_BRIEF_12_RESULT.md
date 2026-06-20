# CODEX BRIEF 12 RESULT

Canonical detailed result: `ops/CODEX_BRIEF_12_trusted_naming_RESULT.md`.

Summary:

- Implemented gemma-confirmed trusted naming in `scripts/walk_name_objects.py`.
- Threaded `trust`/`name_source` through inventory, fusion, ingest, `/api/world`, `/world3d`, and spatial recall.
- Rejected records are never fused into positioned 3D or cited by spatial recall.
- Added focused tests for trusted naming and rejected spatial recall.
- Added missing deduped vocab words so the brief's 10 real gemma-only words are present exactly once.

Real office artifacts regenerated:

- 280 frames
- 6,799 crops
- 6,799 CLIP labels
- 425 raw distinct labels / 6,796 accepted instances at score floor 0.22
- 425 raw no-pose world objects, 0 positioned

Blocked:

- Ollama/gemma could not run: local bind/connect to `127.0.0.1:11434` is sandbox-blocked.
- `/tmp/home_labels.json`, `/tmp/home_named.json`, and `/tmp/reconcile_buckets.json` are absent.
- Device verification could not run: `devicectl` timed out waiting for CoreDeviceService.
- Git commits could not be created: `.git/index.lock` is not writable.

Verification:

- `python3 scripts/walk_name_objects.py --self-test` PASS
- `python3 scripts/walk_build_inventory.py --self-test` PASS
- `python3 scripts/walk_fuse_world.py --self-test` PASS
- `node --check /tmp/world3d_body.js` PASS
- `python3 -m unittest discover -s tests -p "test_*.py"`: 128/128 PASS
- `python3 evaluation/run_north_star.py`: 9/10 = 0.90, threshold PASS; same baseline miss as before this change

LOUD WARNING: the measured trusted home count, false-positive kill rate, and gemma-named recall recovery were not computable in this sandbox because gemma, device access, and the home label artifacts were unavailable.
