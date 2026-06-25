#!/bin/zsh
# Cable-sync loop: every INTERVAL seconds pull the device perception spool
# over USB, replay it through the real ingest path (timestamps preserved),
# then truncate the device spool. Gives a live-ish /world on networks with
# client isolation where the phone cannot reach the hub directly.
# Usage: ./scripts/cable_sync_spool.sh [interval_seconds]   (default 120)
set -u
cd "$(dirname "$0")/.."
DEV="D3A506B2-8923-5313-B8A3-FF769ABBA228"
SRC="Library/Application Support/TRACE/perception_spool.ndjson"
INTERVAL="${1:-120}"
: > /tmp/empty_spool.ndjson
echo "[cable-sync] started $(date) interval=${INTERVAL}s"
while true; do
  TMP=/tmp/cable_sync_spool.ndjson
  rm -f "$TMP"
  if xcrun devicectl device copy from --device "$DEV" \
       --domain-type appDataContainer --domain-identifier de.zer00.trace \
       --source "$SRC" --destination "$TMP" >/dev/null 2>&1 \
     && [ -s "$TMP" ]; then
    N=$(grep -c . "$TMP" 2>/dev/null || echo 0)
    if [ "$N" -gt 0 ]; then
      REPLAY_OUT=$(python3 scripts/replay_perception_spool.py "$TMP" 2>&1)
      REPLAY_RC=$?
      echo "$REPLAY_OUT" >> /tmp/cable_sync.log
      # Only truncate the device spool when every packet truly ingested —
      # replay exits 0 even when individual packets fail.
      if [ $REPLAY_RC -eq 0 ] && ! echo "$REPLAY_OUT" | grep -q "ingest failed"; then
        xcrun devicectl device copy to --device "$DEV" \
          --domain-type appDataContainer --domain-identifier de.zer00.trace \
          --source /tmp/empty_spool.ndjson --destination "$SRC" >/dev/null 2>&1
        echo "[cable-sync] $(date +%H:%M:%S) replayed $N packets, spool truncated"
      else
        echo "[cable-sync] $(date +%H:%M:%S) replay FAILED for $N packets (spool kept)"
      fi
    fi
  fi
  sleep "$INTERVAL"
done
