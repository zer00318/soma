#!/bin/bash
# Install (or reinstall) the TRACE cockpit as a launchd LaunchAgent so it self-heals on
# any death and survives reboot/sleep. Idempotent: safe to re-run. Reversible:
#   launchctl bootout gui/$(id -u)/com.trace.cockpit ; rm ~/Library/LaunchAgents/com.trace.cockpit.plist
set -u
REPO="/Users/zer00/Documents/VLM"
LABEL="com.trace.cockpit"
SRC="$REPO/ops/com.trace.cockpit.plist"
DST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

echo "== installing $LABEL =="
mkdir -p "$HOME/Library/LaunchAgents"

# Free the port: stop any manually-launched cockpit so the agent can bind cleanly.
pkill -f "scripts/ops_cockpit.py" 2>/dev/null && echo "stopped a manually-running cockpit" || true
sleep 1

cp "$SRC" "$DST"
echo "copied plist -> $DST"

# Tear down a prior copy of the agent, then load fresh (works on modern + old launchd).
launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || launchctl unload "$DST" 2>/dev/null || true
if launchctl bootstrap "$DOMAIN" "$DST" 2>/dev/null; then
  echo "bootstrapped via launchctl bootstrap"
else
  launchctl load -w "$DST" && echo "loaded via launchctl load -w"
fi
launchctl enable "$DOMAIN/$LABEL" 2>/dev/null || true

sleep 2
echo "== status =="
launchctl print "$DOMAIN/$LABEL" 2>/dev/null | grep -iE "state =|pid =|program =" || launchctl list | grep "$LABEL" || true
echo "done. Logs: /tmp/trace_cockpit.log"
