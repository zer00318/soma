#!/usr/bin/env bash
# Start the local TRACE stack used by the iPhone spatial word map.
# Idempotent: existing hub/dashboard/enricher processes are reused.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -n "${PYTHON:-}" ]]; then
  PY="$PYTHON"
elif [[ "$(uname -s)" == "Darwin" ]] && command -v xcrun >/dev/null 2>&1; then
  PY="$(xcrun --find python3)"
else
  PY="$ROOT/.venv/bin/python"
fi
if [[ ! -x "$PY" ]]; then
  PY="python3"
fi

start_if_missing() {
  local name="$1"
  local pattern="$2"
  local log="$3"
  shift 3
  if pgrep -f "$pattern" >/dev/null 2>&1; then
    local pid
    pid="$(pgrep -f "$pattern" | head -n 1)"
    echo "$name already running (pid $pid)"
    return
  fi
  mkdir -p "$(dirname "$log")"
  if [[ "$(uname -s)" == "Darwin" ]] && command -v launchctl >/dev/null 2>&1; then
    local label safe_name cmd arg
    safe_name="$(printf "%s" "$name" | tr -cs '[:alnum:]' '-' | tr '[:upper:]' '[:lower:]' | sed 's/^-//;s/-$//')"
    label="com.soma.trace.${safe_name}"
    launchctl remove "$label" >/dev/null 2>&1 || true
  fi
  PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" nohup "$@" >> "$log" 2>&1 &
  echo "$name started (pid $!, log $log)"
}

start_if_missing \
  "hub :8765" \
  "soma_hub.api.*--port 8765" \
  "/tmp/soma_hub.log" \
  "$PY" -m soma_hub.api --host 0.0.0.0 --port 8765

start_if_missing \
  "dashboard :8777" \
  "scripts/trace_demo_dashboard.py" \
  "/tmp/trace_demo_dashboard.log" \
  "$PY" "$ROOT/scripts/trace_demo_dashboard.py"

start_if_missing \
  "enricher" \
  "soma_perception.enricher.*data/soma_hub.sqlite3" \
  "/tmp/soma_enricher.log" \
  "$PY" -m soma_perception.enricher --db data/soma_hub.sqlite3

sleep 2
hub_code="$(curl -s -H "X-SOMA-Token: dev-token" -o /dev/null -w "%{http_code}" "http://127.0.0.1:8765/health" || true)"
echo "http://127.0.0.1:8765/health -> $hub_code"
for url in "http://127.0.0.1:8777/" "http://127.0.0.1:8777/world"; do
  code="$(curl -s -o /dev/null -w "%{http_code}" "$url" || true)"
  echo "$url -> $code"
done
