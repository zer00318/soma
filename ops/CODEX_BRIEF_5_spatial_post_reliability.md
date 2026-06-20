# CODEX BRIEF 5 — spatial post reliability (silent-loss bug)

Lead-verified failure, 2026-06-12: the 13:51–13:54 desk scan on build
`1b7e50d` produced 11 perfect objects on-device, but the hub received ZERO
posts and `/world` stayed empty. The phone was not on the Mac's new Wi-Fi
(10.168.8.x), and `SpatialWorld.postSpatialSnapshotIfNeeded()` (SpatialWorld.swift
~line 1159) is fire-and-forget: `URLSession.shared.dataTask(...).resume()`
with no completion handler. Failures are invisible AND `lastPostedSignature`
is updated before the request runs, so the same snapshot is never retried.
This is the same class as the perception-spool bug we already fixed for the
main capture path — spatial posts simply never got the fix.

## P0 — spool fallback for spatial snapshots

- In `postSpatialSnapshotIfNeeded()`, use a completion handler. On any
  error or non-2xx, append the exact payload JSON line to
  `Application Support/SOMA/perception_spool.ndjson` (same file/format the
  main capture path spools to — `scripts/replay_perception_spool.py` must
  be able to replay it unchanged; it already preserves timestamps).
- Update `lastPostedSignature` / `lastPostAt` only AFTER a 2xx OR a
  successful spool append, never before the outcome is known.
- Keep the existing 8s/signature rate limit semantics.

## P1 — visible connectivity in the status line

- Track counters: spatial posts ok / failed-spooled this session. Surface
  in the Spatial status line, e.g. `hub ok:12 spooled:3`. The founder must
  be able to SEE during a scan that the hub is unreachable — the Wi-Fi
  gotcha (Control Center toggle doesn't rejoin; needs Settings → WLAN)
  has now burned us twice.

## Acceptance (lead verifies on device artifacts)

1. Airplane-mode scan → spool file gains `mobileclip_spatial_word` lines;
   status line shows spooled count climbing.
2. Re-enable network → `python3 scripts/replay_perception_spool.py` lands
   the words in the hub; `/world` shows them with original capture time.
3. Normal-network scan → posts arrive live (hub access log), spool stays
   empty, status shows ok count.
4. Python suite + north-star stay green (no hub changes expected, but law
   is law).

Build/install recipe is in HANDOVER (the `-sdk iphoneos26.5` +
`ASSETCATALOG_EXEC=/tmp/actool_wrapper/actool` form; destination builds
fail). Stamp = current git SHA, verify in status line after install.

Do NOT start P4 (re-entry events, brief 4) until this lands — permanence
events are worthless if they can be silently dropped.
