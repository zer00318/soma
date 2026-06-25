#!/usr/bin/env bash
# TRACE camera stack: perception worker (camera+scheduler) + enrichment daemon
# (gemma vision -> graph). Run from a Terminal that has camera permission:
#
#   nohup ./scripts/run_trace_camera.sh 12 > /dev/null 2>&1 &
#
# arg1 = enrichments/hour budget (default 12). Logs:
#   /tmp/trace_budget_run.json  - perception ticks + enrichment_request lines
#   /tmp/trace_enricher.log     - VLM passes and stored graph facts
# Stop everything: pkill -f trace_perception
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
BUDGET="${1:-12}"

mkdir -p /tmp/trace_enrich
nohup .venv/bin/python -m trace_perception.enricher --db data/trace_hub.sqlite3 \
  >> /tmp/trace_enricher.log 2>&1 &
echo "enricher started (pid $!)"

exec .venv/bin/python -m trace_perception.worker \
  --enrich-budget "$BUDGET" --frame-stride 8 \
  >> /tmp/trace_budget_run.json 2>&1
