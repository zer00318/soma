#!/bin/zsh
# 3-day-carry blockers #4 + #2 in one process. The hub used to run via nohup in a
# terminal — one crash, one Mac sleep, one accidental ⌘W and capture silently stopped;
# and the sleep binder had never run automatically (cron on this Mac is TCC-flaky, so
# the scheduler lives HERE instead). This wrapper:
#   - restarts the hub whenever it exits (crash-safe),
#   - fires scripts/nightly_sleep.py once per night in the 03:30 hour
#     (backup → consolidate → canonical battery → one line in evaluation/nightly_log.jsonl),
#   - holds `caffeinate -si` so the Mac never sleeps while serving (also keeps 03:30 real),
#   - appends to /tmp/trace_hub.log and /tmp/trace_nightly.log.
# Start (leave the terminal open, or `nohup ./scripts/run_hub_keepalive.sh &`):
#   ./scripts/run_hub_keepalive.sh
# Stop: Ctrl-C (or kill the caffeinate process group).
cd "$(dirname "$0")/.." || exit 1
ROOT="$PWD"
echo "[keepalive] starting at $(date) — hub on :8765, log /tmp/trace_hub.log, nightly 03:30"
exec caffeinate -si zsh -c '
  cd "'"$ROOT"'" || exit 1
  last_nightly=""
  (
    while true; do
      hour=$(date +%H); today=$(date +%Y%m%d)
      if [[ "$hour" == "03" && "$last_nightly" != "$today" ]]; then
        last_nightly="$today"
        echo "[keepalive] nightly consolidation starting at $(date)" >> /tmp/trace_nightly.log
        .venv/bin/python scripts/nightly_sleep.py >> /tmp/trace_nightly.log 2>&1
      fi
      sleep 600
    done
  ) &
  while true; do
    .venv/bin/python -u scripts/trace_hub.py --store data/trace_store.sqlite3 --port 8765 >> /tmp/trace_hub.log 2>&1
    echo "[keepalive] hub exited rc=$? at $(date) — restarting in 3s" >> /tmp/trace_hub.log
    sleep 3
  done
'
