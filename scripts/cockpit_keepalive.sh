#!/bin/bash
# Userland supervisor for the TRACE cockpit — the founder's window stays up.
#
# WHY NOT launchd? macOS TCC blocks a launchd LaunchAgent from reading ~/Documents
# ("Operation not permitted"), and the repo lives in /Users/zer00/Documents/VLM. This
# keepalive instead runs in the founder's already-authorized session context, so it needs
# NO Full Disk Access grant. It restarts the server on ANY crash within ~2s. Started
# detached (see scripts/cockpit_supervise.sh), it survives the Chief's session ending and
# sleep/wake. The ONLY gap is a full reboot — for that, grant Full Disk Access to
# /usr/bin/python3 and load ops/com.trace.cockpit.plist (documented in the cockpit asks box).
cd /Users/zer00/Documents/VLM || exit 1
echo "$(date '+%F %T')  keepalive START (pid $$)" >> /tmp/trace_cockpit.log
while true; do
  /usr/bin/python3 scripts/ops_cockpit.py >> /tmp/trace_cockpit.log 2>&1
  rc=$?
  echo "$(date '+%F %T')  cockpit exited rc=$rc — restarting in 2s" >> /tmp/trace_cockpit.log
  sleep 2
done
