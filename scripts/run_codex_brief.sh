#!/bin/zsh
# Orchestration: lead (Claude) fires Codex non-interactively on a brief.
# Usage: ./scripts/run_codex_brief.sh ops/CODEX_BRIEF_7_....md
set -u
cd "$(dirname "$0")/.."
BRIEF="$1"
CODEX=/Applications/Codex.app/Contents/Resources/codex
LOG=/tmp/codex_run_$(date +%H%M%S).log
echo "[codex-run] brief=$BRIEF log=$LOG"
"$CODEX" exec --cd "$PWD" --full-auto -s workspace-write \
  "You are Codex working in this repo. Read $BRIEF and execute it fully. \
Follow the laws section exactly. The build recipe and device install \
procedure are in ops/HANDOVER.md. Work autonomously to completion, then \
write ops/$(basename ${BRIEF%.md})_RESULT.md describing device-verified \
results." > "$LOG" 2>&1
echo "[codex-run] exit=$? — tail:"
tail -5 "$LOG"
