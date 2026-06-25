# CODEX BRIEF 9 dense segmentation RESULT

Status: code complete, tests/build verified, device install/run verification
BLOCKED.

LOUD COMMIT WARNING: work is uncommitted because `.git` is read-only in this
sandbox. `git commit` failed with:

`fatal: Unable to create '/Users/zer00/Documents/VLM/.git/index.lock': Operation not permitted`

## Model choice

Chosen path: P0 fallback, dense pyramid crops.

Why: no local SAM/MobileSAM/FastSAM CoreML package or checkpoint exists in the
repo. The web search path did not yield a usable published CoreML artifact in
this session, and shell network/download is restricted, so self-conversion
could not land end-to-end within budget. Implemented the brief fallback:
Vision objectness saliency plus 5x5 and 7x7 grid crops at two scales, IoU
dedupe, area filter 1.5%-70%, cap 40 proposals/frame.

## Implemented

- Spatial scanner now uses dense proposals instead of the 3-region saliency
  ceiling.
- MobileCLIP naming is batched per frame with one `VNImageRequestHandler`
  over multiple ROI requests.
- Per-frame status includes scan ms, namer p50/p95, proposals/frame, and
  words/min.
- Proposal cap starts at 40, halves on thermal serious/critical, and reduces
  if scan p95 exceeds 600 ms. Cap changes are logged to spatial diag.
- Accepted proposals project footprint polygons through the existing raycast
  path, simplify to <=24 points, persist `footprint: [[x,z]...]` and
  `heightM`.
- Spatial posts include `footprint` and `heightM`.
- Hub stores both fields inside `spatial_pose`; `/api/world` passes them
  through for DB and live objects.
- Replay helper `scripts/ingest_spatial_world.py` preserves the new shape
  fields.
- Vocab bundle: `Resources/vocab_embeddings.json` has 914 entries, so it is
  bundled. No app `.cache` directory is present.

## Verification

- Python suite: PASS, 124 tests.
- North-star: 9/10 = 0.90, threshold 0.8. This matches the pre-edit baseline;
  it is not the historical 1.00 noted in handover.
- Py compile: PASS with `PYTHONPYCACHEPREFIX=/tmp/trace_pycache`.
- iPhone Release build: PASS with the required recipe:
  `xcodebuild -project FastVLM.xcodeproj -scheme "FastVLM App" -configuration Release -sdk iphoneos26.5 ASSETCATALOG_EXEC=/tmp/actool_wrapper/actool build`
- Build product:
  `/Users/zer00/Library/Developer/Xcode/DerivedData/FastVLM-hgpowjcsgrivjgftwcetohnqmdug/Build/Products/Release-iphoneos/FastVLM App.app`

## Device verification

Not device-verified in this sandbox.

Two `xcrun devicectl list devices` attempts failed before device enumeration:

`ERROR: Timed out waiting for CoreDeviceService to fully initialize.`

No alternate local installer (`ios-deploy`, `ideviceinstaller`) is available.
Local hub/dashboard were also not running on ports 8765/8777, so no live
device artifact pull or `/api/world` measurement could be made for this build.

Measured proposal counts on device: unavailable due the CoreDevice blocker.
Expected scanner cap from code: up to 40 proposals/frame, halved to 20 under
thermal serious/critical or after p95 scan >600 ms.

## Risks

- Fallback crops are not true SAM-quality masks. Footprints are projected
  crop polygons/rectangles, so object shape is approximate until a real
  segment-everything CoreML model lands.
- Dense MobileCLIP over 40 ROIs may still exceed the 600 ms p95 target on
  device. The guard will cap and log, but founder acceptance still needs a
  real cluttered-room run.
- Multiple same-label instances are now allowed per frame if their ROIs do
  not overlap, which improves recall but may increase duplicate pressure
  until the existing spatial merge sees stable positions.
