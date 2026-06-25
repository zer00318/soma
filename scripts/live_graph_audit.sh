#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${TRACE_DATA_DIR:-$ROOT_DIR/data}"
HUB_HOST="${TRACE_HUB_HOST:-127.0.0.1}"
HUB_PORT="${TRACE_HUB_PORT:-8765}"
HUB_TOKEN="${TRACE_HUB_TOKEN:-dev-token}"
AUDIT_INTERVAL="${TRACE_AUDIT_INTERVAL:-12}"
AUDIT_ITERATIONS="${TRACE_AUDIT_ITERATIONS:-30}"
RELAUNCH_NATIVE="${TRACE_RELAUNCH_NATIVE:-1}"
APP_PATH="${TRACE_NATIVE_APP_PATH:-$HOME/Library/Developer/Xcode/DerivedData/FastVLM-hgpowjcsgrivjgftwcetohnqmdug/Build/Products/Debug/FastVLM App.app}"

cleanup() {
  if [[ -n "${HUB_PID:-}" ]]; then
    kill "$HUB_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

cd "$ROOT_DIR"
mkdir -p "$DATA_DIR"

if curl -fsS -H "X-TRACE-Token: $HUB_TOKEN" "http://$HUB_HOST:$HUB_PORT/health" >/dev/null 2>&1; then
  echo "TRACE hub already running on http://$HUB_HOST:$HUB_PORT"
else
  echo "Starting TRACE hub on http://$HUB_HOST:$HUB_PORT"
  python3 -m trace_hub serve --host "$HUB_HOST" --port "$HUB_PORT" --data-dir "$DATA_DIR" --token "$HUB_TOKEN" &
  HUB_PID="$!"
  sleep 1
fi

if [[ -d "$APP_PATH" ]]; then
  echo "Opening native TRACE app: $APP_PATH"
  if [[ "$RELAUNCH_NATIVE" == "1" ]]; then
    osascript -e 'tell application "FastVLM App" to quit' >/dev/null 2>&1 || true
    sleep 1
  fi
  open "$APP_PATH"
else
  echo "Native app build not found at: $APP_PATH"
  echo "Run: xcodebuild -project trace-native-fastvlm/FastVLM.xcodeproj -scheme 'FastVLM App' -configuration Debug -destination 'platform=macOS' CODE_SIGNING_ALLOWED=NO build"
fi

echo "Auditing graph every ${AUDIT_INTERVAL}s for ${AUDIT_ITERATIONS} iterations."
python3 scripts/audit_live_graph.py \
  --base-url "http://$HUB_HOST:$HUB_PORT" \
  --token "$HUB_TOKEN" \
  --interval "$AUDIT_INTERVAL" \
  --iterations "$AUDIT_ITERATIONS"
