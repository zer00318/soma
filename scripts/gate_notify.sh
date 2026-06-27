#!/usr/bin/env bash
# gate_notify.sh — run a validation command; on finish, POP A MAC NOTIFICATION (so the
# founder is "called") + write a status flag the cockpit/Chief can read. Wrap any gate
# or eval in it.
#   scripts/gate_notify.sh "T1 eval unify" .venv/bin/python -m pytest tests/unit/test_agent.py -q
set -uo pipefail
LABEL="${1:?usage: gate_notify.sh LABEL CMD...}"; shift
STATUS_FILE="ops/cockpit/gate_status.json"
mkdir -p ops/cockpit
"$@"; RC=$?
if [ "$RC" -eq 0 ]; then STATE="PASS"; SOUND="Glass"; else STATE="FAIL"; SOUND="Basso"; fi
TS="$(date '+%Y-%m-%d %H:%M:%S')"
printf '{"label":"%s","state":"%s","rc":%d,"when":"%s"}\n' "$LABEL" "$STATE" "$RC" "$TS" > "$STATUS_FILE"
osascript -e "display notification \"$LABEL — $STATE\" with title \"TRACE gate\" sound name \"$SOUND\"" 2>/dev/null
echo "[gate] $LABEL -> $STATE (rc=$RC) @ $TS"
exit "$RC"
