#!/bin/bash
# Userland supervisor: keeps ollama + trace_brain_server alive 24/7.
# Start with: bash scripts/trace_supervise.sh &
# Check: curl http://127.0.0.1:8765/health && curl http://127.0.0.1:11434/api/tags
#
# WHY NOT launchd? TCC blocks launchd LaunchAgents from reading ~/Documents.
# This runs in the already-authorized session so no Full Disk Access grant needed.
# Survives the terminal closing; only gap is a full reboot.

set -euo pipefail
cd /Users/zer00/Documents/VLM || exit 1

LOG=/tmp/trace_supervise.log
VENV=.venv/bin/python3

log() { echo "$(date '+%F %T')  $*" | tee -a "$LOG"; }

log "trace_supervise START pid=$$"

# Ensure ollama app is running (it self-daemonizes)
ensure_ollama() {
  if ! curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    log "ollama not responding — launching"
    open -a Ollama 2>/dev/null || /usr/local/bin/ollama serve >> "$LOG" 2>&1 &
    sleep 5
  fi
}

# Ensure brain server is up
ensure_brain() {
  # If a brain process exists (even mid-load), do NOT start another — health may
  # lag process start by seconds while gemma loads. Guarding on health alone double-starts.
  if pgrep -f "trace_brain_server" >/dev/null 2>&1; then
    return
  fi
  if ! curl -sf http://127.0.0.1:8765/health >/dev/null 2>&1; then
    log "brain :8765 down — restarting"
    pkill -f "trace_brain_server" 2>/dev/null || true
    sleep 1
    TRACE_BIND=0.0.0.0 TRACE_BRAIN_PORT=8765 TRACE_PERCEIVE=1 PYTHONUNBUFFERED=1 \
      nohup caffeinate -is "$VENV" scripts/trace_brain_server.py >> /tmp/trace_brain.log 2>&1 &
    sleep 3
    if curl -sf http://127.0.0.1:8765/health >/dev/null 2>&1; then
      log "brain :8765 UP"
    else
      log "brain :8765 FAILED to start — check /tmp/trace_brain.log"
    fi
  fi
}

ensure_cockpit() {
  if ! curl -sf http://127.0.0.1:8799/ops >/dev/null 2>&1; then
    log "cockpit :8799 down — restarting"
    pkill -f "cockpit_ask_server" 2>/dev/null || true
    sleep 1
    nohup "$VENV" scripts/cockpit_ask_server.py >> /tmp/trace_cockpit.log 2>&1 &
    sleep 2
    log "cockpit restarted"
  fi
}

ensure_worker() {
  if ! pgrep -f "autonomous_worker" >/dev/null 2>&1; then
    log "autonomous_worker down — restarting (auto-apply, full-suite gated)"
    # WORKER_AUTOAPPLY=1: a patch lands only if its test AND the whole suite pass in an
    # isolated copy — safe autonomous building 24/7 while the Chief sleeps.
    WORKER_AUTOAPPLY=1 nohup "$VENV" scripts/autonomous_worker.py >> /tmp/trace_worker.log 2>&1 &
    sleep 2
    log "worker restarted (pid $(pgrep -f autonomous_worker))"
  fi
}

while true; do
  ensure_ollama
  ensure_brain
  ensure_cockpit
  ensure_worker
  sleep 30
done
