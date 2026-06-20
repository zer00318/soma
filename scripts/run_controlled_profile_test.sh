#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HUB_HOST="${SOMA_HUB_HOST:-127.0.0.1}"
HUB_PORT="${SOMA_HUB_PORT:-8765}"
HUB_TOKEN="${SOMA_HUB_TOKEN:-dev-token}"
DATA_DIR="${SOMA_DATA_DIR:-$(mktemp -d /tmp/soma-controlled-profile.XXXXXX)}"
APP_PATH="${SOMA_NATIVE_APP_PATH:-$ROOT_DIR/build/SomaDerivedData/Build/Products/Debug/FastVLM App.app}"
PERSON_SECONDS="${SOMA_PERSON_SECONDS:-20}"
SIGN_SECONDS="${SOMA_SIGN_SECONDS:-20}"
OBJECT_SECONDS="${SOMA_OBJECT_SECONDS:-20}"
STALE_SECONDS="${SOMA_STALE_SECONDS:-12}"
WARMUP_SECONDS="${SOMA_WARMUP_SECONDS:-8}"
HUB_PID=""

cleanup() {
  if [[ -n "$HUB_PID" ]]; then
    kill "$HUB_PID" 2>/dev/null || true
  fi
  if [[ -z "${SOMA_DATA_DIR:-}" && "${SOMA_KEEP_TEST_DATA:-0}" != "1" ]]; then
    rm -rf "$DATA_DIR"
  fi
}
trap cleanup EXIT INT TERM

countdown() {
  local seconds="$1"
  while [[ "$seconds" -gt 0 ]]; do
    printf "\r%2ss remaining..." "$seconds"
    sleep 1
    seconds=$((seconds - 1))
  done
  printf "\rDone.             \n"
}

audit() {
  local label="${1:-}"
  if [[ -n "$label" ]]; then
    python3 "$ROOT_DIR/scripts/audit_live_graph.py" \
      --base-url "http://$HUB_HOST:$HUB_PORT" \
      --token "$HUB_TOKEN" \
      --label "$label" \
      --iterations 1
  else
    python3 "$ROOT_DIR/scripts/audit_live_graph.py" \
      --base-url "http://$HUB_HOST:$HUB_PORT" \
      --token "$HUB_TOKEN" \
      --iterations 1
  fi
}

reset_graph() {
  if [[ -z "$HUB_PID" && "${SOMA_RESET_EXISTING_HUB:-0}" != "1" ]]; then
    echo "Existing hub detected; not deleting its graph automatically."
    echo "For a clean controlled test, stop the existing hub or set SOMA_RESET_EXISTING_HUB=1."
    return
  fi

  curl -fsS \
    -H "Content-Type: application/json" \
    -H "X-SOMA-Token: $HUB_TOKEN" \
    -d '{"scope":"all"}' \
    "http://$HUB_HOST:$HUB_PORT/delete" >/dev/null
}

cd "$ROOT_DIR"
mkdir -p "$DATA_DIR"

if curl -fsS -H "X-SOMA-Token: $HUB_TOKEN" "http://$HUB_HOST:$HUB_PORT/health" >/dev/null 2>&1; then
  echo "Using existing SOMA hub at http://$HUB_HOST:$HUB_PORT"
else
  echo "Starting SOMA hub at http://$HUB_HOST:$HUB_PORT"
  python3 -m soma_hub serve --host "$HUB_HOST" --port "$HUB_PORT" --data-dir "$DATA_DIR" --token "$HUB_TOKEN" &
  HUB_PID="$!"
  sleep 1
fi

if [[ -d "$APP_PATH" ]]; then
  echo "Opening SOMA native app: $APP_PATH"
  open "$APP_PATH"
else
  echo "Native app not found at: $APP_PATH"
  echo "Build it first with:"
  echo "xcodebuild -project soma-native-fastvlm/FastVLM.xcodeproj -scheme 'FastVLM App' -configuration Debug -derivedDataPath build/SomaDerivedData CODE_SIGNING_ALLOWED=NO build"
  exit 2
fi

echo
echo "Controlled SOMA profile test"
echo "Data dir: $DATA_DIR"
echo "This test stores structured text/metadata only. It should not write raw audio, video, screenshots, or frames."
echo
read -r -p "When the app camera preview is live, press Enter to start..."
echo "Resetting the test graph after camera warmup..."
reset_graph
sleep 2
reset_graph
echo "Graph reset complete; stage boundaries are clean from here."

echo
echo "Stage 0: warmup. Keep the camera still; do not present a target yet."
countdown "$WARMUP_SECONDS"
audit || true

echo
echo "Stage 1: person profile. Keep one person steady in view. Try to include face, upper body, shirt, glasses/accessories if present."
countdown "$PERSON_SECONDS"
audit "visible person" || true

echo
echo "Stage 2: sign/OCR profile. Hold a readable sign, package, paper, or screen text steady and filling a useful part of the frame."
countdown "$SIGN_SECONDS"
audit "transit sign" || true

echo
echo "Stage 3: object profile. Hold one bag/bottle/object steady. Rotate slowly once if useful, then hold still."
countdown "$OBJECT_SECONDS"
audit || true

echo
echo "Stage 4: stale check. Point away from the person/object/sign at a blank wall or empty area."
countdown "$STALE_SECONDS"
audit || true

echo
echo "Controlled test complete."
echo "Tell Codex what looked wrong in each stage, especially:"
echo "- person profile slots: correct/missing/wrong"
echo "- sign OCR: correct text vs noisy variants"
echo "- object details: color/material/parts/wear"
echo "- stale behavior: old target still current, or correctly stale"
if [[ "${SOMA_KEEP_TEST_DATA:-0}" == "1" || -n "${SOMA_DATA_DIR:-}" ]]; then
  echo "Graph data kept at: $DATA_DIR"
fi
