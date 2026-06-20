#!/usr/bin/env bash
set -euo pipefail

MODEL_KEY="${1:-nvidia/nemotron-3-nano-omni}"
IDENTIFIER="${SOMA_LOCAL_MODEL_ID:-soma-local-worker}"
TTL_SECONDS="${SOMA_LOCAL_MODEL_TTL:-7200}"
PARALLEL="${SOMA_LOCAL_MODEL_PARALLEL:-1}"
PORT="${SOMA_LOCAL_MODEL_PORT:-1234}"

if ! command -v lms >/dev/null 2>&1; then
  echo "LM Studio CLI (lms) is not available. Open LM Studio once or install its CLI first." >&2
  exit 1
fi

SERVER_JSON="$(lms server status --json)"
if ! printf '%s' "$SERVER_JSON" | grep -q '"running":true'; then
  echo "Starting LM Studio local server on 127.0.0.1:${PORT}..."
  lms server start --bind 127.0.0.1 --port "${PORT}"
else
  echo "LM Studio local server is already running."
fi

LOADED_JSON="$(lms ps --json)"
if printf '%s' "$LOADED_JSON" | grep -q "\"identifier\":\"${IDENTIFIER}\""; then
  echo "Local worker model '${IDENTIFIER}' is already loaded."
else
  echo "Loading '${MODEL_KEY}' as '${IDENTIFIER}'..."
  lms load "${MODEL_KEY}" \
    --identifier "${IDENTIFIER}" \
    --ttl "${TTL_SECONDS}" \
    --parallel "${PARALLEL}" \
    -y
fi

echo
echo "Local worker stack ready."
echo "Server: http://127.0.0.1:${PORT}"
echo "Model identifier: ${IDENTIFIER}"
echo
echo "Try:"
echo "python3 scripts/local_model_worker.py --model ${IDENTIFIER} --mode scout --task \"Summarize likely risks in the provided file.\" --context-file /Users/zer00/Documents/VLM/soma_hub/graph.py"
