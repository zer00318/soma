#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${TRACE_WORKSPACE:-/Users/zer00/Documents/VLM}"
TOOLS_DIR="$WORKSPACE/tools"
PYTHON_BIN="$WORKSPACE/.venv/bin/python"
YOLO_MODEL="$WORKSPACE/yolo11n.pt"
ASR_MODEL="$WORKSPACE/models/asr/ggml-base.en.bin"
WHISPER_LINK="$TOOLS_DIR/whisper-stream"

mkdir -p "$TOOLS_DIR"

find_whisper_stream() {
  if [[ -x "$WHISPER_LINK" ]]; then
    printf '%s\n' "$WHISPER_LINK"
    return 0
  fi
  if command -v whisper-stream >/dev/null 2>&1; then
    command -v whisper-stream
    return 0
  fi
  for candidate in /opt/homebrew/bin/whisper-stream /usr/local/bin/whisper-stream; do
    if [[ -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

WHISPER_BIN="$(find_whisper_stream || true)"
if [[ -n "$WHISPER_BIN" && "$WHISPER_BIN" != "$WHISPER_LINK" ]]; then
  ln -sf "$WHISPER_BIN" "$WHISPER_LINK"
fi

missing=0
check_path() {
  local label="$1"
  local path="$2"
  if [[ -e "$path" ]]; then
    printf 'OK   %s: %s\n' "$label" "$path"
  else
    printf 'MISS %s: %s\n' "$label" "$path"
    missing=1
  fi
}

check_path "workspace" "$WORKSPACE"
check_path "python helper" "$PYTHON_BIN"
check_path "YOLO model" "$YOLO_MODEL"
check_path "ASR model" "$ASR_MODEL"
check_path "whisper-stream" "$WHISPER_LINK"

if [[ "$missing" -ne 0 ]]; then
  printf '\nNative runtime setup is incomplete.\n'
  exit 1
fi

printf '\nNative runtime setup is ready. Raw audio/video/image files are not created by this script.\n'
