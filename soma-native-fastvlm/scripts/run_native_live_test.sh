#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-full}"
WORKSPACE="${SOMA_WORKSPACE:-/Users/zer00/Documents/VLM}"
APP_PATH="${SOMA_NATIVE_APP:-$HOME/Library/Developer/Xcode/DerivedData/FastVLM-hgpowjcsgrivjgftwcetohnqmdug/Build/Products/Debug/FastVLM App.app}"
LOG_FILE="${SOMA_NATIVE_LOG:-$HOME/Library/Application Support/SOMA/soma_native_text.ndjson}"
NODE_BIN="${NODE_BIN:-$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORT_FILE="${SOMA_NATIVE_REPORT:-$WORKSPACE/soma-native-fastvlm/SOMA_NATIVE_LIVE_REPORT.md}"

usage() {
  cat <<'USAGE'
Usage:
  run_native_live_test.sh readiness
  run_native_live_test.sh detector
  run_native_live_test.sh ocr
  run_native_live_test.sh speech
  run_native_live_test.sh full

Modes:
  readiness  Launch app and verify local engines, GPS, context, memory hygiene, no raw media.
  detector   Ask for a visible person/object and require detector-backed OBJECT memory.
  ocr        Ask for a visible sign/board and require OCR sign/board memory.
  speech     Ask for spoken words and require speech EVENT memory.
  full       Runs readiness, then prompts for detector, OCR, and speech evidence.

This script clears SOMA's text log before each run. It does not save audio, video, images, screenshots, or frames.
USAGE
}

if [[ "$MODE" == "-h" || "$MODE" == "--help" ]]; then
  usage
  exit 0
fi

case "$MODE" in
  readiness|detector|ocr|speech|full) ;;
  *)
    usage
    exit 2
    ;;
esac

require_file() {
  local label="$1"
  local path="$2"
  if [[ ! -e "$path" ]]; then
    printf 'Missing %s: %s\n' "$label" "$path" >&2
    exit 1
  fi
}

countdown() {
  local seconds="$1"
  local label="$2"
  printf '%s (%ss)\n' "$label" "$seconds"
  while [[ "$seconds" -gt 0 ]]; do
    printf '\r%3ss remaining' "$seconds"
    sleep 1
    seconds=$((seconds - 1))
  done
  printf '\rDone.              \n'
}

verify() {
  if "$NODE_BIN" "$SCRIPT_DIR/verify_native_readiness.mjs" "$@" &&
    "$NODE_BIN" "$SCRIPT_DIR/audit_no_raw_media.mjs" >/dev/null; then
    "$NODE_BIN" "$SCRIPT_DIR/report_native_live_test.mjs" --mode "$MODE" --out "$REPORT_FILE" >/dev/null
    return 0
  fi
  "$NODE_BIN" "$SCRIPT_DIR/report_native_live_test.mjs" --mode "$MODE" --out "$REPORT_FILE" >/dev/null || true
  printf '\nLive test report: %s\n' "$REPORT_FILE" >&2
  return 1
}

launch_clean() {
  "$SCRIPT_DIR/setup_native_runtime.sh"
  require_file "native app" "$APP_PATH"
  pkill -f "/FastVLM App.app/Contents/MacOS/FastVLM App" >/dev/null 2>&1 || true
  pkill -f "soma_perception" >/dev/null 2>&1 || true
  pkill -f "whisper-stream" >/dev/null 2>&1 || true
  rm -f "$LOG_FILE"
  open "$APP_PATH"
  countdown 90 "Warming up SOMA native app"
}

prompt_phase() {
  local seconds="$1"
  local message="$2"
  printf '\n%s\n' "$message"
  countdown "$seconds" "Recording text-only memory evidence"
}

launch_clean

case "$MODE" in
  readiness)
    verify
    ;;
  detector)
    prompt_phase 45 "Show a person or clear object in the camera view. Keep it visible and steady."
    verify --require-detector-memory
    ;;
  ocr)
    prompt_phase 60 "Show a sign, board, printed page, or screen with readable text. Hold it steady."
    verify --require-ocr
    ;;
  speech)
    prompt_phase 45 "Speak near the Mac: 'SOMA test pencil backpack thermal camera.'"
    countdown 30 "Waiting for local Whisper text commit"
    verify --require-speech
    ;;
  full)
    verify
    prompt_phase 45 "Phase 1: show a person or clear object in the camera view."
    verify --require-detector-memory
    prompt_phase 60 "Phase 2: show a sign, board, printed page, or screen with readable text."
    verify --require-ocr
    prompt_phase 45 "Phase 3: speak near the Mac: 'SOMA test pencil backpack thermal camera.'"
    countdown 30 "Waiting for local Whisper text commit"
    verify --require-speech
    ;;
esac

printf '\nSOMA native live test passed: %s\n' "$MODE"
printf 'Text log: %s\n' "$LOG_FILE"
printf 'Live test report: %s\n' "$REPORT_FILE"
