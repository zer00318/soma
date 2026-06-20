#!/bin/bash
# Start the cockpit keepalive supervisor, detached and idempotent. Safe to re-run: if a
# keepalive is already running it just reports and exits. Detaches via a subshell + nohup
# so the supervisor outlives the session that launched it (reparents to launchd/pid 1).
cd /Users/zer00/Documents/VLM || exit 1
if pgrep -f "cockpit_keepalive.sh" >/dev/null 2>&1; then
  echo "keepalive already running (pids: $(pgrep -f cockpit_keepalive.sh | tr '\n' ' '))"
  exit 0
fi
( nohup ./scripts/cockpit_keepalive.sh >/dev/null 2>&1 & )
sleep 1
if pgrep -f "cockpit_keepalive.sh" >/dev/null 2>&1; then
  echo "keepalive started (pids: $(pgrep -f cockpit_keepalive.sh | tr '\n' ' '))"
else
  echo "FAILED to start keepalive — check /tmp/trace_cockpit.log"
  exit 1
fi
