#!/bin/zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

function show_list() {
  cat <<'EOF'
Phase 1 Serial Queue

04  Store Hygiene
    Command:
      .venv/bin/python scripts/build_demo_store.py

06  iOS Dense Capture Fix (only if fps regresses)
    Command:
      ./scripts/run_codex_brief.sh ops/serial_queue/06_ios_dense_capture_codex.md

07  Controlled Demo Lock
    Command:
      ./scripts/run_codex_brief.sh ops/serial_queue/07_controlled_demo_lock.md

08  Bedroom Capture Overhaul
    Command:
      .venv/bin/python scripts/probe_bedroom_coverage.py --store data/trace_store_frontier.sqlite3
    Prerequisite:
      Task 07 validated

09  Frontier Demo Number
    Command:
      ./scripts/run_frontier_room_cycle.sh \
        data/phone_captures/bedroom_dense_353f \
        data/phone_captures/bedroom_kf40 \
        data/trace_store_frontier.sqlite3 \
        evaluation/ras/store_eval_frontier.json
    Prerequisite:
      Task 08 validated

10  Dominant Failure Only
    Command:
      ./scripts/run_codex_brief.sh ops/serial_queue/10_dominant_failure_only.md
    Prerequisite:
      Task 09 validated

11  Truth Surface Final
    Command:
      ./scripts/run_codex_brief.sh ops/serial_queue/11_truth_surface_final.md
    Prerequisite:
      Task 10 validated
EOF
}

case "${1:-list}" in
  list)
    show_list
    ;;
  04)
    .venv/bin/python scripts/build_demo_store.py
    ;;
  06)
    ./scripts/run_codex_brief.sh ops/serial_queue/06_ios_dense_capture_codex.md
    ;;
  07)
    ./scripts/run_codex_brief.sh ops/serial_queue/07_controlled_demo_lock.md
    ;;
  08)
    .venv/bin/python scripts/probe_bedroom_coverage.py --store data/trace_store_frontier.sqlite3
    ;;
  09)
    ./scripts/run_frontier_room_cycle.sh \
      data/phone_captures/bedroom_dense_353f \
      data/phone_captures/bedroom_kf40 \
      data/trace_store_frontier.sqlite3 \
      evaluation/ras/store_eval_frontier.json
    ;;
  10)
    ./scripts/run_codex_brief.sh ops/serial_queue/10_dominant_failure_only.md
    ;;
  11)
    ./scripts/run_codex_brief.sh ops/serial_queue/11_truth_surface_final.md
    ;;
  *)
    echo "unknown task: ${1}" >&2
    exit 1
    ;;
esac
