# CODEX BRIEF 12 trusted naming RESULT

## Shipped

- Added `scripts/walk_name_objects.py`.
  - CLIP labels are treated as candidates.
  - Score-floor rejects are emitted as `trust: rejected`.
  - Surviving crops go through one serial Ollama `gemma3:12b` vision call.
  - Outputs carry `word`/`label`, `clip_word`, `clip_score`, `gemma_label`, `trust`, `name_source`, and `reject_reason`.
  - `--self-test` covers `clip_agreed`, `gemma_named`, and `clip_only` rejection without models.
- Threaded trust through offline inventory, fusion, ingest, `/api/world`, `/world3d`, and spatial recall.
  - `walk_fuse_world.py` only backprojects/clusters `trust: trusted` records.
  - `ingest_walk_world.py` never emits `metadata.spatial_words` for `trust: rejected`.
  - `trace_hub.graph` refuses rejected spatial words and filters legacy rejected poses from spatial recall.
  - `/api/world` carries `trust` and `name_source`.
  - `/world3d` hides rejected objects entirely and reports rejected-hidden count in the HUD.
- Appended the missing brief vocab words, deduped. The 10 target words are now present exactly once:
  `carpet`, `footrest`, `cabinet`, `server`, `corkboard`, `notebook`, `sign`, `container`, `hanger`, `cup`.

## Real office artifacts regenerated

Source: `data/walks/walk_office_jun11.mov`

- Frames: 280 in `/tmp/walk_frames`
- Crops: 6,799 in `/tmp/walk_crops`
- CLIP labels: 6,799 in `/tmp/walk_labels.json`
- Raw pre-gemma inventory at score floor 0.22: 425 distinct labels / 6,796 accepted instances
- Raw no-pose world: `/tmp/walk_world_raw.json`, 425 objects, 0 positioned

CLIP score-floor survivor counts:

| floor | survivors | distinct |
|---:|---:|---:|
| 0.22 | 6,796 | 425 |
| 0.25 | 6,688 | 418 |
| 0.28 | 5,202 | 361 |
| 0.30 | 2,920 | 249 |
| 0.32 | 980 | 103 |
| 0.35 | 104 | 8 |

Vocab recall signal after appending missing words:

- `carpet`: 183 CLIP instances
- `footrest`: 110
- `server`: 32
- `sign`: 9
- `cabinet`, `corkboard`, `notebook`, `container`, `hanger`, `cup`: 0 in this regenerated CLIP pass

Known suspect words are still present pre-gemma and therefore still untrusted: `razorblade` 152, `bedpan` 146, `iron` 136, `cloak` 82, `saucer` 81, `keg` 31, `sword` 20, `dagger` 1.

## Blocked acceptance items

LOUD WARNING: device/gemma/home verification could not be completed in this sandbox.

- Ollama/gemma is blocked by sandbox networking:
  - `ollama serve` -> `listen tcp 127.0.0.1:11434: bind: operation not permitted`
  - `ollama list` -> `dial tcp 127.0.0.1:11434: connect: operation not permitted`
- The expected real-data files are absent:
  - `/tmp/home_labels.json` absent
  - `/tmp/home_named.json` absent
  - `/tmp/reconcile_buckets.json` absent
  - no home raw capture file exists in the repo; only `evaluation/home_eval_20260612.md` and current DB/archive worlds are present
- Device verification is blocked:
  - `xcrun devicectl list devices` timed out waiting for CoreDeviceService initialization
  - No iOS source changed, so no app rebuild/install was needed for this code path, but `/world3d` could not be device-verified.
- Git commits are blocked:
  - `git add ...` failed with `.git/index.lock: Operation not permitted`
  - P0/P1 changes are therefore uncommitted despite the brief's commit-per-P law.

Because gemma could not run, the requested measured trusted home count, false-positive kill rate against the 274 CLIP-only suspects, and gemma-only recovered count as `gemma_named` are not honestly computable here. The code path is implemented and tested; the model/device acceptance still needs to be run in an environment that can start Ollama and access the phone/artifacts.

## Local verification

- `python3 scripts/walk_name_objects.py --self-test` PASS
- `python3 scripts/walk_build_inventory.py --self-test` PASS
- `python3 scripts/walk_fuse_world.py --self-test` PASS
- `PYTHONPYCACHEPREFIX=/tmp/trace_pycache python3 -m py_compile ...` PASS
- `node --check /tmp/world3d_body.js` PASS
- `python3 -m unittest discover -s tests -p "test_*.py"`: 128/128 PASS
- `python3 evaluation/run_north_star.py`: 9/10 = 0.90, threshold PASS

North-star note: 0.90 was already the baseline before this change in this session; the same `Alice Tester.open_commitments_none` case failed before and after.

Direct current-DB `/api/world` function check:

- 226 world objects
- 79 positioned/spatial objects
- `trusted_entities`: 226
- `rejected_entities`: 0

This is not a device verification of the new gemma trust pass; it only proves the updated API can read the current DB and emits trust fields with the legacy default.
