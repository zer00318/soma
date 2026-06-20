#!/bin/bash
# Overnight: re-watch the home video with a COUNTING-AWARE eye (count groups of
# similar objects + note differences at the seeing stage), then rebuild the one
# deduplicated room memory from it. Both steps checkpointed. Morning: compare
# world_memory_count.json vs world_memory.json.
set -u
cd "$(dirname "$0")/.." || exit 1
LOG=/tmp/overnight_recount.log
echo "=== overnight recount started $(date) ===" > "$LOG"

KF=data/walks/home_capture_20260613/memory/kf_memory_count.json
WM=data/walks/home_capture_20260613/memory/world_memory_count.json

echo "[1/2] counting-aware re-caption (Qwen2.5-VL)..." >> "$LOG"
.venv/bin/python scripts/build_keyframe_memory.py --counting --cap 120 \
    --out "$KF" >> "$LOG" 2>&1
echo "[1/2] done $(date)" >> "$LOG"

echo "[2/2] rebuild deduplicated world memory..." >> "$LOG"
python3 scripts/build_world_memory.py --memory "$KF" --out "$WM" >> "$LOG" 2>&1
echo "[2/2] done $(date)" >> "$LOG"
echo "=== overnight recount finished $(date) ===" >> "$LOG"
