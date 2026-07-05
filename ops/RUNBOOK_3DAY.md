# RUNBOOK — the 3 real days (P50)

The done-bar (spec v3): 3 real days of founder usage + founder blind battery, ≥75% /
0-confident-wrong. This runbook is everything the 3 days need to survive contact with
reality. The 2026-07-04 readiness audit found four blockers; all four are addressed and
each has a line here.

## One-time setup (Mac, ~2 minutes)

1. **One command — hub keepalive + nightly consolidation** (blockers #4 and #2):
   ```
   nohup ./scripts/run_hub_keepalive.sh > /dev/null 2>&1 &
   ```
   Restarts the hub on crash, holds `caffeinate -si` so the Mac never sleeps while
   serving, and fires the nightly job itself in the 03:30 hour (cron on this Mac is
   TCC-flaky — verified 2026-07-04 — so the scheduler lives inside the keepalive).
   Nightly = dated store backup (keeps 7) → sleep consolidation → canonical battery
   (exit-1 on any confident-wrong) → one JSON line in `evaluation/nightly_log.jsonl`.
   Live feeds: `tail -f /tmp/trace_hub.log` and `/tmp/trace_nightly.log`.

2. **Phone hub address — use the mDNS name, not a LAN IP** (walk 1's connection failure
   was a hotspot-vs-wifi IP mismatch). In the app (brain icon):
   ```
   http://MacBook-Pro-3.local:8765
   ```
   Resolves on any network the Mac and phone share; off-network the phone spools.

## The carry protocol (phone)

- **Capture is foreground-only** (iOS suspends camera in background). "3 real days" =
  the app open during the stretches you'd want remembered — cooking, desk time, walks —
  not literally 72 h of filming. Lock the phone whenever you want; reopen resumes.
- **Away from the Mac all day is fine** (blocker #1 — fixed): packets spool on the phone
  (`perception_spool.ndjson`) and auto-drain the moment the brain is reachable again
  (8-second health loop, bounded chunks, capture timestamps preserved so temporal answers
  stay honest). Nothing is lost, nothing is manual.
- **Battery**: continuous ARKit+VLM is heavy; expect ~2–3 h per charge of active capture.
  Carry a cable; charging while capturing is fine.
- **Privacy**: the memory-pause toggle stops committing without killing the app. Frames
  never leave the phone either way (L1).
- **Ask anytime, on the phone** (P40): Ask Trace → badge + receipts. Each question is
  also a free product test.

## Every morning (30 seconds)

```
tail -1 evaluation/nightly_log.jsonl
```
- `"ok": true` → the night's consolidation + battery held (0 confident-wrong). Carry on.
- `"ok": false` → STOP and tell the chief; yesterday's backup is in
  `data/nightly_backups/` (restore = copy over `data/trace_store.sqlite3`).

## Known limits going in (honest expectations)

- Multi-day brain semantics were probed at 23k rows (3-day scale, 2026-07-04):
  worst ask latency ~37 s (gemma-bound, no blowup), "yesterday" browse + temporal-order
  fixed the same day. "Where is X" answers can be thin at scale (filed, quality-not-honesty).
- Counting under the probe's artificial duplication refused rather than lied — honest
  degradation; real distinct days don't duplicate rows.
- Day 3 ends with the founder blind battery (P51) on the real store.
