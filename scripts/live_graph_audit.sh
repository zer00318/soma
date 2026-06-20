#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${SOMA_DATA_DIR:-$ROOT_DIR/data}"
HUB_HOST="${SOMA_HUB_HOST:-127.0.0.1}"
HUB_PORT="${SOMA_HUB_PORT:-8765}"
HUB_TOKEN="${SOMA_HUB_TOKEN:-dev-token}"
AUDIT_INTERVAL="${SOMA_AUDIT_INTERVAL:-12}"
AUDIT_ITERATIONS="${SOMA_AUDIT_ITERATIONS:-30}"
RELAUNCH_NATIVE="${SOMA_RELAUNCH_NATIVE:-1}"
APP_PATH="${SOMA_NATIVE_APP_PATH:-$HOME/Library/Developer/Xcode/DerivedData/FastVLM-hgpowjcsgrivjgftwcetohnqmdug/Build/Products/Debug/FastVLM App.app}"

cleanup() {
  if [[ -n "${HUB_PID:-}" ]]; then
    kill "$HUB_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

cd "$ROOT_DIR"
mkdir -p "$DATA_DIR"

if curl -fsS -H "X-SOMA-Token: $HUB_TOKEN" "http://$HUB_HOST:$HUB_PORT/health" >/dev/null 2>&1; then
  echo "SOMA hub already running on http://$HUB_HOST:$HUB_PORT"
else
  echo "Starting SOMA hub on http://$HUB_HOST:$HUB_PORT"
  python3 -m soma_hub serve --host "$HUB_HOST" --port "$HUB_PORT" --data-dir "$DATA_DIR" --token "$HUB_TOKEN" &
  HUB_PID="$!"
  sleep 1
fi

if [[ -d "$APP_PATH" ]]; then
  echo "Opening native SOMA app: $APP_PATH"
  if [[ "$RELAUNCH_NATIVE" == "1" ]]; then
    osascript -e 'tell application "FastVLM App" to quit' >/dev/null 2>&1 || true
    sleep 1
  fi
  open "$APP_PATH"
else
  echo "Native app build not found at: $APP_PATH"
  echo "Run: xcodebuild -project soma-native-fastvlm/FastVLM.xcodeproj -scheme 'FastVLM App' -configuration Debug -destination 'platform=macOS' CODE_SIGNING_ALLOWED=NO build"
fi

echo "Auditing graph every ${AUDIT_INTERVAL}s for ${AUDIT_ITERATIONS} iterations."
python3 scripts/audit_live_graph.py \
  --base-url "http://$HUB_HOST:$HUB_PORT" \
  --token "$HUB_TOKEN" \
  --interval "$AUDIT_INTERVAL" \
  --iterations "$AUDIT_ITERATIONS"
