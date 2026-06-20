#!/usr/bin/env bash
set -euo pipefail

cd /Users/zer00/Documents/VLM

exec python3 scripts/claude_supervisor_loop.py "$@"
