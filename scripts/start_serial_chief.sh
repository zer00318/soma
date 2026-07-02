#!/bin/zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$ROOT/ops/serial_runtime/daemon.log"
PID_FILE="$ROOT/ops/serial_runtime/daemon.pid"
TASK="${1:-09}"

mkdir -p "$ROOT/ops/serial_runtime"
touch "$LOG"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE" 2>/dev/null)" >/dev/null 2>&1; then
  echo "serial chief task already running"
  exit 0
fi

nohup caffeinate -is /bin/zsh -lc "exec \"$ROOT/scripts/run_phase1_serial.sh\" \"$TASK\"" >> "$LOG" 2>&1 &
JOB_PID=$!
echo "$JOB_PID" > "$PID_FILE"
printf '[%s] armed task=%s pid=%s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$TASK" "$JOB_PID" >> "$LOG"

echo "serial chief task armed: $TASK"
echo "log: $LOG"
