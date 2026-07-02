#!/usr/bin/env bash
set -euo pipefail

DEVICE_ID="${TRACE_DEVICE_UDID:-00008150-001460D83686401C}"
BUNDLE_ID="${TRACE_BUNDLE_ID:-de.zer00.trace}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT_DIR="${1:-$APP_ROOT/device_captures}"
TMP_JSON="$(mktemp)"
cleanup() {
  rm -f "$TMP_JSON"
}
trap cleanup EXIT

mkdir -p "$OUT_DIR"

xcrun devicectl device info files \
  --device "$DEVICE_ID" \
  --domain-type appDataContainer \
  --domain-identifier "$BUNDLE_ID" \
  --subdirectory Documents/TraceCaptures \
  --json-output "$TMP_JSON" >/dev/null

LATEST_FILE="$(/usr/bin/python3 - "$TMP_JSON" <<'PY'
import json, sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    payload = json.load(fh)

files = payload.get("result", {}).get("files", [])
movies = [
    item for item in files
    if not item.get("resources", {}).get("isDirectory")
    and item.get("name", "").lower().endswith(".mov")
]

if not movies:
    sys.exit(1)

movies.sort(key=lambda item: item.get("metadata", {}).get("lastModDate", ""))
print(movies[-1]["relativePath"])
PY
)" || {
  echo "No .mov capture found yet in Documents/TraceCaptures on device $DEVICE_ID." >&2
  exit 1
}

LOCAL_PATH="$OUT_DIR/$(basename "$LATEST_FILE")"

xcrun devicectl device copy from \
  --device "$DEVICE_ID" \
  --domain-type appDataContainer \
  --domain-identifier "$BUNDLE_ID" \
  --source "Documents/TraceCaptures/$LATEST_FILE" \
  --destination "$LOCAL_PATH"

echo "Pulled latest iPhone capture to:"
echo "$LOCAL_PATH"
