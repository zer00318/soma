#!/bin/zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CAPTURE_DIR="${1:-data/phone_captures/bedroom_dense_353f}"
KEYFRAME_DIR="${2:-data/phone_captures/bedroom_kf40}"
STORE_PATH="${3:-data/trace_store_frontier.sqlite3}"
OUT_PATH="${4:-evaluation/ras/store_eval_frontier.json}"
HELPER_MODE="${TRACE_ROOM_HELPER_MODE:-scene_only}"

if [[ ! -d "$CAPTURE_DIR" ]]; then
  echo "capture dir not found: $CAPTURE_DIR" >&2
  exit 2
fi

if [[ ! -f .secrets/frontier.env ]]; then
  echo "missing .secrets/frontier.env" >&2
  exit 2
fi

export ANTHROPIC_API_KEY="$(grep -m1 '^ANTHROPIC_API_KEY=' .secrets/frontier.env | cut -d= -f2- | tr -d '\r\n ')"
if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "ANTHROPIC_API_KEY empty after load" >&2
  exit 2
fi

echo "[cycle] capture=$CAPTURE_DIR"
echo "[cycle] keyframes=$KEYFRAME_DIR"
echo "[cycle] store=$STORE_PATH"
echo "[cycle] out=$OUT_PATH"
echo "[cycle] helper_mode=$HELPER_MODE"

.venv/bin/python scripts/select_keyframes.py "$CAPTURE_DIR" "$KEYFRAME_DIR" --n 40
.venv/bin/python scripts/light_ingest.py "$KEYFRAME_DIR" --store "$STORE_PATH" --backend frontier --helper-mode "$HELPER_MODE" --fresh --sleep-bind
.venv/bin/python scripts/probe_bedroom_coverage.py --store "$STORE_PATH"
TRACE_RESTRICT_SOURCES=phone_camera .venv/bin/python evaluation/annotate_live.py \
  --store "$STORE_PATH" \
  --annotations data/phone_captures/live/ground_truth.json \
  --reasoner frontier \
  --repeats 1 \
  --out "$OUT_PATH"
