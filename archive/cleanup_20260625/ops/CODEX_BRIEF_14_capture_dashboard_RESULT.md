# CODEX BRIEF 14 capture dashboard RESULT

## Shipped

- Added `scripts/capture_index.py`.
  - Stdlib-only CLI: `--walks-dir`, `--out-json`, `--out-html`, `--self-test`.
  - Scans capture directories with `meta.json` or `video.mov`.
  - Reads capture health from `meta.json`: battery, thermal samples, duration,
    pose count, build sha, and device.
  - Stats `video.mov` directly for size.
  - Reads optional finalized pipeline outputs:
    `work/run_inventory.json`, `work/run_named.json`, `work/run_world.json`.
  - Writes a JSON index and a dark, self-contained HTML dashboard.
  - Refuses output paths under the walks directory, preserving the read-only
    rule for `data/walks`.
  - Tolerates missing or half-written pipeline JSON by leaving counts absent
    and surfacing artifact read errors in JSON/HTML.

## Device-Verified Result

Source capture: `data/walks/home_capture_20260613`, pulled from iPhone
`iPhone18,3` on iOS `27.0`, app build `15caaf9`.

Command:

```bash
python3 scripts/capture_index.py \
  --walks-dir data/walks \
  --out-json /tmp/capture_index.json \
  --out-html /tmp/capture_index.html
```

Indexed result:

- Capture count: 1
- Capture card: `home_capture_20260613`
- Duration: `720.259` seconds
- Battery: `80% -> 80%`, drain `0.0` percentage points
- Max thermal state: `nominal`
- Pose count: `7197`
- `video.mov` stat size: `1081328394` bytes
- Processed badge shown after final pipeline artifacts appeared
- `run_inventory.json`: 257 distinct inventory entries
- `run_named.json`: 0 trusted records, 6901 rejected records
- `run_world.json`: 257 objects, 0 positioned objects with finite x/y/z
- Outputs written outside the capture tree:
  `/tmp/capture_index.json`, `/tmp/capture_index.html`

Read-only guard check:

```bash
python3 scripts/capture_index.py \
  --walks-dir data/walks \
  --out-json data/walks/nope.json \
  --out-html /tmp/nope.html
```

Result: refused with `error: refusing to write under walks dir:
data/walks/nope.json`.

## Verification

- `PYTHONPYCACHEPREFIX=/tmp/trace_pycache python3 -m py_compile scripts/capture_index.py` PASS
- `python3 scripts/capture_index.py --self-test` PASS
- Real capture dashboard generation to `/tmp/capture_index.{json,html}` PASS
- `python3 -m unittest discover -s tests -p "test_*.py"`: 128/128 PASS
- `python3 evaluation/run_north_star.py`: 9/10 = 0.90, threshold PASS

North-star note: the same 0.90 result was present before this change in this
session. The failing case is `Alice Tester.open_commitments_none`. This brief
does not change `trace_hub`, and the brief says to stop after P0.

## Scope Notes

- No `trace_hub` files changed.
- No pipeline scripts changed.
- No writes were made under `data/walks` by the dashboard.
- No network, model, `cv2`, or `torch` use was added.
- No iOS build/install was run; this P0 is a read-only Mac-side dashboard, and
  verification used the preserved device capture artifacts.

## LOUD GIT NOTE

Commit was requested, but git is not writable in this sandbox. Attempted:

```bash
git add scripts/capture_index.py ops/CODEX_BRIEF_14_capture_dashboard_RESULT.md &&
git commit -m "Add capture session dashboard" \
  -m "Index device capture directories read-only and emit JSON plus HTML health summaries."
```

Result:

```text
fatal: Unable to create '/Users/zer00/Documents/VLM/.git/index.lock': Operation not permitted
```
