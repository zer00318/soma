#!/bin/zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME="$ROOT/ops/serial_runtime/world_overhaul"
LOG="$RUNTIME/daemon.log"
PID_FILE="$RUNTIME/daemon.pid"

mkdir -p "$RUNTIME"
touch "$LOG"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE" 2>/dev/null)" >/dev/null 2>&1; then
  echo "world overhaul supervisor already running"
  exit 0
fi

nohup /bin/zsh -lc "cd \"$ROOT\" && exec .venv/bin/python scripts/world_overhaul_supervisor.py" >> "$LOG" 2>&1 &
PID=$!
echo "$PID" > "$PID_FILE"
printf '[%s] started pid=%s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$PID" >> "$LOG"

echo "world overhaul supervisor armed"
echo "log: $LOG"
