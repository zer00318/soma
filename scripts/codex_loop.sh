#!/usr/bin/env bash
# 24/7 local-agent driver. Runs `codex exec` on queued briefs ONE AT A TIME,
# unattended. Each brief lands its work on its OWN branch (the brief tells codex
# to branch + commit) so nothing reaches the live path without human review.
#
# Safe by design:
#   - never runs two codex agents at once (serializes on pgrep)
#   - tasks are review-branches, never auto-merged to main
#   - every run is fully logged under ops/codex_queue/logs/
#
# Launch detached:  nohup bash scripts/codex_loop.sh > /tmp/codex_loop.out 2>&1 & disown
# Stop:            touch ops/codex_queue/STOP   (loop exits after the current task)
set -u
ROOT="/Users/zer00/Documents/VLM"
Q="$ROOT/ops/codex_queue"
mkdir -p "$Q/pending" "$Q/running" "$Q/done" "$Q/logs"
cd "$ROOT" || exit 1

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$Q/driver.log"; }
log "driver started (pid $$)"

while true; do
  [ -f "$Q/STOP" ] && { log "STOP file present — exiting"; rm -f "$Q/STOP"; exit 0; }

  # Don't start a task while ANY codex is active (the manual task-1 run, or a prior loop task).
  if pgrep -f "codex exec" >/dev/null 2>&1; then sleep 30; continue; fi

  brief="$(ls "$Q"/pending/*.md 2>/dev/null | sort | head -1)"
  if [ -z "${brief:-}" ]; then sleep 60; continue; fi   # idle until a brief is queued

  name="$(basename "$brief" .md)"
  mv "$brief" "$Q/running/$name.md"
  ts="$(date +%Y%m%d-%H%M%S)"
  logf="$Q/logs/${name}.${ts}.log"
  log "START $name  -> $logf"

  codex exec -C "$ROOT" -s workspace-write --skip-git-repo-check \
    "Implement the brief in $Q/running/$name.md exactly. Follow every guardrail in it. \
Create and work on the branch it names (or codex/$name if none), make all its acceptance \
tests pass, run '.venv/bin/python -m pytest tests/ -q', commit on that branch (DO NOT push, \
DO NOT merge to main). End by printing a summary of changed files + the pytest result." \
    >> "$logf" 2>&1
  rc=$?

  # Codex's sandbox can't write .git, so the driver checkpoints the work (code paths
  # only — model binaries stay gitignored). Lands on this dev branch for review; never main/push.
  git -C "$ROOT" add scripts src tests ops evaluation .gitignore >/dev/null 2>&1
  if ! git -C "$ROOT" diff --cached --quiet 2>/dev/null; then
    git -C "$ROOT" commit -q -m "codex(${name}): autonomous task output [needs review]" >>"$logf" 2>&1 \
      && log "committed $name ($(git -C "$ROOT" rev-parse --short HEAD))"
  else
    log "no code changes to commit for $name"
  fi

  mv "$Q/running/$name.md" "$Q/done/$name.md"
  log "DONE  $name  rc=$rc  (committed on $(git -C "$ROOT" branch --show-current); log $logf)"
  sleep 20
done
